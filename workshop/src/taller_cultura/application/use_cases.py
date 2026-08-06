"""Casos de uso (puertos de entrada) del taller de diagnóstico cultural.

Cada caso de uso recibe sus dependencias (puertos de salida) por el
constructor, así la composición concreta —qué adaptador usar— queda fuera
de aquí, en el punto de entrada (`main.py`) o en la GUI.

El flujo completo es:

    ValidarArchivoTaller   ¿el archivo sirve?
    ImportarSesionTaller   registrar la sesión (empresa + fecha) y cargarla
    CalcularReporteTaller  agregar los resultados de una sesión
    CompararSesiones       contrastar dos sesiones de la misma empresa
    ExportarReporteTaller / ExportarReporteComparativo / ExportarPlantillaTaller
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    Calificador,
    SesionTaller,
)
from taller_cultura.domain.services import (
    CalculadoraResumen,
    ComparacionCategoria,
    ComparacionTaller,
    ComparadorSesiones,
    DiagnosticoTaller,
    Momento,
    ResumenCategoria,
    ResumenTaller,
)

from .ports import (
    ExportadorComparativo,
    ExportadorPlantilla,
    ExportadorReporte,
    LectorTaller,
    RepositorioTaller,
)
from .validacion import ResultadoValidacion


class SesionNoEncontrada(Exception):
    """Se pidió trabajar con una sesión que no existe en el repositorio."""


class ArchivoNoProcesable(Exception):
    """El archivo no pasó la validación previa."""

    def __init__(self, resultado: ResultadoValidacion) -> None:
        super().__init__(resultado.resumen)
        self.resultado = resultado


# -- validación ------------------------------------------------------------


class ValidarArchivoTaller:
    """Revisa el archivo antes de procesarlo y reporta lo que encuentre."""

    def __init__(self, lector: LectorTaller) -> None:
        self._lector = lector

    def ejecutar(self) -> ResultadoValidacion:
        return self._lector.validar()


# -- importación -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResultadoImportacion:
    sesion: SesionTaller
    calificadores: int
    aspectos: int
    calificaciones: int
    validacion: ResultadoValidacion


class ImportarSesionTaller:
    """Registra una sesión (empresa + fecha) y carga en ella el archivo.

    Si la empresa ya tiene sesiones previas, la nueva recibe automáticamente
    el siguiente número de versión, que es lo que después permite comparar
    "antes y ahora".
    """

    def __init__(self, lector: LectorTaller, repositorio: RepositorioTaller) -> None:
        self._lector = lector
        self._repositorio = repositorio

    def ejecutar(
        self,
        *,
        empresa: str,
        fecha_taller: date,
        archivo_origen: str = "",
        omitir_validacion: bool = False,
    ) -> ResultadoImportacion:
        validacion = self._lector.validar()
        if not omitir_validacion and not validacion.es_procesable:
            raise ArchivoNoProcesable(validacion)

        empresa = empresa.strip() or "Empresa sin nombre"
        sesion = self._repositorio.crear_sesion(
            SesionTaller(
                id=None,
                empresa=empresa,
                fecha_taller=fecha_taller,
                numero_version=self._repositorio.siguiente_version(empresa),
                archivo_origen=archivo_origen,
            )
        )

        calificadores: list[Calificador] = self._lector.leer_calificadores()
        aspectos: list[Aspecto] = self._lector.leer_aspectos()
        calificaciones: list[Calificacion] = self._lector.leer_calificaciones(aspectos)

        self._repositorio.guardar_calificadores(sesion.id, calificadores)
        mapa_ids = self._repositorio.guardar_aspectos(sesion.id, aspectos)
        calificaciones = self._remapear_aspecto_ids(calificaciones, mapa_ids)
        self._repositorio.guardar_calificaciones(sesion.id, calificaciones)

        return ResultadoImportacion(
            sesion=sesion,
            calificadores=len(calificadores),
            aspectos=len(aspectos),
            calificaciones=len(calificaciones),
            validacion=validacion,
        )

    @staticmethod
    def _remapear_aspecto_ids(
        calificaciones: list[Calificacion], mapa_ids: dict[int, int]
    ) -> list[Calificacion]:
        """Traduce el id temporal (posición) del aspecto al id real asignado
        por el repositorio, que el lector no puede conocer.
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


# -- consulta de sesiones ---------------------------------------------------


class ListarSesiones:
    """Sesiones registradas, para elegir cuál reportar o comparar."""

    def __init__(self, repositorio: RepositorioTaller) -> None:
        self._repositorio = repositorio

    def ejecutar(self, empresa: str | None = None) -> list[SesionTaller]:
        return self._repositorio.listar_sesiones(empresa)


# -- reporte de una sesión ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReporteTaller:
    """Todo lo que un adaptador de reporte necesita para producir su salida."""

    sesion: SesionTaller
    resumen: ResumenTaller
    detalle_categoria: tuple[ResumenCategoria, ...]
    calificadores_participantes: int
    base_calculo: str
    diagnostico: DiagnosticoTaller

    @property
    def titulo(self) -> str:
        return self.sesion.empresa


class CalcularReporteTaller:
    """Agrega los resultados de una sesión.

    Por defecto usa **solo las filas de CONSENSO**, que es la unidad de
    análisis del taller: el libro original agrega exactamente así (sus
    hojas FINAL y CULTURAS cuentan una sola fila —la de consenso— por
    ítem). Con `solo_consenso=False` se incluyen además las calificaciones
    individuales de cada participante.
    """

    def __init__(
        self,
        repositorio: RepositorioTaller,
        calculadora: CalculadoraResumen | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._calculadora = calculadora or CalculadoraResumen()

    def ejecutar(self, sesion_id: int, *, solo_consenso: bool = True) -> ReporteTaller:
        sesion = self._repositorio.obtener_sesion(sesion_id)
        if sesion is None:
            raise SesionNoEncontrada(f"No existe la sesión {sesion_id}")

        aspectos = self._repositorio.listar_aspectos(sesion_id)
        calificaciones = self._repositorio.listar_calificaciones(sesion_id)
        consideradas = (
            [c for c in calificaciones if c.es_consenso] if solo_consenso else calificaciones
        )

        return ReporteTaller(
            sesion=sesion,
            resumen=self._calculadora.calcular(
                aspectos, calificaciones, solo_consenso=solo_consenso
            ),
            detalle_categoria=self._calculadora.calcular_detalle_por_categoria(
                aspectos, consideradas
            ),
            calificadores_participantes=len(
                {c.calificador_codigo for c in calificaciones if not c.es_consenso}
            ),
            base_calculo="Consenso del grupo" if solo_consenso else "Todas las respuestas",
            diagnostico=self._calculadora.diagnosticar(aspectos, consideradas),
        )


# -- comparación entre sesiones ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ReporteComparativo:
    """El contraste entre dos sesiones, listo para exportar."""

    antes: ReporteTaller
    ahora: ReporteTaller
    comparacion: ComparacionTaller
    comparacion_categoria: tuple[ComparacionCategoria, ...]
    momento: Momento

    @property
    def empresa(self) -> str:
        return self.ahora.sesion.empresa


class CompararSesiones:
    """Contrasta dos sesiones del taller: la anterior contra la actual."""

    def __init__(
        self,
        repositorio: RepositorioTaller,
        comparador: ComparadorSesiones | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._calcular = CalcularReporteTaller(repositorio)
        self._comparador = comparador or ComparadorSesiones()

    def ejecutar(
        self,
        sesion_antes_id: int,
        sesion_ahora_id: int,
        *,
        solo_consenso: bool = True,
        momento: Momento = Momento.PASADO,
    ) -> ReporteComparativo:
        antes = self._calcular.ejecutar(sesion_antes_id, solo_consenso=solo_consenso)
        ahora = self._calcular.ejecutar(sesion_ahora_id, solo_consenso=solo_consenso)
        return ReporteComparativo(
            antes=antes,
            ahora=ahora,
            comparacion=self._comparador.comparar(antes.resumen, ahora.resumen, momento),
            comparacion_categoria=self._comparador.comparar_por_categoria(
                antes.detalle_categoria, ahora.detalle_categoria
            ),
            momento=momento,
        )


# -- exportación --------------------------------------------------------------


class ExportarReporteTaller:
    """Exporta un `ReporteTaller` a un destino externo (Excel, HTML, ...)."""

    def __init__(self, exportador: ExportadorReporte) -> None:
        self._exportador = exportador

    def ejecutar(self, reporte: ReporteTaller, ruta_destino: str) -> None:
        self._exportador.exportar_reporte(reporte, ruta_destino)


class ExportarReporteComparativo:
    """Exporta el reporte de "antes y ahora" entre dos sesiones."""

    def __init__(self, exportador: ExportadorComparativo) -> None:
        self._exportador = exportador

    def ejecutar(self, comparativo: ReporteComparativo, ruta_destino: str) -> None:
        self._exportador.exportar_comparativo(comparativo, ruta_destino)


class ExportarPlantillaTaller:
    """Produce el archivo que efectivamente se reparte a los participantes.

    Del libro original solo se envía la hoja TALLER (más el roster de
    CALIFICADORES, al que TALLER hace referencia). Todo lo demás —RESUMEN,
    PRESENTACION, FINAL, CULTURAS— es material derivado y su contenido va
    en el reporte que genera esta aplicación.
    """

    def __init__(self, exportador: ExportadorPlantilla) -> None:
        self._exportador = exportador

    def ejecutar(self, ruta_excel_origen: str, ruta_destino: str) -> None:
        self._exportador.exportar_plantilla(ruta_excel_origen, ruta_destino)
