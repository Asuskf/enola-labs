"""Capa de aplicación: casos de uso que orquestan el dominio y los puertos.

No contiene lógica de negocio (eso vive en `taller_cultura.domain`) ni
detalles técnicos (eso vive en `taller_cultura.infrastructure`). Solo
coordina: valida el archivo, llama al lector, guarda con el repositorio,
pide al dominio que calcule, entrega al exportador.
"""

from .use_cases import (
    ArchivoNoProcesable,
    CalcularReporteTaller,
    CompararSesiones,
    ExportarPlantillaTaller,
    ExportarReporteComparativo,
    ExportarReporteTaller,
    ImportarSesionTaller,
    ListarSesiones,
    ReporteComparativo,
    ReporteTaller,
    SesionNoEncontrada,
    ValidarArchivoTaller,
)
from .validacion import Hallazgo, ResultadoValidacion, Severidad

__all__ = [
    "ArchivoNoProcesable",
    "CalcularReporteTaller",
    "CompararSesiones",
    "ExportarPlantillaTaller",
    "ExportarReporteComparativo",
    "ExportarReporteTaller",
    "Hallazgo",
    "ImportarSesionTaller",
    "ListarSesiones",
    "ReporteComparativo",
    "ReporteTaller",
    "ResultadoValidacion",
    "SesionNoEncontrada",
    "Severidad",
    "ValidarArchivoTaller",
]
