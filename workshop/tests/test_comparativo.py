"""Tests del comparativo: cálculo por categoría y estructura del reporte.

El comparativo comparte las cinco pestañas del reporte individual
(Resumen ejecutivo · Por cultura · Por categoría · Datos · Cómo leer esto)
para que ambos documentos se lean igual.
"""

import re
from datetime import date

import pytest

from taller_cultura.application.use_cases import CompararSesiones
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    CategoriaAspecto,
    Momento,
    TipoCultura,
    Valoracion,
)
from taller_cultura.infrastructure.adapters.html_comparativo import ExportadorComparativoHTML

from .test_use_cases import RepositorioEnMemoria

PESTANAS_ESPERADAS = [
    "Resumen ejecutivo",
    "Por cultura",
    "Por categoría",
    "Datos",
    "Cómo leer esto",
]


def _aspecto(id_, tipo_cultura, categoria):
    return Aspecto(
        id=id_, tipo_cultura=tipo_cultura, categoria=categoria, orden=id_, texto=f"ítem {id_}"
    )


def _sembrar(repo, fecha, valoracion_por_categoria, version=1):
    """Una sesión con una valoración de consenso por cultura y categoría."""
    aspectos, calificaciones, siguiente = [], [], 1
    for categoria, valoracion in valoracion_por_categoria.items():
        for tipo_cultura in TipoCultura:
            aspectos.append(_aspecto(siguiente, tipo_cultura, categoria))
            calificaciones.append(
                Calificacion(siguiente, 0, Momento.PASADO, valoracion, es_consenso=True)
            )
            siguiente += 1
    return repo.sembrar("ACME", fecha, aspectos, calificaciones, version=version)


@pytest.fixture
def comparativo():
    repo = RepositorioEnMemoria()
    antes = _sembrar(
        repo,
        date(2025, 1, 1),
        {CategoriaAspecto.COMPORTAMIENTOS: Valoracion.BAJO, CategoriaAspecto.SISTEMAS: Valoracion.MEDIO},
    )
    ahora = _sembrar(
        repo,
        date(2026, 1, 1),
        {CategoriaAspecto.COMPORTAMIENTOS: Valoracion.ALTO, CategoriaAspecto.SISTEMAS: Valoracion.MEDIO},
        version=2,
    )
    return CompararSesiones(repo).ejecutar(antes.id, ahora.id)


def test_compara_cada_categoria_por_separado(comparativo):
    """Comportamientos sube de rojo a verde; Sistemas se queda igual."""
    por_clave = {
        (c.categoria, c.tipo_cultura): c for c in comparativo.comparacion_categoria
    }

    comportamientos = por_clave[(CategoriaAspecto.COMPORTAMIENTOS, TipoCultura.LOGRO)]
    assert comportamientos.promedio_antes == 0.0
    assert comportamientos.promedio_ahora == 2.0
    assert comportamientos.variacion == 2.0
    assert comportamientos.mejoro

    sistemas = por_clave[(CategoriaAspecto.SISTEMAS, TipoCultura.LOGRO)]
    assert sistemas.variacion == 0.0
    assert not sistemas.mejoro and not sistemas.empeoro


def test_cubre_todas_las_culturas_de_cada_categoria(comparativo):
    esperadas = {
        (categoria, cultura)
        for categoria in (CategoriaAspecto.COMPORTAMIENTOS, CategoriaAspecto.SISTEMAS)
        for cultura in TipoCultura
    }

    obtenidas = {(c.categoria, c.tipo_cultura) for c in comparativo.comparacion_categoria}

    assert obtenidas == esperadas


def test_el_reporte_tiene_las_mismas_cinco_pestanas(comparativo, tmp_path):
    destino = tmp_path / "comparativo.html"

    ExportadorComparativoHTML().exportar_comparativo(comparativo, str(destino))
    html = destino.read_text(encoding="utf-8")

    pestanas = re.findall(r'data-panel="panel-[^"]+">([^<]+)</button>', html)
    assert pestanas == PESTANAS_ESPERADAS
    for ident in ("resumen", "culturas", "categorias", "datos", "metodo"):
        assert f'id="panel-{ident}"' in html


def test_muestra_las_dos_tartas_de_cada_cultura(comparativo, tmp_path):
    """Cinco culturas por dos mediciones en «Por cultura», más el desglose."""
    destino = tmp_path / "comparativo.html"

    ExportadorComparativoHTML().exportar_comparativo(comparativo, str(destino))
    html = destino.read_text(encoding="utf-8")

    # 5 culturas + 10 (2 categorías × 5 culturas) pares, cada uno con 2 tartas.
    assert html.count('class="tarjeta-par') == 15
    assert html.count('class="tarta"') == 30
    for animal in ("Águila real", "Delfín", "Lobo", "Pulpo", "Colibrí"):
        assert animal in html


def test_usa_los_colores_del_semaforo_del_libro(comparativo, tmp_path):
    destino = tmp_path / "comparativo.html"

    ExportadorComparativoHTML().exportar_comparativo(comparativo, str(destino))
    html = destino.read_text(encoding="utf-8")

    for color in ("#ED3737", "#F7F732", "#60C541"):
        assert color in html
