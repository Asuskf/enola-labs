"""Interfaz gráfica de escritorio (tkinter) del taller de cultura.

Es un **adaptador primario**: igual que la CLI, se limita a invocar los
casos de uso de `taller_cultura.application`. No contiene ninguna regla de
negocio; si algo hay que calcular, lo calcula el dominio.

El flujo sigue el orden natural del trabajo:

    1. ¿Taller nuevo o nueva versión de uno anterior?
       · nuevo          → se piden empresa y fecha
       · nueva versión  → se elige la empresa ya registrada y se pide la fecha
    2. Se elige el archivo y **se valida antes de procesar**.
    3. Se procesa y se genera el reporte de la sesión.
    4. Si la empresa tiene dos o más sesiones, se habilita el comparativo.

Usa solo tkinter (biblioteca estándar), así que no añade dependencias. Las
tareas lentas corren en un hilo aparte para que la ventana no se congele.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from taller_cultura.application.use_cases import (
    ArchivoNoProcesable,
    CalcularReporteTaller,
    CompararSesiones,
    ExportarPlantillaTaller,
    ExportarReporteComparativo,
    ExportarReporteTaller,
    ImportarSesionTaller,
    ListarSesiones,
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

TITULO = "Taller de cultura organizacional"
BD_POR_DEFECTO = Path("data") / "talleres.db"

# Los filtros de archivo se declaran con una tupla de extensiones y con "*"
# como comodín: `"*.xlsx *.xlsm"` en una sola cadena y `"*.*"` funcionan en
# Windows, pero en macOS y Linux `*.*` deja fuera los archivos sin punto.
FILTROS_EXCEL = (("Libros de Excel", ("*.xlsx", "*.xlsm")), ("Todos los archivos", "*"))
FILTROS_HTML = (("Página HTML", "*.html"), ("Todos los archivos", "*"))
FILTROS_XLSX = (("Libro de Excel", "*.xlsx"), ("Todos los archivos", "*"))

MODO_NUEVO = "nuevo"
MODO_VERSION = "version"


class AplicacionTaller(ttk.Frame):
    """Ventana principal."""

    def __init__(self, raiz: tk.Tk) -> None:
        super().__init__(raiz, padding=12)
        self.raiz = raiz
        self.grid(sticky="nsew")
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        self.ruta_bd = tk.StringVar(value=str(BD_POR_DEFECTO))
        self.modo = tk.StringVar(value=MODO_NUEVO)
        self.empresa = tk.StringVar()
        self.empresa_existente = tk.StringVar()
        self.fecha = tk.StringVar(value=date.today().isoformat())
        self.ruta_excel = tk.StringVar()
        self.solo_consenso = tk.BooleanVar(value=True)
        self.estado = tk.StringVar(value="Indica si es un taller nuevo o una nueva versión.")

        self._cola: queue.Queue = queue.Queue()
        self._sesion_actual_id: int | None = None
        self._ultimo_html: Path | None = None
        self._botones: list[ttk.Button] = []

        self._construir_seccion_taller()
        self._construir_seccion_archivo()
        self._construir_seccion_acciones()
        self._construir_seccion_resultados()
        self._construir_barra_estado()

        self._al_cambiar_modo()
        self.after(100, self._procesar_cola)

    # -- 1. tipo de taller ---------------------------------------------------

    def _construir_seccion_taller(self) -> None:
        marco = ttk.LabelFrame(self, text="1. ¿Qué vas a procesar?", padding=10)
        marco.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        marco.columnconfigure(1, weight=1)

        opciones = ttk.Frame(marco)
        opciones.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Radiobutton(
            opciones, text="Taller nuevo", value=MODO_NUEVO,
            variable=self.modo, command=self._al_cambiar_modo,
        ).grid(row=0, column=0, padx=(0, 16))
        ttk.Radiobutton(
            opciones, text="Nueva versión de un taller anterior", value=MODO_VERSION,
            variable=self.modo, command=self._al_cambiar_modo,
        ).grid(row=0, column=1)

        self.etiqueta_empresa = ttk.Label(marco, text="Empresa:")
        self.etiqueta_empresa.grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.entrada_empresa = ttk.Entry(marco, textvariable=self.empresa)
        self.entrada_empresa.grid(row=1, column=1, sticky="ew")
        self.combo_empresa = ttk.Combobox(
            marco, textvariable=self.empresa_existente, state="readonly", values=[]
        )
        self.combo_empresa.grid(row=1, column=1, sticky="ew")
        self.combo_empresa.bind("<<ComboboxSelected>>", lambda _e: self._refrescar_sesiones())

        ttk.Label(marco, text="Fecha del taller:").grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0)
        )
        ttk.Entry(marco, textvariable=self.fecha, width=16).grid(
            row=2, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Label(marco, text="(AAAA-MM-DD)", foreground="#898781").grid(
            row=2, column=2, sticky="w", padx=(8, 0), pady=(8, 0)
        )

        self.etiqueta_historial = ttk.Label(marco, text="", foreground="#52514e", wraplength=620)
        self.etiqueta_historial.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

    # -- 2. archivo ------------------------------------------------------------

    def _construir_seccion_archivo(self) -> None:
        marco = ttk.LabelFrame(self, text="2. Archivo del taller", padding=10)
        marco.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        marco.columnconfigure(1, weight=1)

        ttk.Label(marco, text="Excel:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(marco, textvariable=self.ruta_excel).grid(row=0, column=1, sticky="ew")
        ttk.Button(marco, text="Examinar…", command=self._elegir_excel).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(marco, text="Validar", command=self._validar).grid(row=0, column=3, padx=(8, 0))

        self.etiqueta_validacion = ttk.Label(
            marco, text="El archivo se valida antes de procesarlo.",
            foreground="#52514e", wraplength=620, justify="left",
        )
        self.etiqueta_validacion.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

    # -- 3. acciones ------------------------------------------------------------

    def _construir_seccion_acciones(self) -> None:
        marco = ttk.LabelFrame(self, text="3. Procesar y reportar", padding=10)
        marco.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        acciones = (
            ("Procesar taller", self._importar),
            ("Reporte HTML", self._reporte_html),
            ("Reporte Excel", self._reporte_excel),
            ("Comparar versiones", self._comparar),
            ("Plantilla para enviar", self._plantilla),
        )
        for columna, (texto, comando) in enumerate(acciones):
            boton = ttk.Button(marco, text=texto, command=comando)
            boton.grid(row=0, column=columna, padx=(0, 6))
            self._botones.append(boton)

        ttk.Checkbutton(
            marco, text="Calcular solo con el consenso del grupo",
            variable=self.solo_consenso, command=self._refrescar_resumen,
        ).grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))

        ttk.Label(
            marco,
            text="«Plantilla para enviar» guarda un Excel solo con la hoja TALLER; "
            "el material derivado va en el reporte.",
            foreground="#52514e", wraplength=620, justify="left",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))

    # -- 4. resultados -----------------------------------------------------------

    def _construir_seccion_resultados(self) -> None:
        marco = ttk.LabelFrame(self, text="4. Resultados", padding=10)
        marco.grid(row=3, column=0, sticky="nsew")
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(1, weight=1)

        self.etiqueta_cobertura = ttk.Label(marco, text="Todavía no se ha procesado ningún taller.")
        self.etiqueta_cobertura.grid(row=0, column=0, sticky="w", pady=(0, 8))

        # Las columnas se rearman al refrescar: con una sola medición no se
        # muestran PASADO/ACTUAL/Brecha sino un único promedio.
        self.tabla = ttk.Treeview(marco, show="headings", height=6)
        self.tabla.grid(row=1, column=0, sticky="nsew")
        self._configurar_columnas(distingue_momentos=False)

        self.boton_abrir = ttk.Button(marco, text="Abrir último reporte", command=self._abrir)
        self.boton_abrir.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.boton_abrir.state(["disabled"])

    def _construir_barra_estado(self) -> None:
        barra = ttk.Frame(self)
        barra.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        barra.columnconfigure(0, weight=1)
        ttk.Label(barra, textvariable=self.estado, foreground="#52514e", wraplength=560).grid(
            row=0, column=0, sticky="w"
        )
        self.progreso = ttk.Progressbar(barra, mode="indeterminate", length=120)
        self.progreso.grid(row=0, column=1, sticky="e")

    # -- modo nuevo / nueva versión -----------------------------------------------

    def _al_cambiar_modo(self) -> None:
        es_nuevo = self.modo.get() == MODO_NUEVO
        if es_nuevo:
            self.combo_empresa.grid_remove()
            self.entrada_empresa.grid()
            self.etiqueta_empresa.config(text="Empresa:")
            self.etiqueta_historial.config(text="")
        else:
            self.entrada_empresa.grid_remove()
            self.combo_empresa.grid()
            self.etiqueta_empresa.config(text="Empresa registrada:")
            self._cargar_empresas()
        self._refrescar_sesiones()

    def _cargar_empresas(self) -> None:
        empresas = sorted({s.empresa for s in self._sesiones()})
        self.combo_empresa.config(values=empresas)
        if empresas and not self.empresa_existente.get():
            self.empresa_existente.set(empresas[0])
        if not empresas:
            self.etiqueta_historial.config(
                text="Todavía no hay talleres registrados: procesa uno como «Taller nuevo» primero."
            )

    def _sesiones(self, empresa: str | None = None):
        if not Path(self.ruta_bd.get()).exists():
            return []
        with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
            return ListarSesiones(repo).ejecutar(empresa)

    def _empresa_elegida(self) -> str:
        if self.modo.get() == MODO_NUEVO:
            return self.empresa.get().strip()
        return self.empresa_existente.get().strip()

    def _refrescar_sesiones(self) -> None:
        empresa = self._empresa_elegida()
        if self.modo.get() == MODO_VERSION and empresa:
            sesiones = self._sesiones(empresa)
            if sesiones:
                detalle = ", ".join(f"v{s.numero_version} ({s.fecha_taller})" for s in sesiones)
                self.etiqueta_historial.config(
                    text=f"«{empresa}» tiene {len(sesiones)} sesión(es): {detalle}. "
                    f"La que proceses ahora será la v{max(s.numero_version for s in sesiones) + 1}."
                )

    # -- selección y validación ------------------------------------------------------

    def _elegir_excel(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Selecciona el Excel del taller",
            filetypes=FILTROS_EXCEL,
        )
        if not ruta:
            return
        self.ruta_excel.set(ruta)
        self.estado.set("Archivo seleccionado. Conviene validarlo antes de procesar.")
        if self.modo.get() == MODO_NUEVO and not self.empresa.get().strip():
            detectada = LectorTallerExcel(ruta).leer_nombre_empresa()
            if detectada:
                self.empresa.set(detectada)

    def _validar(self) -> None:
        ruta = self.ruta_excel.get().strip()
        if not self._archivo_listo(ruta):
            return

        def tarea():
            resultado = ValidarArchivoTaller(LectorTallerExcel(ruta)).ejecutar()
            return "validacion", resultado

        self._en_hilo(tarea, "Validando el archivo…")

    def _mostrar_validacion(self, resultado) -> None:
        lineas = [resultado.resumen] + [f"• {h.mensaje}" for h in resultado.hallazgos]
        self.etiqueta_validacion.config(
            text="\n".join(lineas),
            foreground="#d03b3b" if not resultado.es_procesable else "#52514e",
        )
        self.estado.set(resultado.resumen)

    # -- acciones ---------------------------------------------------------------------

    def _archivo_listo(self, ruta: str) -> bool:
        if not ruta:
            messagebox.showwarning(TITULO, "Primero elige el Excel del taller.")
            return False
        if not Path(ruta).exists():
            messagebox.showerror(TITULO, f"No se encuentra el archivo:\n{ruta}")
            return False
        return True

    def _importar(self) -> None:
        ruta = self.ruta_excel.get().strip()
        if not self._archivo_listo(ruta):
            return

        empresa = self._empresa_elegida()
        if not empresa:
            messagebox.showwarning(
                TITULO,
                "Falta la empresa: escríbela (taller nuevo) o elígela de la lista "
                "(nueva versión).",
            )
            return
        try:
            fecha_taller = date.fromisoformat(self.fecha.get().strip())
        except ValueError:
            messagebox.showwarning(
                TITULO, "La fecha no es válida. Usa el formato AAAA-MM-DD, por ejemplo 2026-03-14."
            )
            return

        def tarea():
            with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
                resultado = ImportarSesionTaller(LectorTallerExcel(ruta), repo).ejecutar(
                    empresa=empresa, fecha_taller=fecha_taller, archivo_origen=ruta
                )
            return "importado", resultado

        self._en_hilo(tarea, "Validando y procesando el taller…")

    def _reporte_html(self) -> None:
        self._exportar_reporte(
            ExportadorReporteHTML(), "reporte.html", FILTROS_HTML, ".html"
        )

    def _reporte_excel(self) -> None:
        self._exportar_reporte(
            ExportadorReporteExcel(), "reporte.xlsx", FILTROS_XLSX, ".xlsx"
        )

    def _exportar_reporte(self, exportador, nombre, tipos, extension) -> None:
        if self._sesion_actual_id is None:
            messagebox.showwarning(TITULO, "Primero procesa un taller.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte", defaultextension=extension,
            initialfile=nombre, filetypes=tipos,
        )
        if not ruta:
            return
        sesion_id = self._sesion_actual_id
        solo_consenso = self.solo_consenso.get()

        def tarea():
            with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
                reporte = CalcularReporteTaller(repo).ejecutar(
                    sesion_id, solo_consenso=solo_consenso
                )
                ExportarReporteTaller(exportador).ejecutar(reporte, ruta)
            return "exportado", Path(ruta)

        self._en_hilo(tarea, "Generando el reporte…")

    def _comparar(self) -> None:
        empresa = self._empresa_elegida()
        sesiones = self._sesiones(empresa) if empresa else []
        if len(sesiones) < 2:
            messagebox.showinfo(
                TITULO,
                "Para comparar hacen falta al menos dos sesiones de la misma empresa.\n\n"
                f"«{empresa or 'sin empresa'}» tiene {len(sesiones)}.",
            )
            return

        eleccion = _DialogoComparar(self, sesiones).resultado
        if eleccion is None:
            return
        antes_id, ahora_id = eleccion

        ruta = filedialog.asksaveasfilename(
            title="Guardar comparativo", defaultextension=".html",
            initialfile="comparativo.html", filetypes=FILTROS_HTML,
        )
        if not ruta:
            return
        solo_consenso = self.solo_consenso.get()

        def tarea():
            with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
                comparativo = CompararSesiones(repo).ejecutar(
                    antes_id, ahora_id, solo_consenso=solo_consenso
                )
                ExportarReporteComparativo(ExportadorComparativoHTML()).ejecutar(comparativo, ruta)
            return "exportado", Path(ruta)

        self._en_hilo(tarea, "Generando el comparativo…")

    def _plantilla(self) -> None:
        ruta_origen = self.ruta_excel.get().strip()
        if not self._archivo_listo(ruta_origen):
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar plantilla para enviar", defaultextension=".xlsx",
            initialfile="TALLER para enviar.xlsx", filetypes=FILTROS_XLSX,
        )
        if not ruta:
            return

        def tarea():
            ExportarPlantillaTaller(ExportadorPlantillaExcel()).ejecutar(ruta_origen, ruta)
            return "plantilla", Path(ruta)

        self._en_hilo(tarea, "Preparando la plantilla…")

    def _abrir(self) -> None:
        if self._ultimo_html and self._ultimo_html.exists():
            webbrowser.open(self._ultimo_html.resolve().as_uri())

    # -- ejecución asíncrona -------------------------------------------------------------

    def _en_hilo(self, tarea, mensaje: str) -> None:
        self.estado.set(mensaje)
        self.progreso.start(12)
        self._bloquear(True)

        def envoltura():
            try:
                self._cola.put(("ok",) + tarea())
            except ArchivoNoProcesable as error:
                self._cola.put(("no_procesable", error.resultado))
            except Exception as error:  # noqa: BLE001 - se muestra al usuario
                self._cola.put(("error", type(error).__name__, str(error)))

        threading.Thread(target=envoltura, daemon=True).start()

    def _procesar_cola(self) -> None:
        try:
            while True:
                self._atender(self._cola.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._procesar_cola)

    def _atender(self, mensaje: tuple) -> None:
        self.progreso.stop()
        self._bloquear(False)
        tipo = mensaje[0]

        if tipo == "error":
            _, clase, detalle = mensaje
            self.estado.set("Ocurrió un error.")
            messagebox.showerror(TITULO, f"{clase}\n\n{detalle}")
            return

        if tipo == "no_procesable":
            resultado = mensaje[1]
            self._mostrar_validacion(resultado)
            messagebox.showerror(
                TITULO,
                "El archivo no se puede procesar:\n\n"
                + "\n".join(f"• {h.mensaje}" for h in resultado.errores),
            )
            return

        _, clase, dato = mensaje
        if clase == "validacion":
            self._mostrar_validacion(dato)
        elif clase == "importado":
            self._sesion_actual_id = dato.sesion.id
            self._mostrar_validacion(dato.validacion)
            self.estado.set(
                f"Sesión #{dato.sesion.id} procesada — {dato.sesion.titulo} · "
                f"{dato.aspectos} ítems, {dato.calificaciones} calificaciones."
            )
            self._cargar_empresas()
            self._refrescar_sesiones()
            self._refrescar_resumen()
        elif clase in {"exportado", "plantilla"}:
            self.estado.set(f"Guardado en {dato}")
            if dato.suffix.lower() in {".html", ".htm"}:
                self._ultimo_html = dato
                self.boton_abrir.state(["!disabled"])

    def _bloquear(self, ocupado: bool) -> None:
        estado = ["disabled"] if ocupado else ["!disabled"]
        for boton in self._botones:
            boton.state(estado)

    # -- resumen en pantalla ----------------------------------------------------------------

    def _configurar_columnas(self, distingue_momentos: bool) -> None:
        if distingue_momentos:
            columnas = (
                ("cultura", "Tipo de cultura", 230, "w"),
                ("pasado", "PASADO", 90, "center"),
                ("actual", "ACTUAL", 90, "center"),
                ("brecha", "Brecha", 90, "center"),
            )
        else:
            columnas = (
                ("cultura", "Tipo de cultura", 300, "w"),
                ("promedio", "Promedio (0-2)", 120, "center"),
            )

        self.tabla.config(columns=[c[0] for c in columnas])
        for clave, titulo, ancho, anchor in columnas:
            self.tabla.heading(clave, text=titulo)
            self.tabla.column(clave, width=ancho, anchor=anchor)

    def _refrescar_resumen(self) -> None:
        if self._sesion_actual_id is None:
            return
        with RepositorioTallerSQLite(self.ruta_bd.get()) as repo:
            reporte = CalcularReporteTaller(repo).ejecutar(
                self._sesion_actual_id, solo_consenso=self.solo_consenso.get()
            )

        d = reporte.diagnostico
        self.etiqueta_cobertura.config(
            text=(
                f"{reporte.sesion.titulo} · {reporte.base_calculo} · "
                f"{d.aspectos_calificados} de {d.total_aspectos} ítems calificados "
                f"({d.porcentaje_cobertura:.0f}%) · {d.respuestas_consenso} de consenso, "
                f"{d.respuestas_individuales} individuales"
            )
        )

        resumen = reporte.resumen
        distingue = resumen.distingue_momentos
        self._configurar_columnas(distingue)
        self.tabla.delete(*self.tabla.get_children())

        for tipo_cultura in TipoCultura:
            if distingue:
                pasado = resumen.para(tipo_cultura, Momento.PASADO)
                actual = resumen.para(tipo_cultura, Momento.ACTUAL)
                valores = (
                    tipo_cultura.value,
                    f"{pasado.promedio_ponderado:.2f}" if pasado else "s/d",
                    f"{actual.promedio_ponderado:.2f}" if actual else "s/d",
                    f"{resumen.brecha(tipo_cultura):+.2f}" if pasado and actual else "s/d",
                )
            else:
                promedio = resumen.promedio(tipo_cultura)
                valores = (
                    tipo_cultura.value,
                    "s/d" if promedio is None else f"{promedio:.2f}",
                )
            self.tabla.insert("", "end", values=valores)


class _DialogoComparar(tk.Toplevel):
    """Pide qué dos sesiones comparar."""

    def __init__(self, padre: tk.Misc, sesiones) -> None:
        super().__init__(padre)
        self.title("Comparar versiones")
        self.resizable(False, False)
        self.resultado: tuple[int, int] | None = None
        self._sesiones = sesiones

        etiquetas = [f"v{s.numero_version} · {s.fecha_taller} (#{s.id})" for s in sesiones]
        marco = ttk.Frame(self, padding=14)
        marco.grid(sticky="nsew")

        ttk.Label(marco, text="Sesión anterior (antes):").grid(row=0, column=0, sticky="w")
        self.combo_antes = ttk.Combobox(marco, values=etiquetas, state="readonly", width=34)
        self.combo_antes.current(0)
        self.combo_antes.grid(row=0, column=1, padx=(10, 0), pady=4)

        ttk.Label(marco, text="Sesión actual (ahora):").grid(row=1, column=0, sticky="w")
        self.combo_ahora = ttk.Combobox(marco, values=etiquetas, state="readonly", width=34)
        self.combo_ahora.current(len(etiquetas) - 1)
        self.combo_ahora.grid(row=1, column=1, padx=(10, 0), pady=4)

        botones = ttk.Frame(marco)
        botones.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(botones, text="Cancelar", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(botones, text="Comparar", command=self._aceptar).grid(row=0, column=1)

        self.transient(padre)
        self.grab_set()
        padre.wait_window(self)

    def _aceptar(self) -> None:
        antes = self._sesiones[self.combo_antes.current()]
        ahora = self._sesiones[self.combo_ahora.current()]
        if antes.id == ahora.id:
            messagebox.showwarning(TITULO, "Elige dos sesiones distintas.", parent=self)
            return
        self.resultado = (antes.id, ahora.id)
        self.destroy()


def _aplicar_tema(raiz: tk.Tk) -> None:
    """Elige el tema nativo de cada plataforma, si está disponible.

    Los temas de ttk dependen del sistema: `vista` solo existe en Windows y
    `aqua` solo en macOS. Se prueba en orden de preferencia y se cae al que
    Tk traiga por defecto, así la ventana se ve correcta en los tres
    sistemas sin ramificar por `sys.platform`.
    """
    estilo = ttk.Style(raiz)
    disponibles = set(estilo.theme_names())
    for tema in ("aqua", "vista", "winnative", "clam", "default"):
        if tema in disponibles:
            try:
                estilo.theme_use(tema)
                return
            except tk.TclError:  # pragma: no cover - depende del Tk instalado
                continue


def lanzar_gui() -> int:
    raiz = tk.Tk()
    raiz.title(TITULO)
    raiz.minsize(780, 640)
    _aplicar_tema(raiz)
    AplicacionTaller(raiz)
    raiz.mainloop()
    return 0
