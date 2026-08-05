"""Tests del dominio puro: CalculadoraResumen y ResumenTaller.

No tocan Excel ni SQLite: construyen entidades a mano para verificar la
lógica de agregación y ponderación.
"""

from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    CategoriaAspecto,
    Momento,
    TipoCultura,
    Valoracion,
)
from taller_cultura.domain.services import CalculadoraResumen


def _aspecto(id_, tipo_cultura):
    return Aspecto(
        id=id_,
        tipo_cultura=tipo_cultura,
        categoria=CategoriaAspecto.COMPORTAMIENTOS,
        orden=1,
        texto="texto de prueba",
    )


def test_calcula_promedio_ponderado_por_cultura_y_momento():
    aspectos = [_aspecto(1, TipoCultura.LOGRO)]
    calificaciones = [
        Calificacion(1, 1, Momento.PASADO, Valoracion.BAJO),
        Calificacion(1, 2, Momento.PASADO, Valoracion.MEDIO),
        Calificacion(1, 3, Momento.PASADO, Valoracion.ALTO),
        Calificacion(1, 1, Momento.ACTUAL, Valoracion.ALTO),
        Calificacion(1, 2, Momento.ACTUAL, Valoracion.ALTO),
    ]

    resumen = CalculadoraResumen().calcular(aspectos, calificaciones)

    pasado = resumen.para(TipoCultura.LOGRO, Momento.PASADO)
    assert pasado.total == 3
    assert pasado.promedio_ponderado == 1.0  # (0+1+2)/3

    actual = resumen.para(TipoCultura.LOGRO, Momento.ACTUAL)
    assert actual.total == 2
    assert actual.promedio_ponderado == 2.0
    assert actual.porcentaje_valor_alto == 100.0


def test_brecha_es_diferencia_entre_actual_y_pasado():
    aspectos = [_aspecto(1, TipoCultura.INNOVADORA)]
    calificaciones = [
        Calificacion(1, 1, Momento.PASADO, Valoracion.BAJO),
        Calificacion(1, 1, Momento.ACTUAL, Valoracion.ALTO),
    ]

    resumen = CalculadoraResumen().calcular(aspectos, calificaciones)

    assert resumen.brecha(TipoCultura.INNOVADORA) == 2.0


def test_solo_consenso_filtra_calificaciones_individuales():
    aspectos = [_aspecto(1, TipoCultura.EQUIPO_UNICO)]
    calificaciones = [
        Calificacion(1, 1, Momento.PASADO, Valoracion.BAJO, es_consenso=False),
        Calificacion(1, 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
    ]

    resumen = CalculadoraResumen().calcular(aspectos, calificaciones, solo_consenso=True)

    pasado = resumen.para(TipoCultura.EQUIPO_UNICO, Momento.PASADO)
    assert pasado.total == 1
    assert pasado.conteo_por_valoracion[Valoracion.ALTO] == 1


def test_resumen_vacio_sin_calificaciones():
    resumen = CalculadoraResumen().calcular([], [])
    assert resumen.resumenes == ()
