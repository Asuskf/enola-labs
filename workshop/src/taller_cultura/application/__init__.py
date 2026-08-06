"""Capa de aplicación: casos de uso que orquestan el dominio y los puertos.

No contiene lógica de negocio (eso vive en `taller_cultura.domain`) ni
detalles técnicos (eso vive en `taller_cultura.infrastructure`). Solo
coordina: llama al lector, guarda con el repositorio, pide al dominio que
calcule, entrega al exportador.
"""

from .use_cases import (
    CalcularReporteTaller,
    CalcularResumenTaller,
    ExportarPlantillaTaller,
    ExportarReporteTaller,
    ImportarTallerDesdeExcel,
    ReporteTaller,
)

__all__ = [
    "CalcularReporteTaller",
    "CalcularResumenTaller",
    "ExportarPlantillaTaller",
    "ExportarReporteTaller",
    "ImportarTallerDesdeExcel",
    "ReporteTaller",
]
