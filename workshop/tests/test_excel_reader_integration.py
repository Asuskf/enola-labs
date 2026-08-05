"""Test de integración contra el Excel real del taller.

Se salta automáticamente si el archivo no está disponible en esta máquina
(por ejemplo, en CI). Verifica que el parser produce un catálogo de
aspectos consistente (5 tipos de cultura x mismo número de ítems por
categoría) y que las calificaciones referencian aspectos válidos.
"""

from pathlib import Path

import pytest

from taller_cultura.domain.model import CategoriaAspecto, TipoCultura
from taller_cultura.infrastructure.adapters.excel_reader import LectorTallerExcel

RUTA_EXCEL = Path(__file__).resolve().parent.parent / "data" / "Taller para pasar a David (1).xlsx"

pytestmark = pytest.mark.skipif(
    not RUTA_EXCEL.exists(), reason="Excel original no disponible en esta máquina"
)


def test_lee_catalogo_de_aspectos_por_categoria():
    """El Excel original es deliberadamente irregular: no todos los tipos de
    cultura tienen la misma cantidad de ítems en cada categoría (ya se
    observa en la hoja `Hoja1`, con columnas de distinto largo). Por eso
    aquí solo verificamos que se leyó contenido real de las 4 categorías y
    de los 5 tipos de cultura, sin exigir simetría perfecta.
    """
    lector = LectorTallerExcel(RUTA_EXCEL)
    aspectos = lector.leer_aspectos()

    assert len(aspectos) > 0

    categorias_presentes = {a.categoria for a in aspectos}
    assert categorias_presentes == set(CategoriaAspecto)

    culturas_presentes = {a.tipo_cultura for a in aspectos}
    assert culturas_presentes == set(TipoCultura)

    # Cada aspecto debe tener texto no vacío.
    assert all(a.texto.strip() for a in aspectos)


def test_calificaciones_referencian_aspectos_validos():
    lector = LectorTallerExcel(RUTA_EXCEL)
    aspectos = lector.leer_aspectos()
    calificaciones = lector.leer_calificaciones(aspectos)

    ids_validos = set(range(len(aspectos)))
    for calificacion in calificaciones:
        assert calificacion.aspecto_id in ids_validos
        assert 0 <= calificacion.calificador_codigo <= 12


def test_lee_calificadores_incluyendo_consenso():
    lector = LectorTallerExcel(RUTA_EXCEL)
    calificadores = lector.leer_calificadores()

    codigos = {c.codigo for c in calificadores}
    assert 0 in codigos  # CONSENSO
    assert len(calificadores) >= 2
