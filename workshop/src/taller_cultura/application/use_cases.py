"""Casos de uso (puertos de entrada) del taller de diagnóstico cultural.

Cada caso de uso es una clase pequeña con un único método `ejecutar`, que
recibe sus dependencias (puertos de salida) por el constructor. Así la
composición concreta (qué adaptador usar) queda fuera de aquí, en
`infrastructure` / el punto de entrada `main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from taller_cultura.domain.model import Aspecto, Calificacion, Calificador, Empresa
from taller_cultura.domain.services import (
    CalculadoraResumen,
    ResumenCategoria,
    ResumenTaller,
)

from .ports import ExportadorReporte, LectorTaller, RepositorioTaller


@dataclass(frozen=True, slots=True)
class ResultadoImportacion:
    empresas: int
    calificadores: int
    aspectos: int
    calificaciones: int


class ImportarTallerDesdeExcel:
    """Lee el Excel original y persiste su contenido en el repositorio."""

    def __init__(self, lector: LectorTaller, repositorio: RepositorioTaller) -> None:
        self._lector = lector
        self._repositorio = repositorio

    def ejecutar(self) -> ResultadoImportacion:
        empresas: list[Empresa] = self._lector.leer_empresas()
        calificadores: list[Calificador] = self._lector.leer_calificadores()
        aspectos: list[Aspecto] = self._lector.leer_aspectos()
        calificaciones: list[Calificacion] = self._lector.leer_calificaciones(aspectos)

        self._repositorio.guardar_empresas(empresas)
        self._repositorio.guardar_calificadores(calificadores)
        mapa_ids_aspectos = self._repositorio.guardar_aspectos(aspectos)

        calificaciones_con_id_final = self._remapear_aspecto_ids(
            calificaciones, aspectos, mapa_ids_aspectos
        )
        self._repositorio.guardar_calificaciones(calificaciones_con_id_final)

        return ResultadoImportacion(
            empresas=len(empresas),
            calificadores=len(calificadores),
            aspectos=len(aspectos),
            calificaciones=len(calificaciones_con_id_final),
        )

    @staticmethod
    def _remapear_aspecto_ids(
        calificaciones: list[Calificacion],
        aspectos: list[Aspecto],
        mapa_ids: dict[int, int],
    ) -> list[Calificacion]:
        """Traduce el id temporal (posición) del aspecto al id real asignado
        por el repositorio, ya que el lector no conoce el autoincrement de
        la base de datos.
        """
        if not mapa_ids:
            return calificaciones
        return [
            Calificacion(
                aspecto_id=mapa_ids.get(c.aspecto_id, c.aspecto_id),
                calificador_codigo=c.calificador_codigo,
                momento=c.momento,
                valoracion=c.valoracion,
                es_consenso=c.es_consenso,
            )
            for c in calificaciones
        ]


class CalcularResumenTaller:
    """Calcula el resumen agregado del taller a partir de lo persistido."""

    def __init__(
        self,
        repositorio: RepositorioTaller,
        calculadora: CalculadoraResumen | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._calculadora = calculadora or CalculadoraResumen()

    def ejecutar(self, *, solo_consenso: bool = False) -> ResumenTaller:
        aspectos = self._repositorio.listar_aspectos()
        calificaciones = self._repositorio.listar_calificaciones()
        return self._calculadora.calcular(aspectos, calificaciones, solo_consenso=solo_consenso)


@dataclass(frozen=True, slots=True)
class ReporteTaller:
    """Todo lo que un adaptador de reporte (Excel, HTML, ...) necesita para
    producir su salida: título/contexto, el resumen agregado y el desglose
    por categoría.
    """

    titulo: str
    resumen: ResumenTaller
    detalle_categoria: tuple[ResumenCategoria, ...]
    calificadores_participantes: int


class CalcularReporteTaller:
    """Calcula el resumen agregado Y el desglose por categoría, listos para
    entregarle a un `ExportadorReporte`.
    """

    def __init__(
        self,
        repositorio: RepositorioTaller,
        calculadora: CalculadoraResumen | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._calculadora = calculadora or CalculadoraResumen()

    def ejecutar(self, *, titulo: str | None = None, solo_consenso: bool = False) -> ReporteTaller:
        aspectos = self._repositorio.listar_aspectos()
        calificaciones = self._repositorio.listar_calificaciones()

        if titulo is None:
            empresas = self._repositorio.listar_empresas()
            titulo = empresas[0].nombre if empresas else "Taller de cultura organizacional"

        resumen = self._calculadora.calcular(aspectos, calificaciones, solo_consenso=solo_consenso)
        detalle_categoria = self._calculadora.calcular_detalle_por_categoria(aspectos, calificaciones)
        calificadores_participantes = len(
            {c.calificador_codigo for c in calificaciones if not c.es_consenso}
        )
        return ReporteTaller(
            titulo=titulo,
            resumen=resumen,
            detalle_categoria=detalle_categoria,
            calificadores_participantes=calificadores_participantes,
        )


class ExportarReporteTaller:
    """Exporta un `ReporteTaller` a un destino externo (Excel, HTML, ...)."""

    def __init__(self, exportador: ExportadorReporte) -> None:
        self._exportador = exportador

    def ejecutar(self, reporte: ReporteTaller, ruta_destino: str) -> None:
        self._exportador.exportar_reporte(reporte, ruta_destino)
