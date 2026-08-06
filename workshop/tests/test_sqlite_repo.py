"""Tests del repositorio SQLite: aislamiento entre sesiones y versionado."""

from datetime import date

import pytest

from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    Calificador,
    CategoriaAspecto,
    Momento,
    SesionTaller,
    TipoCultura,
    Valoracion,
)
from taller_cultura.infrastructure.adapters.sqlite_repo import RepositorioTallerSQLite


@pytest.fixture
def repo(tmp_path):
    with RepositorioTallerSQLite(tmp_path / "talleres.db") as repositorio:
        yield repositorio


def _sesion(empresa="ACME", fecha=date(2025, 1, 1), version=1) -> SesionTaller:
    return SesionTaller(id=None, empresa=empresa, fecha_taller=fecha, numero_version=version)


def _aspecto(orden, tipo_cultura=TipoCultura.LOGRO) -> Aspecto:
    return Aspecto(
        id=None,
        tipo_cultura=tipo_cultura,
        categoria=CategoriaAspecto.COMPORTAMIENTOS,
        orden=orden,
        texto=f"ítem {orden}",
    )


def test_la_version_se_numera_por_empresa(repo):
    assert repo.siguiente_version("ACME") == 1
    repo.crear_sesion(_sesion(version=1))
    assert repo.siguiente_version("ACME") == 2
    # Otra empresa arranca de nuevo en 1.
    assert repo.siguiente_version("OTRA") == 1


def test_conserva_la_fecha_como_fecha_no_como_texto(repo):
    creada = repo.crear_sesion(_sesion(fecha=date(2026, 3, 14)))

    recuperada = repo.obtener_sesion(creada.id)

    assert recuperada.fecha_taller == date(2026, 3, 14)
    assert recuperada.empresa == "ACME"


def test_cada_sesion_guarda_sus_datos_por_separado(repo):
    """Dos sesiones de la misma empresa no deben mezclarse: es la base de
    poder comparar «antes» contra «ahora».
    """
    v1 = repo.crear_sesion(_sesion(version=1))
    v2 = repo.crear_sesion(_sesion(fecha=date(2026, 1, 1), version=2))

    ids_v1 = repo.guardar_aspectos(v1.id, [_aspecto(1)])
    ids_v2 = repo.guardar_aspectos(v2.id, [_aspecto(1), _aspecto(2)])

    repo.guardar_calificaciones(
        v1.id, [Calificacion(ids_v1[0], 0, Momento.PASADO, Valoracion.BAJO, es_consenso=True)]
    )
    repo.guardar_calificaciones(
        v2.id,
        [
            Calificacion(ids_v2[0], 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
            Calificacion(ids_v2[1], 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True),
        ],
    )

    assert len(repo.listar_aspectos(v1.id)) == 1
    assert len(repo.listar_aspectos(v2.id)) == 2
    assert len(repo.listar_calificaciones(v1.id)) == 1
    assert len(repo.listar_calificaciones(v2.id)) == 2
    assert repo.listar_calificaciones(v1.id)[0].valoracion is Valoracion.BAJO


def test_reimportar_una_sesion_reemplaza_sus_calificaciones(repo):
    """Volver a cargar el archivo no debe duplicar las respuestas."""
    sesion = repo.crear_sesion(_sesion())
    ids = repo.guardar_aspectos(sesion.id, [_aspecto(1)])
    calificacion = Calificacion(ids[0], 0, Momento.PASADO, Valoracion.MEDIO, es_consenso=True)

    repo.guardar_calificaciones(sesion.id, [calificacion])
    repo.guardar_calificaciones(sesion.id, [calificacion])

    assert len(repo.listar_calificaciones(sesion.id)) == 1


def test_eliminar_una_sesion_se_lleva_su_contenido(repo):
    sesion = repo.crear_sesion(_sesion())
    ids = repo.guardar_aspectos(sesion.id, [_aspecto(1)])
    repo.guardar_calificaciones(
        sesion.id, [Calificacion(ids[0], 0, Momento.PASADO, Valoracion.ALTO, es_consenso=True)]
    )

    repo.eliminar_sesion(sesion.id)

    assert repo.obtener_sesion(sesion.id) is None
    assert repo.listar_aspectos(sesion.id) == []
    assert repo.listar_calificaciones(sesion.id) == []


def test_listar_sesiones_filtra_por_empresa(repo):
    repo.crear_sesion(_sesion(empresa="ACME"))
    repo.crear_sesion(_sesion(empresa="OTRA"))

    assert len(repo.listar_sesiones()) == 2
    assert [s.empresa for s in repo.listar_sesiones("ACME")] == ["ACME"]


def test_guarda_los_calificadores_de_cada_sesion(repo):
    sesion = repo.crear_sesion(_sesion())

    repo.guardar_calificadores(
        sesion.id, [Calificador(codigo=0, nombre="CONSENSO"), Calificador(codigo=1, nombre="Ana")]
    )

    calificadores = repo.listar_calificadores(sesion.id)
    assert [c.codigo for c in calificadores] == [0, 1]
    assert calificadores[1].nombre == "Ana"
