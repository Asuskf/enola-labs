"""Tests de integración contra el Excel real del taller.

Se saltan automáticamente si el archivo no está disponible.

El test importante es `test_captura_todas_las_respuestas_de_la_hoja`: fija
la invariante que un bug real rompió (el detector de bloques exigía una
etiqueta en la columna B que solo lleva el primer ítem de cada categoría,
así que perdía la mayoría de los ítems y sus calificaciones).
"""

from pathlib import Path

import pytest

from taller_cultura.domain.model import CategoriaAspecto, Momento, TipoCultura
from taller_cultura.infrastructure.adapters.excel_reader import (
    COLUMNAS_TIPO_CULTURA,
    LectorTallerExcel,
    _es_valoracion_valida,
)

RUTA_EXCEL = Path(__file__).resolve().parents[1] / "data" / "Taller para pasar a David (1).xlsx"

pytestmark = pytest.mark.skipif(
    not RUTA_EXCEL.exists(), reason="Excel del taller no disponible en esta máquina"
)


@pytest.fixture(scope="module")
def lector() -> LectorTallerExcel:
    return LectorTallerExcel(RUTA_EXCEL)


def _celdas_de_valoracion_en_la_hoja(hoja) -> set[tuple[int, int]]:
    """Toda celda con un símbolo A/R/V en las columnas de las 5 culturas."""
    columnas = [c for par in COLUMNAS_TIPO_CULTURA.values() for c in par]
    return {
        (fila, col)
        for fila in range(1, hoja.max_row + 1)
        for col in columnas
        if _es_valoracion_valida(hoja.cell(fila, col).value)
    }


def _celdas_de_eco(hoja) -> set[tuple[int, int]]:
    """Las filas inmediatamente posteriores a un CONSENSO son un VLOOKUP que
    repite ese mismo consenso: son cálculo, no respuestas, y no deben contarse.
    """
    filas_consenso = {
        fila
        for fila in range(1, hoja.max_row + 1)
        if isinstance(hoja.cell(fila, 2).value, str)
        and hoja.cell(fila, 2).value.strip().upper() == "CONSENSO"
    }
    return {
        (fila, col)
        for (fila, col) in _celdas_de_valoracion_en_la_hoja(hoja)
        if (fila - 1) in filas_consenso
    }


def test_captura_todas_las_respuestas_de_la_hoja(lector):
    """Ni una respuesta de menos (datos perdidos) ni de más (eco duplicado)."""
    hoja = lector._workbook["TALLER"]
    esperadas = _celdas_de_valoracion_en_la_hoja(hoja) - _celdas_de_eco(hoja)

    aspectos = lector.leer_aspectos()
    calificaciones = lector.leer_calificaciones(aspectos)

    assert len(calificaciones) == len(esperadas)
    assert len(esperadas) > 100, "el archivo de prueba debería traer datos reales"


def test_detecta_items_sin_etiqueta_de_categoria(lector):
    """Solo el primer ítem de cada categoría lleva etiqueta en la columna B;
    los demás la heredan. Deben catalogarse igual.
    """
    hoja = lector._workbook["TALLER"]
    aspectos = lector.leer_aspectos()

    filas_de_item = {b.fila_item for b in lector._obtener_bloques()}
    sin_etiqueta = {f for f in filas_de_item if hoja.cell(f, 2).value is None}

    assert sin_etiqueta, "el archivo de prueba tiene ítems sin etiqueta en la columna B"
    # Comportamientos tiene más de un ítem justamente por esos casos.
    ordenes = {a.orden for a in aspectos if a.categoria is CategoriaAspecto.COMPORTAMIENTOS}
    assert len(ordenes) > 1


def test_lee_las_cuatro_categorias_y_las_cinco_culturas(lector):
    aspectos = lector.leer_aspectos()

    assert {a.categoria for a in aspectos} == set(CategoriaAspecto)
    assert {a.tipo_cultura for a in aspectos} == set(TipoCultura)
    assert all(a.texto.strip() for a in aspectos)


def test_calificaciones_referencian_aspectos_validos(lector):
    aspectos = lector.leer_aspectos()
    calificaciones = lector.leer_calificaciones(aspectos)

    ids_validos = set(range(len(aspectos)))
    for calificacion in calificaciones:
        assert calificacion.aspecto_id in ids_validos
        assert 0 <= calificacion.calificador_codigo <= 12
        assert calificacion.momento in (Momento.PASADO, Momento.ACTUAL)


def test_marca_correctamente_las_filas_de_consenso(lector):
    aspectos = lector.leer_aspectos()
    calificaciones = lector.leer_calificaciones(aspectos)

    consenso = [c for c in calificaciones if c.es_consenso]
    assert consenso, "el taller trae valoraciones de consenso"
    assert all(c.calificador_codigo == 0 for c in consenso)
    assert all(c.calificador_codigo != 0 for c in calificaciones if not c.es_consenso)


def test_lee_calificadores_incluyendo_consenso(lector):
    calificadores = lector.leer_calificadores()

    codigos = {c.codigo for c in calificadores}
    assert 0 in codigos  # CONSENSO
    assert len(calificadores) >= 2
