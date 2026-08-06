"""Validación del archivo del taller antes de procesarlo.

El objetivo es no importar a ciegas: si al usuario le pasaron un libro que
no es el del taller, o que está a medio llenar, conviene decírselo *antes*
de generar un reporte que parecería válido pero no lo sería.

Se distinguen dos niveles:

- `ERROR`: el archivo no se puede procesar (falta la hoja TALLER, no se
  reconoce ningún bloque de ítems…). La importación debe detenerse.
- `AVISO`: el archivo se procesa, pero hay algo que el usuario debe saber
  al leer el reporte (no hay respuestas, falta un momento, cobertura baja).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severidad(str, Enum):
    ERROR = "ERROR"
    AVISO = "AVISO"


@dataclass(frozen=True, slots=True)
class Hallazgo:
    severidad: Severidad
    mensaje: str

    def __str__(self) -> str:  # pragma: no cover - conveniencia al imprimir
        return f"[{self.severidad.value}] {self.mensaje}"


@dataclass(frozen=True, slots=True)
class ResultadoValidacion:
    """Lo que se encontró al revisar el archivo."""

    hallazgos: tuple[Hallazgo, ...]

    @property
    def errores(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.severidad is Severidad.ERROR)

    @property
    def avisos(self) -> tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.severidad is Severidad.AVISO)

    @property
    def es_procesable(self) -> bool:
        return not self.errores

    @property
    def resumen(self) -> str:
        if self.errores:
            return f"{len(self.errores)} error(es) impiden procesar el archivo."
        if self.avisos:
            return f"Archivo válido con {len(self.avisos)} aviso(s)."
        return "Archivo válido."
