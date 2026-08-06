"""Tests de la validación previa del archivo.

La regla: un ERROR detiene la importación; un AVISO la deja seguir pero
queda registrado para que quien lea el reporte sepa en qué apoyarse.
"""

from pathlib import Path

import openpyxl
import pytest

from taller_cultura.application.validacion import Hallazgo, ResultadoValidacion, Severidad
from taller_cultura.infrastructure.adapters.excel_reader import LectorTallerExcel

RUTA_EXCEL = Path(__file__).resolve().parents[1] / "data" / "Taller para pasar a David (1).xlsx"


def test_un_error_impide_procesar():
    resultado = ResultadoValidacion(
        hallazgos=(Hallazgo(Severidad.ERROR, "falta la hoja"),)
    )

    assert not resultado.es_procesable
    assert len(resultado.errores) == 1
    assert "1 error" in resultado.resumen


def test_los_avisos_no_impiden_procesar():
    resultado = ResultadoValidacion(
        hallazgos=(Hallazgo(Severidad.AVISO, "cobertura baja"),)
    )

    assert resultado.es_procesable
    assert len(resultado.avisos) == 1


def test_sin_hallazgos_el_archivo_es_valido():
    assert ResultadoValidacion(hallazgos=()).resumen == "Archivo válido."


def test_rechaza_un_libro_sin_hoja_taller(tmp_path):
    ruta = tmp_path / "cualquiera.xlsx"
    libro = openpyxl.Workbook()
    libro.active.title = "Datos"
    libro.save(ruta)

    resultado = LectorTallerExcel(ruta).validar()

    assert not resultado.es_procesable
    assert any("TALLER" in h.mensaje for h in resultado.errores)


def test_rechaza_una_hoja_taller_sin_la_estructura_esperada(tmp_path):
    """La hoja existe pero no tiene los tipos de cultura ni bloques: no se
    puede sacar nada de ahí, así que es un error, no un aviso.
    """
    ruta = tmp_path / "vacio.xlsx"
    libro = openpyxl.Workbook()
    libro.active.title = "TALLER"
    libro.active["A1"] = "hoja en blanco"
    libro.save(ruta)

    resultado = LectorTallerExcel(ruta).validar()

    assert not resultado.es_procesable


@pytest.mark.skipif(not RUTA_EXCEL.exists(), reason="Excel del taller no disponible")
def test_acepta_el_taller_real_con_avisos():
    resultado = LectorTallerExcel(RUTA_EXCEL).validar()

    assert resultado.es_procesable
    # El archivo real no tiene el momento ACTUAL lleno; debe avisarlo.
    assert any("ACTUAL" in h.mensaje for h in resultado.avisos)
