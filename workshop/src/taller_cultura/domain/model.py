"""Entidades y objetos de valor del taller de diagnóstico cultural.

Contexto de negocio (extraído del Excel original):

- Existen 5 "tipos de cultura": LOGRO, CENTRADA EN EL CLIENTE, EQUIPO UNICO,
  INNOVADORA, LAS PERSONAS PRIMERO.
- Cada tipo de cultura se evalúa en varias categorías (aspectos):
  TIPO DE CULTURA (definición), Comportamientos, Símbolos, Sistemas.
- Cada aspecto tiene varios ítems (frases) que un calificador puntúa con un
  semáforo: A (Alineado/Alto), R (Regular), V (Vacío/Bajo) - la escala 1-12
  original se traduce a este semáforo en el taller.
- Cada calificación se hace en dos momentos: PASADO y ACTUAL.
- Varios calificadores (personas de una EMPRESA) participan y luego se
  calcula un CONSENSO por aspecto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .exceptions import (
    CategoriaInvalida,
    MomentoInvalido,
    TipoCulturaDesconocido,
    ValoracionInvalida,
)


class TipoCultura(str, Enum):
    """Los 5 tipos de cultura organizacional evaluados en el taller."""

    LOGRO = "LOGRO"
    CENTRADA_EN_EL_CLIENTE = "CENTRADA EN EL CLIENTE"
    EQUIPO_UNICO = "EQUIPO UNICO"
    INNOVADORA = "INNOVADORA"
    LAS_PERSONAS_PRIMERO = "LAS PERSONAS PRIMERO"

    @classmethod
    def desde_texto(cls, texto: str) -> "TipoCultura":
        clave = (texto or "").strip().upper()
        for miembro in cls:
            if miembro.value.upper() == clave:
                return miembro
        raise TipoCulturaDesconocido(f"Tipo de cultura desconocido: {texto!r}")

    @property
    def animal(self) -> str:
        """El animal con que el taller representa a cada cultura.

        Es parte del lenguaje del taller —así titula sus gráficos la hoja
        CULTURAS del libro original—, así que el reporte lo conserva.
        """
        return {
            "LOGRO": "Águila real",
            "CENTRADA EN EL CLIENTE": "Delfín",
            "EQUIPO UNICO": "Lobo",
            "INNOVADORA": "Pulpo",
            "LAS PERSONAS PRIMERO": "Colibrí",
        }[self.value]


class CategoriaAspecto(str, Enum):
    """Las categorías dentro de las cuales se agrupan los ítems evaluados."""

    TIPO_DE_CULTURA = "TIPO DE CULTURA"
    COMPORTAMIENTOS = "Comportamientos"
    SIMBOLOS = "Símbolos"
    SISTEMAS = "Sistemas"

    @classmethod
    def desde_texto(cls, texto: str) -> "CategoriaAspecto":
        clave = (texto or "").strip().lower()
        alias = {
            "tipo de cultura": cls.TIPO_DE_CULTURA,
            "comportamientos": cls.COMPORTAMIENTOS,
            "simbolos": cls.SIMBOLOS,
            "símbolos": cls.SIMBOLOS,
            "sistemas": cls.SISTEMAS,
        }
        if clave not in alias:
            raise CategoriaInvalida(f"Categoría desconocida: {texto!r}")
        return alias[clave]


class Momento(str, Enum):
    """Momento temporal en el que se hace la calificación."""

    PASADO = "PASADO"
    ACTUAL = "ACTUAL"

    @classmethod
    def desde_texto(cls, texto: str) -> "Momento":
        clave = (texto or "").strip().upper()
        for miembro in cls:
            if miembro.value == clave:
                return miembro
        raise MomentoInvalido(f"Momento desconocido: {texto!r}")


class Valoracion(str, Enum):
    """Semáforo de calificación usado en el taller: símbolos R / A / V.

    El peso numérico de cada símbolo replica EXACTAMENTE las fórmulas
    originales del Excel (columnas de cálculo N:W de la hoja TALLER):
    `IF(celda="V",1,IF(celda="A",0.5,IF(celda="R",0,"")))`. Es decir, en
    este taller el orden de la escala es R (bajo) < A (medio) < V (alto);
    no se le atribuye ningún significado adicional a las letras en sí,
    solo se preserva el orden y peso que ya usaba la planilla.
    """

    BAJO = "R"
    MEDIO = "A"
    ALTO = "V"

    @classmethod
    def desde_texto(cls, texto: str) -> "Valoracion":
        clave = (texto or "").strip().upper()
        for miembro in cls:
            if miembro.value == clave:
                return miembro
        raise ValoracionInvalida(f"Valoración fuera del semáforo A/R/V: {texto!r}")

    @property
    def peso(self) -> int:
        """Peso numérico usado para promediar/ordenar valoraciones (0/1/2),
        proporcional al 0 / 0.5 / 1 que usa la fórmula original del Excel.
        """
        return {"R": 0, "A": 1, "V": 2}[self.value]


@dataclass(frozen=True, slots=True)
class Empresa:
    """La organización que es objeto del diagnóstico."""

    id: int | None
    nombre: str


@dataclass(frozen=True, slots=True)
class SesionTaller:
    """Una aplicación concreta del taller: una empresa, en una fecha dada.

    Una misma empresa puede repetir el taller más adelante para medir cómo
    evolucionó su cultura. Cada repetición es una sesión nueva con su
    propio `numero_version` (1 la primera, 2 la siguiente, …), y comparar
    dos sesiones de la misma empresa es lo que produce el reporte de
    "antes y ahora".
    """

    id: int | None
    empresa: str
    fecha_taller: date
    numero_version: int = 1
    archivo_origen: str = ""

    @property
    def etiqueta(self) -> str:
        """Texto corto para identificarla en listas y encabezados."""
        return f"v{self.numero_version} · {self.fecha_taller.isoformat()}"

    @property
    def titulo(self) -> str:
        return f"{self.empresa} — {self.etiqueta}"


@dataclass(frozen=True, slots=True)
class Calificador:
    """Una persona que participa calificando ítems del taller."""

    codigo: int
    nombre: str
    empresa_id: int | None = None


@dataclass(frozen=True, slots=True)
class Aspecto:
    """Un ítem/frase evaluable dentro de una categoría y tipo de cultura."""

    id: int | None
    tipo_cultura: TipoCultura
    categoria: CategoriaAspecto
    orden: int
    texto: str


@dataclass(frozen=True, slots=True)
class Calificacion:
    """Una valoración puntual: quién, qué aspecto, en qué momento, cuánto."""

    aspecto_id: int
    calificador_codigo: int
    momento: Momento
    valoracion: Valoracion
    es_consenso: bool = False


@dataclass(frozen=True, slots=True)
class ResumenAspecto:
    """Estadística agregada de un aspecto en un momento dado."""

    tipo_cultura: TipoCultura
    categoria: CategoriaAspecto
    momento: Momento
    total_alineado: int
    total_regular: int
    total_vacio: int

    @property
    def total(self) -> int:
        return self.total_alineado + self.total_regular + self.total_vacio

    @property
    def promedio_ponderado(self) -> float:
        if self.total == 0:
            return 0.0
        suma = self.total_alineado * 2 + self.total_regular * 1 + self.total_vacio * 0
        return round(suma / self.total, 2)
