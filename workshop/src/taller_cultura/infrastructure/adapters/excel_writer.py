"""Adaptador de salida: exporta un `ReporteTaller` a un archivo `.xlsx`.

Implementa el puerto `ExportadorReporte`. Usa pandas para construir hojas
tabulares limpias (una fila por combinación tipo de cultura / momento, y
otra por tipo de cultura / categoría / momento), muy distintas de la
disposición original del taller.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from taller_cultura.application.ports import ExportadorReporte
from taller_cultura.application.use_cases import ReporteTaller
from taller_cultura.domain.model import Momento, TipoCultura, Valoracion
from taller_cultura.domain.services import ResumenTaller


class ExportadorReporteExcel(ExportadorReporte):
    """Genera un reporte `.xlsx` con el resumen del taller."""

    def exportar_reporte(self, reporte: ReporteTaller, ruta_destino: str) -> None:
        ruta = Path(ruta_destino)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
            self._construir_dataframe_ficha(reporte).to_excel(
                writer, sheet_name="Ficha", index=False
            )
            self._construir_dataframe_resumen(reporte.resumen).to_excel(
                writer, sheet_name="Resumen", index=False
            )
            # La hoja de brechas solo existe si hay dos momentos que restar.
            if reporte.resumen.distingue_momentos:
                self._construir_dataframe_brechas(reporte.resumen).to_excel(
                    writer, sheet_name="Brechas", index=False
                )
            self._construir_dataframe_detalle(reporte).to_excel(
                writer, sheet_name="Detalle por categoria", index=False
            )

    @staticmethod
    def _construir_dataframe_ficha(reporte: ReporteTaller) -> pd.DataFrame:
        d = reporte.diagnostico
        filas = [
            ("Empresa", reporte.sesion.empresa),
            ("Fecha del taller", reporte.sesion.fecha_taller.isoformat()),
            ("Versión", reporte.sesion.numero_version),
            ("Base de cálculo", reporte.base_calculo),
            ("Ítems del taller", d.total_aspectos),
            ("Ítems calificados", d.aspectos_calificados),
            ("Ítems sin calificar", d.aspectos_sin_calificar),
            ("Cobertura (%)", d.porcentaje_cobertura),
            ("Respuestas de consenso", d.respuestas_consenso),
            ("Respuestas individuales", d.respuestas_individuales),
            ("Calificadores participantes", reporte.calificadores_participantes),
        ]
        return pd.DataFrame(filas, columns=["Concepto", "Valor"])

    @staticmethod
    def _construir_dataframe_resumen(resumen: ResumenTaller) -> pd.DataFrame:
        # Con una sola medición la columna «Momento» sobra: todas las filas
        # dirían lo mismo y nombrarla confunde.
        distingue = resumen.distingue_momentos
        filas = []
        for r in resumen.resumenes:
            filas.append(
                {
                    "Tipo de cultura": r.tipo_cultura.value,
                    **({"Momento": r.momento.value} if distingue else {}),
                    "Total respuestas": r.total,
                    "Bajo (R)": r.conteo_por_valoracion.get(Valoracion.BAJO, 0),
                    "Medio (A)": r.conteo_por_valoracion.get(Valoracion.MEDIO, 0),
                    "Alto (V)": r.conteo_por_valoracion.get(Valoracion.ALTO, 0),
                    "Promedio ponderado (0-2)": r.promedio_ponderado,
                    "% valor alto (V)": r.porcentaje_valor_alto,
                }
            )
        return pd.DataFrame(filas)

    @staticmethod
    def _construir_dataframe_brechas(resumen: ResumenTaller) -> pd.DataFrame:
        filas = []
        for tipo_cultura in TipoCultura:
            pasado = resumen.para(tipo_cultura, Momento.PASADO)
            actual = resumen.para(tipo_cultura, Momento.ACTUAL)
            filas.append(
                {
                    "Tipo de cultura": tipo_cultura.value,
                    "Promedio PASADO": pasado.promedio_ponderado if pasado else None,
                    "Promedio ACTUAL": actual.promedio_ponderado if actual else None,
                    "Brecha (ACTUAL - PASADO)": resumen.brecha(tipo_cultura),
                }
            )
        return pd.DataFrame(filas)

    @staticmethod
    def _construir_dataframe_detalle(reporte: ReporteTaller) -> pd.DataFrame:
        distingue = reporte.resumen.distingue_momentos
        filas = []
        for r in reporte.detalle_categoria:
            filas.append(
                {
                    "Tipo de cultura": r.tipo_cultura.value,
                    "Categoria": r.categoria.value,
                    **({"Momento": r.momento.value} if distingue else {}),
                    "Total respuestas": r.total,
                    "Bajo (R)": r.conteo_por_valoracion.get(Valoracion.BAJO, 0),
                    "Medio (A)": r.conteo_por_valoracion.get(Valoracion.MEDIO, 0),
                    "Alto (V)": r.conteo_por_valoracion.get(Valoracion.ALTO, 0),
                    "Promedio ponderado (0-2)": r.promedio_ponderado,
                }
            )
        return pd.DataFrame(filas)
