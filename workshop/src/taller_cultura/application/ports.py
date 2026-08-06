"""Puertos: contratos que separan el dominio/aplicación de la infraestructura.

Arquitectura hexagonal:
- Puertos de ENTRADA (driving/primary): los casos de uso en `use_cases.py`
  son en sí el puerto de entrada; la CLI y la GUI los invocan.
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
    SesionTaller,
)

from .validacion import ResultadoValidacion


class LectorTaller(ABC):
    """Puerto de salida: lee el taller desde una fuente externa (p.ej. Excel)."""

    @abstractmethod
    def validar(self) -> ResultadoValidacion:
        """Revisa el archivo y reporta problemas ANTES de procesarlo."""

    @abstractmethod
    def leer_nombre_empresa(self) -> str | None:
        """Nombre de la empresa si el archivo lo trae; `None` si no."""

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
    """Puerto de salida: persiste y consulta las sesiones del taller."""

    # -- sesiones -------------------------------------------------------

    @abstractmethod
    def crear_sesion(self, sesion: SesionTaller) -> SesionTaller:
        """Guarda una sesión nueva y devuelve la versión con su id asignado."""

    @abstractmethod
    def listar_sesiones(self, empresa: str | None = None) -> list[SesionTaller]:
        """Sesiones registradas, opcionalmente filtradas por empresa."""

    @abstractmethod
    def obtener_sesion(self, sesion_id: int) -> SesionTaller | None:
        ...

    @abstractmethod
    def siguiente_version(self, empresa: str) -> int:
        """Qué número de versión le toca a la próxima sesión de esa empresa."""

    @abstractmethod
    def eliminar_sesion(self, sesion_id: int) -> None:
        ...

    # -- contenido de una sesión -----------------------------------------

    @abstractmethod
    def guardar_calificadores(self, sesion_id: int, calificadores: list[Calificador]) -> None:
        ...

    @abstractmethod
    def guardar_aspectos(self, sesion_id: int, aspectos: list[Aspecto]) -> dict[int, int]:
        """Persiste aspectos y devuelve un mapa índice_original -> id asignado."""

    @abstractmethod
    def guardar_calificaciones(self, sesion_id: int, calificaciones: list[Calificacion]) -> None:
        ...

    @abstractmethod
    def listar_aspectos(self, sesion_id: int) -> list[Aspecto]:
        ...

    @abstractmethod
    def listar_calificaciones(self, sesion_id: int) -> list[Calificacion]:
        ...

    @abstractmethod
    def listar_calificadores(self, sesion_id: int) -> list[Calificador]:
        ...


class ExportadorReporte(ABC):
    """Puerto de salida: exporta un `ReporteTaller` a un destino (Excel, HTML, ...)."""

    @abstractmethod
    def exportar_reporte(self, reporte, ruta_destino: str) -> None:
        ...


class ExportadorComparativo(ABC):
    """Puerto de salida: exporta el contraste entre dos sesiones del taller."""

    @abstractmethod
    def exportar_comparativo(self, comparativo, ruta_destino: str) -> None:
        ...


class ExportadorPlantilla(ABC):
    """Puerto de salida: produce el archivo que se reparte a los participantes.

    Solo la hoja de trabajo del taller; el material derivado va al reporte.
    """

    @abstractmethod
    def exportar_plantilla(self, ruta_excel_origen: str, ruta_destino: str) -> None:
        ...
