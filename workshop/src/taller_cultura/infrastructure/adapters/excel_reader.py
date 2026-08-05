"""Adaptador de salida: lee el Excel original del taller de cultura.

Implementa el puerto `LectorTaller`. Es el único lugar del proyecto que
conoce la disposición física, irregular, del archivo `.xlsx` original
(hojas `CALIFICADORES` y `TALLER`). Si el formato de origen cambia, solo
este archivo debería tocarse.

Estructura descubierta en la hoja TALLER (fila/columna en notación Excel,
1-indexado):
- Columnas C/D, E/F, G/H, I/J, K/L son pares (PASADO, ACTUAL) para los
  5 tipos de cultura, en ese orden fijo: LOGRO, CENTRADA EN EL CLIENTE,
  EQUIPO UNICO, INNOVADORA, LAS PERSONAS PRIMERO.
- Cada "bloque de ítem" empieza en una fila cuya columna B contiene una
  de las etiquetas de categoría/ítem ("TIPO DE CULTURA", "Otras
  palabras", "Una definición", "Comportamientos", "Símbolos", "Sistemas").
  Las columnas C, E, G, I, K de esa fila traen el texto del ítem para
  cada tipo de cultura (excepto la fila "TIPO DE CULTURA", que solo
  encabeza la sección y no es un ítem calificable).
- Debajo de cada fila de ítem hay N filas de respuesta: columna B trae
  la posición del calificador (1..12) o la etiqueta "CONSENSO"; las
  columnas C..L (pares PASADO/ACTUAL) traen el símbolo A/R/V si fue
  calificado. El bloque termina cuando la columna B deja de ser un
  número de posición o "CONSENSO".
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import openpyxl
import pandas as pd

from taller_cultura.application.ports import LectorTaller
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    Calificador,
    CategoriaAspecto,
    Empresa,
    Momento,
    TipoCultura,
    Valoracion,
)

HOJA_CALIFICADORES = "CALIFICADORES"
HOJA_TALLER = "TALLER"

CODIGO_CALIFICADOR_CONSENSO = 0
NOMBRE_CALIFICADOR_CONSENSO = "CONSENSO"

# Columnas (1-indexadas, estilo Excel) de la hoja TALLER: tipo_cultura -> (col_pasado, col_actual)
COLUMNAS_TIPO_CULTURA: dict[TipoCultura, tuple[int, int]] = {
    TipoCultura.LOGRO: (3, 4),
    TipoCultura.CENTRADA_EN_EL_CLIENTE: (5, 6),
    TipoCultura.EQUIPO_UNICO: (7, 8),
    TipoCultura.INNOVADORA: (9, 10),
    TipoCultura.LAS_PERSONAS_PRIMERO: (11, 12),
}
COLUMNA_ETIQUETA_ITEM = 2  # columna B

# Etiquetas normalizadas (minúsculas, sin acentos) que marcan el inicio de un bloque.
ETIQUETA_A_CATEGORIA: dict[str, CategoriaAspecto | None] = {
    "tipo de cultura": None,  # encabezado de sección, no es un ítem calificable
    "otras palabras": CategoriaAspecto.TIPO_DE_CULTURA,
    "una definicion": CategoriaAspecto.TIPO_DE_CULTURA,
    "comportamientos": CategoriaAspecto.COMPORTAMIENTOS,
    "simbolos": CategoriaAspecto.SIMBOLOS,
    "sistemas": CategoriaAspecto.SISTEMAS,
}


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_acentos.strip().lower()


def _es_valoracion_valida(texto: object) -> bool:
    return isinstance(texto, str) and texto.strip().upper() in {"A", "R", "V"}


@dataclass
class _BloqueItem:
    """Un ítem calificable ya localizado en la hoja: su fila y, para cada
    tipo de cultura presente, el Aspecto de dominio junto con el id
    temporal (posición en la lista plana) que lo identifica antes de que
    el repositorio le asigne un id real.
    """

    fila_item: int
    aspectos_por_cultura: dict[TipoCultura, tuple[int, Aspecto]]


class LectorTallerExcel(LectorTaller):
    """Lee empresas, calificadores, aspectos y calificaciones del `.xlsx`."""

    def __init__(self, ruta_excel: str | Path) -> None:
        self._ruta = Path(ruta_excel)
        self._workbook = openpyxl.load_workbook(self._ruta, data_only=True)
        self._bloques: list[_BloqueItem] | None = None

    def leer_empresas(self) -> list[Empresa]:
        hoja = self._workbook[HOJA_CALIFICADORES]
        nombre = hoja["C1"].value or hoja["B1"].value
        if not nombre or str(nombre).strip().upper() in {"EMPRESA", ""}:
            nombre = self._ruta.stem
        return [Empresa(id=None, nombre=str(nombre).strip())]

    def leer_calificadores(self) -> list[Calificador]:
        """Lee el roster de la hoja CALIFICADORES (filas 4 a 15: COD/NOMBRES)."""
        df = pd.read_excel(
            self._ruta,
            sheet_name=HOJA_CALIFICADORES,
            header=None,
            skiprows=3,
            nrows=12,
            usecols=[1, 2],
            names=["codigo", "nombre"],
        )
        calificadores = [
            Calificador(codigo=CODIGO_CALIFICADOR_CONSENSO, nombre=NOMBRE_CALIFICADOR_CONSENSO)
        ]
        for fila in df.itertuples(index=False):
            if pd.isna(fila.codigo):
                continue
            codigo = int(fila.codigo)
            nombre = str(fila.nombre) if not pd.isna(fila.nombre) else str(codigo)
            calificadores.append(Calificador(codigo=codigo, nombre=nombre))
        return calificadores

    def leer_aspectos(self) -> list[Aspecto]:
        aspectos: list[Aspecto] = []
        for bloque in self._obtener_bloques():
            for _tipo_cultura, (_id_temporal, aspecto) in bloque.aspectos_por_cultura.items():
                aspectos.append(aspecto)
        return aspectos

    def leer_calificaciones(self, aspectos: list[Aspecto]) -> list[Calificacion]:
        """Recorre los bloques ya localizados extrayendo sus filas de
        respuesta. El id temporal de cada calificación coincide con la
        posición del aspecto correspondiente en la lista que devuelve
        `leer_aspectos` (misma numeración), que la capa de aplicación
        luego remapea al id real asignado por el repositorio.
        """
        calificaciones: list[Calificacion] = []
        for bloque in self._obtener_bloques():
            calificaciones.extend(self._leer_respuestas_del_bloque(bloque))
        return calificaciones

    # -- helpers privados -------------------------------------------------

    def _obtener_bloques(self) -> list[_BloqueItem]:
        if self._bloques is None:
            self._bloques = list(self._localizar_bloques())
        return self._bloques

    def _localizar_bloques(self):
        """Recorre la hoja TALLER una sola vez, ubicando cada bloque de
        ítem y asignando a cada (bloque, tipo_cultura) el id temporal
        secuencial que tendrá en la lista plana de aspectos.
        """
        hoja = self._workbook[HOJA_TALLER]
        orden_por_categoria: dict[CategoriaAspecto, int] = {}
        id_temporal = 0

        for fila in range(1, hoja.max_row + 1):
            etiqueta = hoja.cell(fila, COLUMNA_ETIQUETA_ITEM).value
            if not isinstance(etiqueta, str):
                continue
            clave = _normalizar(etiqueta)
            if clave not in ETIQUETA_A_CATEGORIA:
                continue

            categoria = ETIQUETA_A_CATEGORIA[clave]
            if categoria is None:
                continue  # fila "TIPO DE CULTURA": encabezado, no es ítem

            orden = orden_por_categoria.get(categoria, 0) + 1
            orden_por_categoria[categoria] = orden

            aspectos_por_cultura: dict[TipoCultura, tuple[int, Aspecto]] = {}
            for tipo_cultura, (col_pasado, _col_actual) in COLUMNAS_TIPO_CULTURA.items():
                texto = hoja.cell(fila, col_pasado).value
                if not isinstance(texto, str) or not texto.strip():
                    continue
                aspecto = Aspecto(
                    id=None,
                    tipo_cultura=tipo_cultura,
                    categoria=categoria,
                    orden=orden,
                    texto=texto.strip(),
                )
                aspectos_por_cultura[tipo_cultura] = (id_temporal, aspecto)
                id_temporal += 1

            if aspectos_por_cultura:
                yield _BloqueItem(fila_item=fila, aspectos_por_cultura=aspectos_por_cultura)

    def _leer_respuestas_del_bloque(self, bloque: _BloqueItem) -> list[Calificacion]:
        hoja = self._workbook[HOJA_TALLER]
        calificaciones: list[Calificacion] = []

        fila = bloque.fila_item + 1
        while fila <= hoja.max_row:
            etiqueta_b = hoja.cell(fila, COLUMNA_ETIQUETA_ITEM).value
            codigo_calificador = self._codigo_calificador_de_fila(etiqueta_b)
            if codigo_calificador is None:
                break

            for tipo_cultura, (id_temporal, _aspecto) in bloque.aspectos_por_cultura.items():
                col_pasado, col_actual = COLUMNAS_TIPO_CULTURA[tipo_cultura]
                for momento, columna in (
                    (Momento.PASADO, col_pasado),
                    (Momento.ACTUAL, col_actual),
                ):
                    valor = hoja.cell(fila, columna).value
                    if not _es_valoracion_valida(valor):
                        continue
                    calificaciones.append(
                        Calificacion(
                            aspecto_id=id_temporal,
                            calificador_codigo=codigo_calificador,
                            momento=momento,
                            valoracion=Valoracion.desde_texto(valor),
                            es_consenso=(codigo_calificador == CODIGO_CALIFICADOR_CONSENSO),
                        )
                    )
            fila += 1

        return calificaciones

    @staticmethod
    def _codigo_calificador_de_fila(etiqueta: object) -> int | None:
        if isinstance(etiqueta, str) and etiqueta.strip().upper() == NOMBRE_CALIFICADOR_CONSENSO:
            return CODIGO_CALIFICADOR_CONSENSO
        if isinstance(etiqueta, (int, float)) and float(etiqueta).is_integer():
            return int(etiqueta)
        return None
