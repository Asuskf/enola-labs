"""Punto de composición y CLI.

Este es el único módulo que conoce TANTO los casos de uso (aplicación)
COMO los adaptadores concretos (infraestructura). Cablea unos con otros
(inyección de dependencias manual) y expone la CLI:

    python -m taller_cultura gui
    python -m taller_cultura validar   --excel taller.xlsx
    python -m taller_cultura importar  --excel taller.xlsx --empresa "ACME" --fecha 2026-03-14
    python -m taller_cultura sesiones
    python -m taller_cultura reporte   --sesion 1 --salida reporte.html
    python -m taller_cultura comparar  --antes 1 --ahora 2 --salida comparativo.html
    python -m taller_cultura plantilla --excel taller.xlsx --salida "TALLER para enviar.xlsx"
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from taller_cultura.application.ports import ExportadorReporte
from taller_cultura.application.use_cases import (
    ArchivoNoProcesable,
    CalcularReporteTaller,
    CompararSesiones,
    ExportarPlantillaTaller,
    ExportarReporteComparativo,
    ExportarReporteTaller,
    ImportarSesionTaller,
    ListarSesiones,
    SesionNoEncontrada,
    ValidarArchivoTaller,
)
from taller_cultura.domain.model import Momento, TipoCultura
from taller_cultura.infrastructure.adapters import (
    ExportadorComparativoHTML,
    ExportadorPlantillaExcel,
    ExportadorReporteExcel,
    ExportadorReporteHTML,
    LectorTallerExcel,
    RepositorioTallerSQLite,
)

BD_POR_DEFECTO = Path("data") / "talleres.db"

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


def _fecha(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida {texto!r}. Use el formato AAAA-MM-DD (por ejemplo 2026-03-14)."
        ) from error


def _imprimir_validacion(resultado) -> None:
    print(resultado.resumen)
    for hallazgo in resultado.hallazgos:
        print(f"  {hallazgo}")


# -- comandos ---------------------------------------------------------------


def _comando_gui(_args: argparse.Namespace) -> None:
    try:
        from taller_cultura.infrastructure.gui import lanzar_gui
    except ImportError as error:  # pragma: no cover - depende de la instalación
        # tkinter viene con Python en Windows y macOS, pero en muchas
        # distribuciones de Linux es un paquete aparte.
        raise SystemExit(
            "No se pudo abrir la interfaz gráfica porque falta tkinter.\n"
            "  · Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  · Fedora:         sudo dnf install python3-tkinter\n"
            "  · Arch:           sudo pacman -S tk\n"
            "Mientras tanto puedes usar los comandos de la CLI "
            "(validar, importar, reporte, comparar, plantilla).\n"
            f"Detalle: {error}"
        ) from error

    lanzar_gui()


def _comando_validar(args: argparse.Namespace) -> None:
    resultado = ValidarArchivoTaller(LectorTallerExcel(args.excel)).ejecutar()
    _imprimir_validacion(resultado)
    if not resultado.es_procesable:
        raise SystemExit(1)


def _comando_importar(args: argparse.Namespace) -> None:
    lector = LectorTallerExcel(args.excel)
    empresa = args.empresa or lector.leer_nombre_empresa() or Path(args.excel).stem

    with RepositorioTallerSQLite(args.bd) as repositorio:
        previas = repositorio.listar_sesiones(empresa)
        try:
            resultado = ImportarSesionTaller(lector, repositorio).ejecutar(
                empresa=empresa,
                fecha_taller=args.fecha,
                archivo_origen=str(args.excel),
                omitir_validacion=args.forzar,
            )
        except ArchivoNoProcesable as error:
            _imprimir_validacion(error.resultado)
            raise SystemExit(1) from error

    sesion = resultado.sesion
    if previas:
        print(
            f"«{empresa}» ya tenía {len(previas)} sesión(es): esta es la versión "
            f"{sesion.numero_version}. Puedes compararlas con el comando «comparar»."
        )
    print(
        f"Sesión #{sesion.id} registrada — {sesion.titulo}\n"
        f"  Calificadores:  {resultado.calificadores}\n"
        f"  Ítems:          {resultado.aspectos}\n"
        f"  Calificaciones: {resultado.calificaciones}"
    )
    if resultado.validacion.avisos:
        print("\nAvisos sobre el archivo:")
        for aviso in resultado.validacion.avisos:
            print(f"  {aviso}")


def _comando_sesiones(args: argparse.Namespace) -> None:
    with RepositorioTallerSQLite(args.bd) as repositorio:
        sesiones = ListarSesiones(repositorio).ejecutar(args.empresa)

    if not sesiones:
        print("No hay sesiones registradas todavía.")
        return
    print(f"{'ID':>4}  {'Empresa':<32} {'Fecha':<12} {'Versión':>7}")
    print("-" * 60)
    for sesion in sesiones:
        print(
            f"{sesion.id:>4}  {sesion.empresa:<32} "
            f"{sesion.fecha_taller.isoformat():<12} {sesion.numero_version:>7}"
        )


def _comando_borrar(args: argparse.Namespace) -> None:
    with RepositorioTallerSQLite(args.bd) as repositorio:
        sesion = repositorio.obtener_sesion(args.sesion)
        if sesion is None:
            raise SystemExit(f"No existe la sesión {args.sesion}")
        if not args.si:
            respuesta = input(f"¿Borrar «{sesion.titulo}» y sus valoraciones? [s/N] ")
            if respuesta.strip().lower() not in {"s", "si", "sí"}:
                print("Cancelado.")
                return
        repositorio.eliminar_sesion(args.sesion)
    print(f"Borrado: {sesion.titulo}")


def _comando_reporte(args: argparse.Namespace) -> None:
    solo_consenso = not args.todas
    with RepositorioTallerSQLite(args.bd) as repositorio:
        try:
            reporte = CalcularReporteTaller(repositorio).ejecutar(
                args.sesion, solo_consenso=solo_consenso
            )
        except SesionNoEncontrada as error:
            raise SystemExit(str(error)) from error

        diagnostico = reporte.diagnostico
        print(f"{reporte.sesion.titulo}")
        print(f"Base de cálculo: {reporte.base_calculo}")
        print(
            f"Cobertura: {diagnostico.aspectos_calificados}/{diagnostico.total_aspectos} ítems "
            f"({diagnostico.porcentaje_cobertura:.0f}%) · "
            f"{diagnostico.respuestas_consenso} consenso, "
            f"{diagnostico.respuestas_individuales} individuales\n"
        )
        # Con una sola medición la columna «Momento» no aporta nada: se omite.
        distingue = reporte.resumen.distingue_momentos
        cabecera_momento = f"{'Momento':<8} " if distingue else ""
        print(
            f"{'Tipo de cultura':<24} {cabecera_momento}{'Total':>6} "
            f"{'Prom(0-2)':>10} {'%Alto V':>9}"
        )
        print("-" * (62 if distingue else 53))
        for r in reporte.resumen.resumenes:
            celda_momento = f"{r.momento.value:<8} " if distingue else ""
            print(
                f"{r.tipo_cultura.value:<24} {celda_momento}{r.total:>6} "
                f"{r.promedio_ponderado:>10.2f} {r.porcentaje_valor_alto:>8.1f}%"
            )

        if args.salida:
            ExportarReporteTaller(_exportador_para(args.salida)).ejecutar(reporte, str(args.salida))
            print(f"\nReporte exportado a: {args.salida}")


def _comando_comparar(args: argparse.Namespace) -> None:
    with RepositorioTallerSQLite(args.bd) as repositorio:
        try:
            comparativo = CompararSesiones(repositorio).ejecutar(
                args.antes,
                args.ahora,
                solo_consenso=not args.todas,
                momento=Momento.desde_texto(args.momento),
            )
        except SesionNoEncontrada as error:
            raise SystemExit(str(error)) from error

        antes, ahora = comparativo.antes.sesion, comparativo.ahora.sesion
        if antes.empresa != ahora.empresa:
            print(
                f"Aviso: se están comparando dos empresas distintas "
                f"(«{antes.empresa}» y «{ahora.empresa}»).\n"
            )
        distingue = (
            comparativo.antes.resumen.distingue_momentos
            or comparativo.ahora.resumen.distingue_momentos
        )
        detalle = f"   (momento {comparativo.momento.value})" if distingue else ""
        print(f"{antes.titulo}  ->  {ahora.titulo}{detalle}\n")
        print(f"{'Tipo de cultura':<24} {'Antes':>7} {'Ahora':>7} {'Variación':>10}")
        print("-" * 52)
        for comp in comparativo.comparacion.comparaciones:
            a = "s/d" if comp.promedio_antes is None else f"{comp.promedio_antes:.2f}"
            b = "s/d" if comp.promedio_ahora is None else f"{comp.promedio_ahora:.2f}"
            v = "—" if comp.variacion is None else f"{comp.variacion:+.2f}"
            print(f"{comp.tipo_cultura.value:<24} {a:>7} {b:>7} {v:>10}")

        if args.salida:
            ExportarReporteComparativo(ExportadorComparativoHTML()).ejecutar(
                comparativo, str(args.salida)
            )
            print(f"\nComparativo exportado a: {args.salida}")


def _comando_plantilla(args: argparse.Namespace) -> None:
    ExportarPlantillaTaller(ExportadorPlantillaExcel()).ejecutar(str(args.excel), str(args.salida))
    print(
        f"Plantilla lista en: {args.salida}\n"
        "Contiene solo las hojas de trabajo (TALLER y CALIFICADORES); el material "
        "derivado va en el reporte."
    )


# -- parser -------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taller_cultura",
        description="Taller de diagnóstico de cultura organizacional: importar, reportar y comparar.",
    )
    parser.add_argument(
        "--bd", type=Path, default=BD_POR_DEFECTO, help=f"Base SQLite (por defecto {BD_POR_DEFECTO})"
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_gui = subparsers.add_parser("gui", help="Abre la interfaz gráfica de escritorio.")
    p_gui.set_defaults(func=_comando_gui)

    p_validar = subparsers.add_parser(
        "validar", help="Revisa el archivo del taller sin importarlo."
    )
    p_validar.add_argument("--excel", required=True, type=Path)
    p_validar.set_defaults(func=_comando_validar)

    p_importar = subparsers.add_parser(
        "importar", help="Registra una sesión (empresa + fecha) y carga el archivo."
    )
    p_importar.add_argument("--excel", required=True, type=Path)
    p_importar.add_argument("--empresa", help="Nombre de la empresa (obligatorio si el libro no lo trae)")
    p_importar.add_argument(
        "--fecha", required=True, type=_fecha, help="Fecha del taller, AAAA-MM-DD"
    )
    p_importar.add_argument(
        "--forzar", action="store_true", help="Importar aunque la validación encuentre errores"
    )
    p_importar.set_defaults(func=_comando_importar)

    p_sesiones = subparsers.add_parser("sesiones", help="Lista las sesiones registradas.")
    p_sesiones.add_argument("--empresa", default=None)
    p_sesiones.set_defaults(func=_comando_sesiones)

    p_borrar = subparsers.add_parser("borrar", help="Borra una sesión y sus valoraciones.")
    p_borrar.add_argument("--sesion", required=True, type=int, help="ID de la sesión")
    p_borrar.add_argument("--si", action="store_true", help="No preguntar confirmación")
    p_borrar.set_defaults(func=_comando_borrar)

    p_reporte = subparsers.add_parser("reporte", help="Reporte de una sesión.")
    p_reporte.add_argument("--sesion", required=True, type=int, help="ID de la sesión")
    p_reporte.add_argument("--salida", type=Path, default=None, help="Archivo .html o .xlsx")
    p_reporte.add_argument(
        "--todas",
        action="store_true",
        help="Incluir las calificaciones individuales (por defecto solo el consenso)",
    )
    p_reporte.set_defaults(func=_comando_reporte)

    p_comparar = subparsers.add_parser(
        "comparar", help="Reporte comparativo entre dos sesiones (antes y ahora)."
    )
    p_comparar.add_argument("--antes", required=True, type=int, help="ID de la sesión anterior")
    p_comparar.add_argument("--ahora", required=True, type=int, help="ID de la sesión actual")
    p_comparar.add_argument("--salida", type=Path, default=None, help="Archivo .html")
    p_comparar.add_argument("--momento", default=Momento.PASADO.value, choices=[m.value for m in Momento])
    p_comparar.add_argument("--todas", action="store_true")
    p_comparar.set_defaults(func=_comando_comparar)

    p_plantilla = subparsers.add_parser(
        "plantilla", help="Genera el Excel que se reparte: solo la hoja TALLER."
    )
    p_plantilla.add_argument("--excel", required=True, type=Path)
    p_plantilla.add_argument("--salida", required=True, type=Path)
    p_plantilla.set_defaults(func=_comando_plantilla)

    return parser


def _preparar_salida() -> None:
    """Evita que un carácter fuera de la codificación de la consola aborte
    el comando (la consola de Windows suele usar cp1252, no UTF-8).
    """
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None:
            try:
                reconfigurar(errors="replace")
            except (ValueError, OSError):  # pragma: no cover - flujo no reconfigurable
                pass


def main(argv: list[str] | None = None) -> int:
    _preparar_salida()
    parser = construir_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
