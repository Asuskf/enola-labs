"""Adaptadores concretos: Excel (lector/escritor) y SQLite (repositorio)."""

from .excel_reader import LectorTallerExcel
from .excel_writer import ExportadorReporteExcel
from .html_writer import ExportadorReporteHTML
from .plantilla_writer import ExportadorPlantillaExcel
from .sqlite_repo import RepositorioTallerSQLite

__all__ = [
    "LectorTallerExcel",
    "ExportadorReporteExcel",
    "ExportadorReporteHTML",
    "ExportadorPlantillaExcel",
    "RepositorioTallerSQLite",
]
