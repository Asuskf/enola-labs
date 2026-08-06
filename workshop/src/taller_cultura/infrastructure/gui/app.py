"""Interfaz gráfica de escritorio (tkinter) del taller de cultura.

Es un **adaptador primario**: igual que la CLI, se limita a invocar los
casos de uso de `taller_cultura.application`. No contiene ninguna regla de
negocio; si algo hay que calcular, lo calcula el dominio.

Usa solo tkinter (biblioteca estándar), así que no añade dependencias.
Las tareas lentas (leer el Excel, generar reportes) corren en un hilo
aparte para que la ventana no se congele.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from taller_cultura.application.use_cases import (
    CalcularReporteTaller,
    ExportarPlantillaTaller,
    ExportarReporteTaller,
    ImportarTallerDesdeExcel,
)
from taller_cultura.domain.model import Momento, TipoCultura
from taller_cultura.infrastructure.adapters import (
    ExportadorPlantillaExcel,
    ExportadorReporteExcel,
    ExportadorReporteHTML,
    LectorTallerExcel,
    RepositorioTallerSQLite,
)

TITULO = "Taller de cultura organizacional"


class AplicacionTaller(ttk.Frame):
    """Ventana principal: elegir el Excel, importarlo y generar entregables."""

    def __init__(self, raiz: tk.Tk) -> None:
        super().__init__(raiz, padding=12)
        self.raiz = raiz
        self.grid(sticky="nsew")
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self.ruta_excel = tk.StringVar()
        self.ruta_bd = tk.StringVar(value=str(Path("data") / "taller.db"))
        self.solo_consenso = tk.BooleanVar(value=True)
        self.estado = tk.StringVar(value="Elige el archivo del taller para empezar.")

        self._cola: queue.Queue = queue.Queue()
        self._ultimo_reporte_html: Path | None = None
        self._botones_accion: list[ttk.Button] = []

        self._construir_seccion_archivo()
        self._construir_seccion_acciones()
        self._construir_seccion_resumen()
        self._construir_barra_estado()
        self._refrescar_habilitacion()
        self.after(100, self._procesar_cola)

    # -- construcción de la interfaz ---------------------------------------

    def _construir_seccion_archivo(self) -> None:
        marco = ttk.LabelFrame(self, text="1. Archivo del taller", padding=10)
        marco.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        marco.columnconfigure(1, weight=1)

        ttk.Label(marco, text="Excel del taller:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(marco, textvariable=self.ruta_excel).grid(row=0, column=1, sticky="ew")
        ttk.Button(marco, text="Examinar…", command=self._elegir_excel).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(marco, text="Base de datos:").grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0)
        )
        ttk.Entry(marco, textvariable=self.ruta_bd).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(marco, text="Cambiar…", command=self._elegir_bd).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0)
        )

    def _construir_seccion_acciones(self) -> None:
        marco = ttk.LabelFrame(self, text="2. Acciones", padding=10)
        marco.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        acciones = (
            ("Importar taller", self._importar),
            ("Reporte HTML", self._generar_html),
            ("Reporte Excel", self._generar_excel),
            ("Plantilla para enviar", self._exportar_plantilla),
        )
        for columna, (texto, comando) in enumerate(acciones):
            boton = ttk.Button(marco, text=texto, command=comando)
            boton.grid(row=0, column=columna, padx=(0, 8))
            self._botones_accion.append(boton)

        ttk.Checkbutton(
            marco,
            text="Calcular solo con el consenso del grupo",
            variable=self.solo_consenso,
            command=self._refrescar_resumen_si_hay_datos,
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))

        ttk.Label(
            marco,
            text="«Plantilla para enviar» guarda un Excel solo con la hoja TALLER; "
            "el material derivado va en el reporte.",
            foreground="#52514e",
            wraplength=620,
            justify="left",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))

    def _construir_seccion_resumen(self) -> None:
        marco = ttk.LabelFrame(self, text="3. Resumen", padding=10)
        marco.grid(row=3, column=0, sticky="nsew")
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(1, weight=1)

        self.etiqueta_cobertura = ttk.Label(marco, text="Todavía no se ha importado nada.")
        self.etiqueta_cobertura.grid(row=0, column=0, sticky="w", pady=(0, 8))

        columnas = ("cultura", "pasado", "actual", "brecha")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings", height=6)
        for col, titulo, ancho in (
            ("cultura", "Tipo de cultura", 220),
            ("pasado", "PASADO", 90),
            ("actual", "ACTUAL", 90),
            ("brecha", "Brecha", 90),
        ):
            self.tabla.heading(col, text=titulo)
            self.tabla.column(col, width=ancho, anchor="w" if col == "cultura" else "center")
        self.tabla.grid(row=1, column=0, sticky="nsew")

        self.boton_abrir = ttk.Button(
            marco, text="Abrir último reporte HTML", command=self._abrir_reporte
        )
        self.boton_abrir.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.boton_abrir.state(["disabled"])

    def _construir_barra_estado(self) -> None:
        barra = ttk.Frame(self)
        barra.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        barra.columnconfigure(0, weight=1)
        ttk.Label(barra, textvariable=self.estado, foreground="#52514e").grid(
            row=0, column=0, sticky="w"
        )
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=120)
        self.progreso.grid(row=0, column=1, sticky="e")

    # -- selección de rutas -------------------------------------------------

    def _elegir_excel(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Selecciona el Excel del taller",
            filetypes=[("Libros de Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")],
        )
        if ruta:
            self.ruta_excel.set(ruta)
            self.estado.set("Archivo seleccionado. Pulsa «Importar taller».")

    def _elegir_bd(self) -> None:
        ruta = filedialog.asksaveasfilename(
            title="Base de datos SQLite",
            defaultextension=".db",
            filetypes=[("SQLite", "*.db"), ("Todos", "*.*")],
        )
        if ruta:
            self.ruta_bd.set(ruta)

    # -- acciones -----------------------------------------------------------

    def _importar(self) -> None:
        ruta = self.ruta_excel.get().strip()
        if not ruta:
            messagebox.showwarning(TITULO, "Primero elige el Excel del taller.")
            return
        if not Path(ruta).exists():
            messagebox.showerror(TITULO, f"No se encuentra el archivo:\n{ruta}")
            return

        def tarea():
            lector = LectorTallerExcel(ruta)
            with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
                resultado = ImportarTallerDesdeExcel(lector, repo).ejecutar()
            return (
                "importado",
                f"Importados {resultado.aspectos} ítems y "
                f"{resultado.calificaciones} calificaciones.",
            )

        self._ejecutar_en_hilo(tarea, "Leyendo el Excel…")

    def _hay_datos_importados(self) -> bool:
        """Evita generar reportes vacíos si aún no se importó nada."""
        if not Path(self.ruta_bd.get()).exists():
            messagebox.showwarning(TITULO, "Primero importa el taller.")
            return False
        with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
            if not repo.listar_aspectos():
                messagebox.showwarning(
                    TITULO, "La base de datos está vacía. Pulsa «Importar taller» primero."
                )
                return False
        return True

    def _generar_html(self) -> None:
        if not self._hay_datos_importados():
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte HTML",
            defaultextension=".html",
            initialfile="reporte.html",
            filetypes=[("Página HTML", "*.html")],
        )
        if not ruta:
            return

        def tarea():
            with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
                reporte = CalcularReporteTaller(repo).ejecutar(
                    solo_consenso=self.solo_consenso.get()
                )
                ExportarReporteTaller(ExportadorReporteHTML()).ejecutar(reporte, ruta)
            self._ultimo_reporte_html = Path(ruta)
            return "reporte", f"Reporte HTML guardado en {ruta}"

        self._ejecutar_en_hilo(tarea, "Generando el reporte HTML…")

    def _generar_excel(self) -> None:
        if not self._hay_datos_importados():
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte Excel",
            defaultextension=".xlsx",
            initialfile="reporte.xlsx",
            filetypes=[("Libro de Excel", "*.xlsx")],
        )
        if not ruta:
            return

        def tarea():
            with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
                reporte = CalcularReporteTaller(repo).ejecutar(
                    solo_consenso=self.solo_consenso.get()
                )
                ExportarReporteTaller(ExportadorReporteExcel()).ejecutar(reporte, ruta)
            return "reporte", f"Reporte Excel guardado en {ruta}"

        self._ejecutar_en_hilo(tarea, "Generando el reporte Excel…")

    def _exportar_plantilla(self) -> None:
        origen = self.ruta_excel.get().strip()
        if not origen or not Path(origen).exists():
            messagebox.showwarning(TITULO, "Primero elige el Excel del taller.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar plantilla para enviar",
            defaultextension=".xlsx",
            initialfile="TALLER para enviar.xlsx",
            filetypes=[("Libro de Excel", "*.xlsx")],
        )
        if not ruta:
            return

        def tarea():
            ExportarPlantillaTaller(ExportadorPlantillaExcel()).ejecutar(origen, ruta)
            return "plantilla", f"Plantilla (solo hoja TALLER) guardada en {ruta}"

        self._ejecutar_en_hilo(tarea, "Preparando la plantilla…")

    def _abrir_reporte(self) -> None:
        if self._ultimo_reporte_html and self._ultimo_reporte_html.exists():
            webbrowser.open(self._ultimo_reporte_html.resolve().as_uri())

    # -- ejecución asíncrona -------------------------------------------------

    def _ejecutar_en_hilo(self, tarea, mensaje: str) -> None:
        self.estado.set(mensaje)
        self.progreso.start(12)
        self._bloquear(True)

        def envoltura():
            try:
                self._cola.put(("ok",) + tarea())
            except Exception as error:  # noqa: BLE001 - se muestra al usuario
                self._cola.put(("error", type(error).__name__, str(error)))

        threading.Thread(target=envoltura, daemon=True).start()

    def _procesar_cola(self) -> None:
        try:
            while True:
                mensaje = self._cola.get_nowait()
                self._atender_mensaje(mensaje)
        except queue.Empty:
            pass
        self.after(100, self._procesar_cola)

    def _atender_mensaje(self, mensaje: tuple) -> None:
        self.progreso.stop()
        self._bloquear(False)

        if mensaje[0] == "error":
            _, tipo, detalle = mensaje
            self.estado.set("Ocurrió un error.")
            messagebox.showerror(TITULO, f"{tipo}\n\n{detalle}")
            return

        _, clase, texto = mensaje
        self.estado.set(texto)
        if clase in {"importado", "reporte"}:
            self._refrescar_resumen()
        if clase == "reporte" and self._ultimo_reporte_html:
            self.boton_abrir.state(["!disabled"])

    def _bloquear(self, ocupado: bool) -> None:
        estado = ["disabled"] if ocupado else ["!disabled"]
        for boton in self._botones_accion:
            boton.state(estado)

    # -- resumen en pantalla --------------------------------------------------

    def _refrescar_habilitacion(self) -> None:
        self._bloquear(False)

    def _refrescar_resumen_si_hay_datos(self) -> None:
        if Path(self.ruta_bd.get()).exists():
            self._refrescar_resumen()

    def _refrescar_resumen(self) -> None:
        ruta_bd = self.ruta_bd.get()
        if not Path(ruta_bd).exists():
            return
        try:
            with RepositorioTallerSQLite(ruta_bd) as repo:
                reporte = CalcularReporteTaller(repo).ejecutar(
                    solo_consenso=self.solo_consenso.get()
                )
        except Exception as error:  # noqa: BLE001
            messagebox.showerror(TITULO, f"No se pudo calcular el resumen:\n{error}")
            return

        d = reporte.diagnostico
        self.etiqueta_cobertura.config(
            text=(
                f"{reporte.base_calculo} · {d.aspectos_calificados} de {d.total_aspectos} ítems "
                f"calificados ({d.porcentaje_cobertura:.0f}% de cobertura) · "
                f"{d.respuestas_consenso} respuestas de consenso, "
                f"{d.respuestas_individuales} individuales"
            )
        )

        self.tabla.delete(*self.tabla.get_children())
        for tipo_cultura in TipoCultura:
            pasado = reporte.resumen.para(tipo_cultura, Momento.PASADO)
            actual = reporte.resumen.para(tipo_cultura, Momento.ACTUAL)
            self.tabla.insert(
                "",
                "end",
                values=(
                    tipo_cultura.value,
                    f"{pasado.promedio_ponderado:.2f}" if pasado else "s/d",
                    f"{actual.promedio_ponderado:.2f}" if actual else "s/d",
                    f"{reporte.resumen.brecha(tipo_cultura):+.2f}"
                    if pasado and actual
                    else "s/d",
                ),
            )


def lanzar_gui() -> int:
    raiz = tk.Tk()
    raiz.title(TITULO)
    raiz.minsize(720, 560)
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    AplicacionTaller(raiz)
    raiz.mainloop()
    return 0
