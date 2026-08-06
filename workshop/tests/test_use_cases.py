"""Tests de la capa de aplicación con dobles de prueba en memoria.

Verifican el cableado de los casos de uso sin tocar Excel ni SQLite: es
justamente lo que permite la arquitectura hexagonal.
"""

from datetime import date

import pytest

from taller_cultura.application.ports import RepositorioTaller
from taller_cultura.application.use_cases import (
    CalcularReporteTaller,
    CompararSesiones,
    SesionNoEncontrada,
)
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    CategoriaAspecto,
    Momento,
    SesionTaller,
    TipoCultura,
    Valoracion,
)


class RepositorioEnMemoria(RepositorioTaller):
    """Doble de prueba: implementa el puerto sin base de datos."""

    def __init__(self) -> None:
        self._sesiones: dict[int, SesionTaller] = {}
        self._aspectos: dict[int, list[Aspecto]] = {}
        self._calificaciones: dict[int, list[Calificacion]] = {}
        self._siguiente_id = 1

    # -- ayuda para armar escenarios en los tests -----------------------

    def sembrar(self, empresa, fecha, aspectos, calificaciones, version=1) -> SesionTaller:
        sesion = self.crear_sesion(
            SesionTaller(id=None, empresa=empresa, fecha_taller=fecha, numero_version=version)
        )
        self._aspectos[sesion.id] = list(aspectos)
        self._calificaciones[sesion.id] = list(calificaciones)
        return sesion

    # -- sesiones --------------------------------------------------------

    def crear_sesion(self, sesion):
        creada = SesionTaller(
            id=self._siguiente_id,
            empresa=sesion.empresa,
            fecha_taller=sesion.fecha_taller,
            numero_version=sesion.numero_version,
            archivo_origen=sesion.archivo_origen,
        )
        self._sesiones[creada.id] = creada
        self._aspectos.setdefault(creada.id, [])
        self._calificaciones.setdefault(creada.id, [])
        self._siguiente_id += 1
        return creada

    def listar_sesiones(self, empresa=None):
        return [s for s in self._sesiones.values() if empresa is None or s.empresa == empresa]

    def obtener_sesion(self, sesion_id):
        return self._sesiones.get(sesion_id)

    def siguiente_version(self, empresa):
        previas = [s.numero_version for s in self._sesiones.values() if s.empresa == empresa]
        return max(previas, default=0) + 1

    def eliminar_sesion(self, sesion_id):
        self._sesiones.pop(sesion_id, None)

    # -- contenido --------------------------------------------------------

    def guardar_calificadores(self, sesion_id, calificadores):
        return None

    def guardar_aspectos(self, sesion_id, aspectos):
        self._aspectos[sesion_id] = list(aspectos)
        return {i: i for i in range(len(aspectos))}

    def guardar_calificaciones(self, sesion_id, calificaciones):
        self._calificaciones[sesion_id] = list(calificaciones)

    def listar_aspectos(self, sesion_id):
        return list(self._aspectos.get(sesion_id, []))

    def listar_calificaciones(self, sesion_id):
        return list(self._calificaciones.get(sesion_id, []))

    def listar_calificadores(self, sesion_id):
        return []


def _aspecto(id_, tipo_cultura=TipoCultura.LOGRO):
    return Aspecto(
        id=id_,
        tipo_cultura=tipo_cultura,
        categoria=CategoriaAspecto.COMPORTAMIENTOS,
        orden=id_,
        texto=f"ítem {id_}",
    )


@pytest.fixture
def repo() -> RepositorioEnMemoria:
    return RepositorioEnMemoria()


# -- reporte de una sesión ----------------------------------------------------


def test_por_defecto_calcula_solo_con_el_consenso(repo):
    """El consenso es la unidad de análisis: así agrega el libro original."""
    sesion = repo.sembrar(
        "ACME",
        date(2025, 1, 10),
        [_aspecto(1)],
        [
            Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
            Calificacion(1, 3, Momento.PASADO, Valoracion.BAJO),
            Calificacion(1, 4, Momento.PASADO, Valoracion.BAJO),
        ],
    )

    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id)

    pasado = reporte.resumen.para(TipoCultura.LOGRO, Momento.PASADO)
    assert pasado.total == 1
    assert pasado.promedio_ponderado == 2.0
    assert reporte.base_calculo == "Consenso del grupo"


def test_puede_incluir_las_calificaciones_individuales(repo):
    sesion = repo.sembrar(
        "ACME",
        date(2025, 1, 10),
        [_aspecto(1)],
        [
            Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
            Calificacion(1, 3, Momento.PASADO, Valoracion.BAJO),
        ],
    )

    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id, solo_consenso=False)

    assert reporte.resumen.para(TipoCultura.LOGRO, Momento.PASADO).total == 2
    assert reporte.base_calculo == "Todas las respuestas"


def test_el_diagnostico_refleja_la_cobertura_real(repo):
    sesion = repo.sembrar(
        "ACME",
        date(2025, 1, 10),
        [_aspecto(1), _aspecto(2), _aspecto(3), _aspecto(4)],
        [
            Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
            Calificacion(2, 0, Momento.PASADO, Valoracion.MEDIO, es_consenso=True),
            Calificacion(3, 5, Momento.PASADO, Valoracion.BAJO),
        ],
    )

    diagnostico = CalcularReporteTaller(repo).ejecutar(
        sesion.id, solo_consenso=False
    ).diagnostico

    assert diagnostico.total_aspectos == 4
    assert diagnostico.aspectos_calificados == 3
    assert diagnostico.aspectos_sin_calificar == 1
    assert diagnostico.porcentaje_cobertura == 75.0
    assert diagnostico.respuestas_consenso == 2
    assert diagnostico.respuestas_individuales == 1


def test_el_detalle_por_categoria_respeta_la_base_de_calculo(repo):
    """Con `solo_consenso` el desglose no debe colar respuestas individuales."""
    sesion = repo.sembrar(
        "ACME",
        date(2025, 1, 10),
        [_aspecto(1)],
        [
            Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
            Calificacion(1, 7, Momento.PASADO, Valoracion.BAJO),
        ],
    )

    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id, solo_consenso=True)

    assert sum(d.total for d in reporte.detalle_categoria) == 1


def test_el_reporte_lleva_los_datos_de_la_sesion(repo):
    sesion = repo.sembrar("ACME", date(2026, 3, 14), [_aspecto(1)], [])

    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id)

    assert reporte.titulo == "ACME"
    assert reporte.sesion.fecha_taller == date(2026, 3, 14)


def test_falla_claro_si_la_sesion_no_existe(repo):
    with pytest.raises(SesionNoEncontrada):
        CalcularReporteTaller(repo).ejecutar(999)


# -- versionado y comparación --------------------------------------------------


def test_la_version_se_numera_por_empresa(repo):
    repo.sembrar("ACME", date(2025, 1, 1), [], [], version=1)
    repo.sembrar("ACME", date(2026, 1, 1), [], [], version=2)

    assert repo.siguiente_version("ACME") == 3
    assert repo.siguiente_version("OTRA") == 1


def test_comparar_dos_sesiones_calcula_la_variacion(repo):
    """Una cultura que pasa de todo-bajo a todo-alto sube de 0 a 2."""
    antes = repo.sembrar(
        "ACME",
        date(2025, 1, 1),
        [_aspecto(1)],
        [Calificacion(1, 0, Momento.PASADO, Valoracion.BAJO, es_consenso=True)],
    )
    ahora = repo.sembrar(
        "ACME",
        date(2026, 1, 1),
        [_aspecto(1)],
        [Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True)],
        version=2,
    )

    comparativo = CompararSesiones(repo).ejecutar(antes.id, ahora.id)

    logro = comparativo.comparacion.para(TipoCultura.LOGRO)
    assert logro.promedio_antes == 0.0
    assert logro.promedio_ahora == 2.0
    assert logro.variacion == 2.0
    assert logro.mejoro
    assert comparativo.comparacion.mayor_avance.tipo_cultura is TipoCultura.LOGRO
    assert comparativo.comparacion.mayor_retroceso is None


def test_una_cultura_sin_datos_en_una_sesion_no_es_comparable(repo):
    antes = repo.sembrar(
        "ACME",
        date(2025, 1, 1),
        [_aspecto(1)],
        [Calificacion(1, 0, Momento.PASADO, Valoracion.MEDIO, es_consenso=True)],
    )
    ahora = repo.sembrar("ACME", date(2026, 1, 1), [_aspecto(1)], [], version=2)

    comparativo = CompararSesiones(repo).ejecutar(antes.id, ahora.id)

    logro = comparativo.comparacion.para(TipoCultura.LOGRO)
    assert not logro.es_comparable
    assert logro.variacion is None
    assert comparativo.comparacion.comparables == ()


def test_la_variacion_porcentual_evita_dividir_por_cero(repo):
    """Si antes era 0, el cambio relativo no está definido (no es infinito)."""
    antes = repo.sembrar(
        "ACME",
        date(2025, 1, 1),
        [_aspecto(1)],
        [Calificacion(1, 0, Momento.PASADO, Valoracion.BAJO, es_consenso=True)],
    )
    ahora = repo.sembrar(
        "ACME",
        date(2026, 1, 1),
        [_aspecto(1)],
        [Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True)],
        version=2,
    )

    logro = CompararSesiones(repo).ejecutar(antes.id, ahora.id).comparacion.para(TipoCultura.LOGRO)

    assert logro.variacion == 2.0
    assert logro.variacion_porcentual is None
