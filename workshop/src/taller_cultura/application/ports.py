"""Puertos: contratos que separan el dominio/aplicación de la infraestructura.

Arquitectura hexagonal:
- Puertos de ENTRADA (driving/primary): los casos de uso en `use_cases.py`
  son en sí el puerto de entrada; la CLI/infra los invoca.
- Puertos de SALIDA (driven/secondary): interfaces que el dominio necesita
  para persistir o leer datos. Los adaptadores (sqlite, pandas/excel) los
  implementan en `infrastructure/`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    Calificador,
    Empresa,
)


class LectorTaller(ABC):
    """Puerto de salida: lee el taller desde una fuente externa (p.ej. Excel)."""

    @abstractmethod
    def leer_empresas(self) -> list[Empresa]:
        ...

    @abstractmethod
    def leer_calificadores(self) -> list[Calificador]:
        ...

    @abstractmethod
    def leer_aspectos(self) -> list[Aspecto]:
        ...

    @abstractmethod
    def leer_calificaciones(self, aspectos: list[Aspecto]) -> list[Calificacion]:
        ...


class RepositorioTaller(ABC):
    """Puerto de salida: persiste y consulta el taller (p.ej. sqlite)."""

    @abstractmethod
    def guardar_empresas(self, empresas: list[Empresa]) -> dict[str, int]:
        """Persiste empresas y devuelve un mapa nombre -> id asignado."""

    @abstractmethod
    def guardar_calificadores(self, calificadores: list[Calificador]) -> None:
        ...

    @abstractmethod
    def guardar_aspectos(self, aspectos: list[Aspecto]) -> dict[int, int]:
        """Persiste aspectos y devuelve un mapa índice_original -> id asignado."""

    @abstractmethod
    def guardar_calificaciones(self, calificaciones: list[Calificacion]) -> None:
        ...

    @abstractmethod
    def listar_aspectos(self) -> list[Aspecto]:
        ...

    @abstractmethod
    def listar_calificaciones(self) -> list[Calificacion]:
        ...

    @abstractmethod
    def listar_calificadores(self) -> list[Calificador]:
        ...

    @abstractmethod
    def listar_empresas(self) -> list[Empresa]:
        ...


class ExportadorReporte(ABC):
    """Puerto de salida: exporta un `ReporteTaller` a un destino (Excel, HTML, ...)."""

    @abstractmethod
    def exportar_reporte(self, reporte, ruta_destino: str) -> None:
        ...


class ExportadorPlantilla(ABC):
    """Puerto de salida: produce el archivo que se reparte a los participantes.

    Solo la hoja de trabajo del taller; el material derivado va al reporte.
    """

    @abstractmethod
    def exportar_plantilla(self, ruta_excel_origen: str, ruta_destino: str) -> None:
        ...
