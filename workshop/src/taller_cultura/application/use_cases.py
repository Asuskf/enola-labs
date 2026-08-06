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
    DiagnosticoTaller,
    ResumenCategoria,
    ResumenTaller,
)

from .ports import (
    ExportadorPlantilla,
    ExportadorReporte,
    LectorTaller,
    RepositorioTaller,
)


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
    producir su salida: título/contexto, el resumen agregado, el desglose
    por categoría y el diagnóstico de cobertura de los datos.
    """

    titulo: str
    resumen: ResumenTaller
    detalle_categoria: tuple[ResumenCategoria, ...]
    calificadores_participantes: int
    base_calculo: str
    diagnostico: DiagnosticoTaller


class CalcularReporteTaller:
    """Calcula el resumen agregado Y el desglose por categoría, listos para
    entregarle a un `ExportadorReporte`.

    Por defecto usa **solo las filas de CONSENSO**, que es la unidad de
    análisis del taller: el libro original agrega exactamente así (sus
    hojas FINAL y CULTURAS cuentan una sola fila —la de consenso— por
    ítem). Pasar `solo_consenso=False` incluye además las calificaciones
    individuales de cada participante.
    """

    def __init__(
        self,
        repositorio: RepositorioTaller,
        calculadora: CalculadoraResumen | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._calculadora = calculadora or CalculadoraResumen()

    def ejecutar(self, *, titulo: str | None = None, solo_consenso: bool = True) -> ReporteTaller:
        aspectos = self._repositorio.listar_aspectos()
        calificaciones = self._repositorio.listar_calificaciones()

        if titulo is None:
            empresas = self._repositorio.listar_empresas()
            titulo = empresas[0].nombre if empresas else "Taller de cultura organizacional"

        consideradas = (
            [c for c in calificaciones if c.es_consenso] if solo_consenso else calificaciones
        )

        resumen = self._calculadora.calcular(aspectos, calificaciones, solo_consenso=solo_consenso)
        detalle_categoria = self._calculadora.calcular_detalle_por_categoria(aspectos, consideradas)
        calificadores_participantes = len(
            {c.calificador_codigo for c in calificaciones if not c.es_consenso}
        )
        return ReporteTaller(
            titulo=titulo,
            resumen=resumen,
            detalle_categoria=detalle_categoria,
            calificadores_participantes=calificadores_participantes,
            base_calculo="Consenso del grupo" if solo_consenso else "Todas las respuestas",
            diagnostico=self._calculadora.diagnosticar(aspectos, consideradas),
        )


class ExportarReporteTaller:
    """Exporta un `ReporteTaller` a un destino externo (Excel, HTML, ...)."""

    def __init__(self, exportador: ExportadorReporte) -> None:
        self._exportador = exportador

    def ejecutar(self, reporte: ReporteTaller, ruta_destino: str) -> None:
        self._exportador.exportar_reporte(reporte, ruta_destino)


class ExportarPlantillaTaller:
    """Produce el archivo que efectivamente se reparte a los participantes.

    Del libro original solo se envía la hoja TALLER (más el roster de
    CALIFICADORES, al que TALLER hace referencia). Todo lo demás —RESUMEN,
    PRESENTACION, FINAL, CULTURAS— es material derivado y su contenido va
    en el reporte que genera esta aplicación, no en el archivo que se
    reparte.
    """

    def __init__(self, exportador: ExportadorPlantilla) -> None:
        self._exportador = exportador

    def ejecutar(self, ruta_excel_origen: str, ruta_destino: str) -> None:
        self._exportador.exportar_plantilla(ruta_excel_origen, ruta_destino)
