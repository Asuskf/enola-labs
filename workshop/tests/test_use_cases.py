"""Tests de la capa de aplicación con dobles de prueba en memoria.

Verifican el cableado de los casos de uso sin tocar Excel ni SQLite: es
justamente lo que permite la arquitectura hexagonal.
"""

from taller_cultura.application.ports import RepositorioTaller
from taller_cultura.application.use_cases import CalcularReporteTaller
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    CategoriaAspecto,
    Empresa,
    Momento,
    TipoCultura,
    Valoracion,
)


class RepositorioEnMemoria(RepositorioTaller):
    """Doble de prueba: implementa el puerto sin base de datos."""

    def __init__(self, aspectos, calificaciones, empresas=()):
        self._aspectos = list(aspectos)
        self._calificaciones = list(calificaciones)
        self._empresas = list(empresas)

    def guardar_empresas(self, empresas):
        return {}

    def guardar_calificadores(self, calificadores):
        return None

    def guardar_aspectos(self, aspectos):
        return {}

    def guardar_calificaciones(self, calificaciones):
        return None

    def listar_aspectos(self):
        return list(self._aspectos)

    def listar_calificaciones(self):
        return list(self._calificaciones)

    def listar_calificadores(self):
        return []

    def listar_empresas(self):
        return list(self._empresas)


def _aspecto(id_, tipo_cultura=TipoCultura.LOGRO):
    return Aspecto(
        id=id_,
        tipo_cultura=tipo_cultura,
        categoria=CategoriaAspecto.COMPORTAMIENTOS,
        orden=id_,
        texto=f"ítem {id_}",
    )


def test_por_defecto_calcula_solo_con_el_consenso():
    """El consenso es la unidad de análisis: así agrega el libro original."""
    aspectos = [_aspecto(1)]
    calificaciones = [
        Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
        Calificacion(1, 3, Momento.PASADO, Valoracion.BAJO, es_consenso=False),
        Calificacion(1, 4, Momento.PASADO, Valoracion.BAJO, es_consenso=False),
    ]
    repo = RepositorioEnMemoria(aspectos, calificaciones)

    reporte = CalcularReporteTaller(repo).ejecutar()

    pasado = reporte.resumen.para(TipoCultura.LOGRO, Momento.PASADO)
    assert pasado.total == 1
    assert pasado.promedio_ponderado == 2.0
    assert reporte.base_calculo == "Consenso del grupo"


def test_puede_incluir_las_calificaciones_individuales():
    aspectos = [_aspecto(1)]
    calificaciones = [
        Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
        Calificacion(1, 3, Momento.PASADO, Valoracion.BAJO, es_consenso=False),
    ]
    repo = RepositorioEnMemoria(aspectos, calificaciones)

    reporte = CalcularReporteTaller(repo).ejecutar(solo_consenso=False)

    assert reporte.resumen.para(TipoCultura.LOGRO, Momento.PASADO).total == 2
    assert reporte.base_calculo == "Todas las respuestas"


def test_el_diagnostico_refleja_la_cobertura_real():
    aspectos = [_aspecto(1), _aspecto(2), _aspecto(3), _aspecto(4)]
    calificaciones = [
        Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
        Calificacion(2, 0, Momento.PASADO, Valoracion.MEDIO, es_consenso=True),
        Calificacion(3, 5, Momento.PASADO, Valoracion.BAJO, es_consenso=False),
    ]
    repo = RepositorioEnMemoria(aspectos, calificaciones)

    diagnostico = CalcularReporteTaller(repo).ejecutar(solo_consenso=False).diagnostico

    assert diagnostico.total_aspectos == 4
    assert diagnostico.aspectos_calificados == 3
    assert diagnostico.aspectos_sin_calificar == 1
    assert diagnostico.porcentaje_cobertura == 75.0
    assert diagnostico.respuestas_consenso == 2
    assert diagnostico.respuestas_individuales == 1


def test_el_detalle_por_categoria_respeta_la_base_de_calculo():
    """Con `solo_consenso` el desglose no debe colar respuestas individuales."""
    aspectos = [_aspecto(1)]
    calificaciones = [
        Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
        Calificacion(1, 7, Momento.PASADO, Valoracion.BAJO, es_consenso=False),
    ]
    repo = RepositorioEnMemoria(aspectos, calificaciones)

    reporte = CalcularReporteTaller(repo).ejecutar(solo_consenso=True)

    assert sum(d.total for d in reporte.detalle_categoria) == 1


def test_usa_el_nombre_de_la_empresa_como_titulo():
    repo = RepositorioEnMemoria([], [], empresas=[Empresa(id=1, nombre="ACME")])

    assert CalcularReporteTaller(repo).ejecutar().titulo == "ACME"
