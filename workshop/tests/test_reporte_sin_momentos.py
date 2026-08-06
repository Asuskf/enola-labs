"""Un taller con una sola medición no debe nombrar ningún momento.

Cuando el taller se hace por primera vez hay un único valor por cultura:
llamarlo "PASADO" no aporta nada y confunde a quien lee el reporte. Las
palabras PASADO / ACTUAL / Momento solo aparecen cuando de verdad hay dos
mediciones que distinguir.
"""

import re
from datetime import date

import pandas as pd
import pytest

from taller_cultura.application.use_cases import CalcularReporteTaller
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    CategoriaAspecto,
    Momento,
    TipoCultura,
    Valoracion,
)
from taller_cultura.infrastructure.adapters.excel_writer import ExportadorReporteExcel
from taller_cultura.infrastructure.adapters.html_writer import ExportadorReporteHTML

from .test_use_cases import RepositorioEnMemoria

PALABRAS_DE_MOMENTO = ("PASADO", "ACTUAL", "Momento", "momento")


def _aspecto(id_, tipo_cultura):
    return Aspecto(
        id=id_,
        tipo_cultura=tipo_cultura,
        categoria=CategoriaAspecto.COMPORTAMIENTOS,
        orden=id_,
        texto=f"ítem {id_}",
    )


def _repo_con(momentos):
    """Una calificación de consenso por cultura, en cada momento indicado."""
    repo = RepositorioEnMemoria()
    aspectos, calificaciones = [], []
    for indice, tipo_cultura in enumerate(TipoCultura, start=1):
        aspectos.append(_aspecto(indice, tipo_cultura))
        for momento in momentos:
            calificaciones.append(
                Calificacion(indice, 0, momento, Valoracion.MEDIO, es_consenso=True)
            )
    sesion = repo.sembrar("ACME", date(2026, 3, 14), aspectos, calificaciones)
    return repo, sesion


def test_el_dominio_sabe_si_distingue_momentos():
    repo_uno, sesion_uno = _repo_con([Momento.PASADO])
    repo_dos, sesion_dos = _repo_con([Momento.PASADO, Momento.ACTUAL])

    resumen_uno = CalcularReporteTaller(repo_uno).ejecutar(sesion_uno.id).resumen
    resumen_dos = CalcularReporteTaller(repo_dos).ejecutar(sesion_dos.id).resumen

    assert not resumen_uno.distingue_momentos
    assert resumen_uno.momento_unico is Momento.PASADO
    assert resumen_dos.distingue_momentos
    assert resumen_dos.momento_unico is None


def test_promedio_sin_indicar_momento_usa_el_unico_que_hay():
    repo, sesion = _repo_con([Momento.PASADO])

    resumen = CalcularReporteTaller(repo).ejecutar(sesion.id).resumen

    assert resumen.promedio(TipoCultura.LOGRO) == 1.0


def test_el_reporte_html_no_nombra_momentos_con_una_sola_medicion(tmp_path):
    repo, sesion = _repo_con([Momento.PASADO])
    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id)
    destino = tmp_path / "reporte.html"

    ExportadorReporteHTML().exportar_reporte(reporte, str(destino))
    html = destino.read_text(encoding="utf-8")

    encontradas = [p for p in PALABRAS_DE_MOMENTO if re.search(p, html)]
    assert not encontradas, f"el reporte menciona {encontradas}"
    # Y en su lugar explica por qué no hay comparación.
    assert "primera medición" in html


def test_el_reporte_html_si_los_nombra_cuando_hay_dos_mediciones(tmp_path):
    repo, sesion = _repo_con([Momento.PASADO, Momento.ACTUAL])
    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id)
    destino = tmp_path / "reporte.html"

    ExportadorReporteHTML().exportar_reporte(reporte, str(destino))
    html = destino.read_text(encoding="utf-8")

    assert "PASADO" in html and "ACTUAL" in html


def test_el_excel_omite_la_columna_y_la_hoja_de_momentos(tmp_path):
    repo, sesion = _repo_con([Momento.PASADO])
    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id)
    destino = tmp_path / "reporte.xlsx"

    ExportadorReporteExcel().exportar_reporte(reporte, str(destino))

    libro = pd.ExcelFile(destino)
    assert "Brechas" not in libro.sheet_names
    assert "Momento" not in pd.read_excel(libro, "Resumen").columns
    assert "Momento" not in pd.read_excel(libro, "Detalle por categoria").columns


def test_el_excel_incluye_las_brechas_cuando_hay_dos_mediciones(tmp_path):
    repo, sesion = _repo_con([Momento.PASADO, Momento.ACTUAL])
    reporte = CalcularReporteTaller(repo).ejecutar(sesion.id)
    destino = tmp_path / "reporte.xlsx"

    ExportadorReporteExcel().exportar_reporte(reporte, str(destino))

    libro = pd.ExcelFile(destino)
    assert "Brechas" in libro.sheet_names
    assert "Momento" in pd.read_excel(libro, "Resumen").columns
