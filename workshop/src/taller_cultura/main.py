"""Punto de composición y CLI.

Este es el único módulo que conoce TANTO los casos de uso (aplicación)
COMO los adaptadores concretos (infraestructura). Cablea unos con otros
(inyección de dependencias manual) y expone una CLI simple con subcomandos:

    python -m taller_cultura importar --excel ruta.xlsx --bd taller.db
    python -m taller_cultura resumen --bd taller.db [--consenso] [--reporte salida.xlsx|salida.html]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from taller_cultura.application.ports import ExportadorReporte
from taller_cultura.application.use_cases import (
    CalcularReporteTaller,
    CalcularResumenTaller,
    ExportarReporteTaller,
    ImportarTallerDesdeExcel,
)
from taller_cultura.infrastructure.adapters import (
    ExportadorReporteExcel,
    ExportadorReporteHTML,
    LectorTallerExcel,
    RepositorioTallerSQLite,
)

EXPORTADORES_POR_EXTENSION: dict[str, type[ExportadorReporte]] = {
    ".xlsx": ExportadorReporteExcel,
    ".html": ExportadorReporteHTML,
    ".htm": ExportadorReporteHTML,
}


def _exportador_para(ruta: Path) -> ExportadorReporte:
    clase = EXPORTADORES_POR_EXTENSION.get(ruta.suffix.lower())
    if clase is None:
        extensiones = ", ".join(EXPORTADORES_POR_EXTENSION)
        raise SystemExit(f"Extensión de reporte no soportada: {ruta.suffix!r} (use: {extensiones})")
    return clase()


def _comando_importar(args: argparse.Namespace) -> None:
    lector = LectorTallerExcel(args.excel)
    with RepositorioTallerSQLite(args.bd) as repositorio:
        resultado = ImportarTallerDesdeExcel(lector, repositorio).ejecutar()
    print(
        f"Importación completa desde {args.excel} hacia {args.bd}:\n"
        f"  Empresas:       {resultado.empresas}\n"
        f"  Calificadores:  {resultado.calificadores}\n"
        f"  Aspectos:       {resultado.aspectos}\n"
        f"  Calificaciones: {resultado.calificaciones}"
    )


def _comando_resumen(args: argparse.Namespace) -> None:
    with RepositorioTallerSQLite(args.bd) as repositorio:
        resumen = CalcularResumenTaller(repositorio).ejecutar(solo_consenso=args.consenso)

        print(f"{'Tipo de cultura':<24} {'Momento':<8} {'Total':>6} {'Prom(0-2)':>10} {'%Alto V':>9}")
        print("-" * 62)
        for r in resumen.resumenes:
            print(
                f"{r.tipo_cultura.value:<24} {r.momento.value:<8} {r.total:>6} "
                f"{r.promedio_ponderado:>10.2f} {r.porcentaje_valor_alto:>8.1f}%"
            )

        print("\nBrecha ACTUAL - PASADO por tipo de cultura:")
        for tipo_cultura in {r.tipo_cultura for r in resumen.resumenes}:
            print(f"  {tipo_cultura.value:<24} {resumen.brecha(tipo_cultura):+.2f}")

        if args.reporte:
            reporte = CalcularReporteTaller(repositorio).ejecutar(solo_consenso=args.consenso)
            exportador = _exportador_para(args.reporte)
            ExportarReporteTaller(exportador).ejecutar(reporte, args.reporte)
            print(f"\nReporte exportado a: {args.reporte}")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taller_cultura",
        description="ETL y cálculo del taller de diagnóstico de cultura organizacional.",
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)

    parser_importar = subparsers.add_parser(
        "importar", help="Lee el Excel original y lo persiste en SQLite."
    )
    parser_importar.add_argument("--excel", required=True, type=Path, help="Ruta al .xlsx original")
    parser_importar.add_argument("--bd", required=True, type=Path, help="Ruta al archivo SQLite destino")
    parser_importar.set_defaults(func=_comando_importar)

    parser_resumen = subparsers.add_parser(
        "resumen", help="Calcula y muestra el resumen del taller desde SQLite."
    )
    parser_resumen.add_argument("--bd", required=True, type=Path, help="Ruta al archivo SQLite origen")
    parser_resumen.add_argument(
        "--consenso", action="store_true", help="Calcular solo con las calificaciones de consenso"
    )
    parser_resumen.add_argument(
        "--reporte",
        type=Path,
        default=None,
        help="Si se indica, exporta el resumen a este archivo (.xlsx o .html)",
    )
    parser_resumen.set_defaults(func=_comando_resumen)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
