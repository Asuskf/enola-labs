"""Adaptador de salida: exporta un `ReporteTaller` a un reporte `.html`.

Implementa el puerto `ExportadorReporte`. Genera un archivo HTML autónomo
(sin dependencias externas: CSS y SVG inline, sin CDNs) con:

- Tarjetas KPI (totales del taller) y un resumen ejecutivo con los
  hallazgos más relevantes (mejor cultura actual, mayor progreso, mayor
  retroceso).
- Gráfico de barras agrupadas: promedio ponderado PASADO vs ACTUAL por
  tipo de cultura.
- Gráfico de barras divergente: brecha (ACTUAL - PASADO) por cultura.
- Gráfico de barras apiladas 100%: distribución Bajo/Medio/Alto (R/A/V)
  por cultura y momento.
- Tablas de datos accesibles (siempre presentes, como respaldo de cada
  gráfico) y el desglose por categoría (Tipo de cultura / Comportamientos
  / Símbolos / Sistemas).
- Botón "Descargar como PDF": abre el diálogo de impresión del navegador
  con una hoja de estilos dedicada (`@media print`); el usuario elige
  "Guardar como PDF" ahí. No requiere ninguna librería ni servicio externo.

Paleta y especificaciones de marca siguen la guía de dataviz del proyecto:
colores categóricos fijos (azul/naranja para PASADO/ACTUAL), rampa
secuencial de un solo tono para la escala ordinal Bajo/Medio/Alto, el par
divergente azul/rojo para la brecha, y la paleta de estado (verde/rojo)
reservada para los hallazgos de progreso/retroceso.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from taller_cultura.application.ports import ExportadorReporte
from taller_cultura.application.use_cases import ReporteTaller
from taller_cultura.domain.model import CategoriaAspecto, Momento, TipoCultura, Valoracion
from taller_cultura.domain.services import ResumenTaller

# -- paleta (paridad con la skill de dataviz del proyecto) -----------------

COLOR_PASADO = "#2a78d6"  # categórico slot 1 (azul)
COLOR_ACTUAL = "#eb6834"  # categórico slot 2 (naranja)
COLOR_POSITIVO = "#2a78d6"  # brecha que mejora (par divergente, polo azul)
COLOR_NEGATIVO = "#e34948"  # brecha que retrocede (par divergente, polo rojo)
COLOR_BAJO = "#86b6ef"  # rampa secuencial azul, escalón 250 (ordinal, más claro)
COLOR_MEDIO = "#2a78d6"  # escalón 450
COLOR_ALTO = "#104281"  # escalón 650 (ordinal, más oscuro)
COLOR_BUENO = "#0ca30c"  # paleta de estado: good
COLOR_CRITICO = "#d03b3b"  # paleta de estado: critical

MAX_ESCALA_PROMEDIO = 2.0


def _escapar(texto: str) -> str:
    return (
        texto.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class ExportadorReporteHTML(ExportadorReporte):
    """Genera un reporte `.html` autocontenido con el resumen del taller."""

    def exportar_reporte(self, reporte: ReporteTaller, ruta_destino: str) -> None:
        html = self._construir_html(reporte)
        ruta = Path(ruta_destino)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(html, encoding="utf-8")

    # -- ensamblado ---------------------------------------------------

    def _construir_html(self, reporte: ReporteTaller) -> str:
        kpis = self._construir_kpis(reporte)
        destacados = self._construir_destacados(reporte.resumen)
        grafico_promedios = self._grafico_barras_agrupadas(reporte.resumen)
        grafico_brecha = self._grafico_brecha(reporte.resumen)
        grafico_distribucion = self._grafico_distribucion(reporte.resumen)
        tabla_resumen = self._tabla_resumen(reporte.resumen)
        tabla_detalle = self._tabla_detalle_categoria(reporte.detalle_categoria)
        generado_en = datetime.now().strftime("%Y-%m-%d %H:%M")

        return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_escapar(reporte.titulo)} — Taller de cultura organizacional</title>
<style>{_CSS}</style>
</head>
<body>
<div class="viz-root">
  <header class="encabezado">
    <div>
      <h1>{_escapar(reporte.titulo)}</h1>
      <p class="subtitulo">Taller de diagnóstico de cultura organizacional</p>
      <p class="marca-tiempo">Generado el {generado_en}</p>
    </div>
    <div class="acciones-encabezado">
      <button class="boton boton-pdf" id="boton-pdf" type="button">⬇ Descargar como PDF</button>
      <button class="boton boton-tema" id="boton-tema" type="button" aria-label="Cambiar tema claro/oscuro">🌓</button>
    </div>
  </header>

  <section class="kpis">
    {kpis}
  </section>

  <section class="seccion">
    <h2>Aspectos destacados</h2>
    {destacados}
  </section>

  <section class="seccion">
    <h2>Promedio ponderado por tipo de cultura</h2>
    <p class="ayuda">Escala 0 (bajo) a 2 (alto), comparando el momento PASADO contra el ACTUAL.</p>
    {grafico_promedios}
  </section>

  <section class="seccion">
    <h2>Brecha ACTUAL − PASADO</h2>
    <p class="ayuda">Diferencia del promedio ponderado. Azul = mejora, rojo = retrocede.</p>
    {grafico_brecha}
  </section>

  <section class="seccion">
    <h2>Distribución de valoraciones (Bajo / Medio / Alto)</h2>
    <p class="ayuda">Proporción de respuestas R (bajo), A (medio) y V (alto) por cultura y momento.</p>
    {grafico_distribucion}
  </section>

  <section class="seccion">
    <h2>Tabla de datos</h2>
    {tabla_resumen}
  </section>

  <section class="seccion">
    <h2>Detalle por categoría</h2>
    <p class="ayuda">Mismo cálculo, desglosado por categoría del taller (Tipo de cultura, Comportamientos, Símbolos, Sistemas).</p>
    {tabla_detalle}
  </section>

  <footer class="pie">Generado automáticamente por el ETL del taller de cultura organizacional.</footer>
</div>
<script>{_JS}</script>
</body>
</html>
"""

    # -- KPIs -----------------------------------------------------------

    @staticmethod
    def _construir_kpis(reporte: ReporteTaller) -> str:
        total_respuestas = sum(r.total for r in reporte.resumen.resumenes)
        culturas_con_datos = len({r.tipo_cultura for r in reporte.resumen.resumenes})
        categorias_con_datos = len({d.categoria for d in reporte.detalle_categoria})
        tiles = [
            ("Respuestas registradas", str(total_respuestas)),
            ("Calificadores participantes", str(reporte.calificadores_participantes)),
            ("Tipos de cultura con datos", f"{culturas_con_datos} / {len(TipoCultura)}"),
            ("Categorías evaluadas", f"{categorias_con_datos} / {len(CategoriaAspecto)}"),
        ]
        return "\n".join(
            f'<div class="kpi"><span class="kpi-valor">{valor}</span>'
            f'<span class="kpi-etiqueta">{_escapar(etiqueta)}</span></div>'
            for etiqueta, valor in tiles
        )

    # -- resumen ejecutivo -------------------------------------------------

    @staticmethod
    def _construir_destacados(resumen: ResumenTaller) -> str:
        mejor_actual: tuple[TipoCultura, float] | None = None
        brechas_validas: list[tuple[TipoCultura, float]] = []

        for tipo_cultura in TipoCultura:
            actual = resumen.para(tipo_cultura, Momento.ACTUAL)
            pasado = resumen.para(tipo_cultura, Momento.PASADO)
            if actual is not None:
                if mejor_actual is None or actual.promedio_ponderado > mejor_actual[1]:
                    mejor_actual = (tipo_cultura, actual.promedio_ponderado)
            if actual is not None and pasado is not None:
                brechas_validas.append((tipo_cultura, round(actual.promedio_ponderado - pasado.promedio_ponderado, 2)))

        mayor_progreso = max(brechas_validas, key=lambda t: t[1], default=None)
        if mayor_progreso is not None and mayor_progreso[1] <= 0:
            mayor_progreso = None
        mayor_retroceso = min(brechas_validas, key=lambda t: t[1], default=None)
        if mayor_retroceso is not None and mayor_retroceso[1] >= 0:
            mayor_retroceso = None

        tarjetas = []
        if mejor_actual:
            tipo_cultura, valor = mejor_actual
            tarjetas.append(
                _tarjeta_destacado("★", None, "Mejor cultura hoy (ACTUAL)", tipo_cultura.value, f"{valor:.2f} / 2.00")
            )
        if mayor_progreso:
            tipo_cultura, valor = mayor_progreso
            tarjetas.append(
                _tarjeta_destacado("▲", COLOR_BUENO, "Mayor progreso", tipo_cultura.value, f"{valor:+.2f}")
            )
        if mayor_retroceso:
            tipo_cultura, valor = mayor_retroceso
            tarjetas.append(
                _tarjeta_destacado("▼", COLOR_CRITICO, "Mayor retroceso", tipo_cultura.value, f"{valor:+.2f}")
            )

        if not tarjetas:
            return '<p class="ayuda">Todavía no hay suficientes calificaciones para destacar hallazgos.</p>'
        return f'<div class="destacados">{"".join(tarjetas)}</div>'

    # -- gráfico A: barras agrupadas PASADO/ACTUAL -----------------------

    @staticmethod
    def _grafico_barras_agrupadas(resumen: ResumenTaller) -> str:
        label_w, chart_w, pad_right = 190, 420, 50
        bar_h, bar_gap, group_gap = 16, 4, 14
        top_pad = 28
        ancho = label_w + chart_w + pad_right + 20
        filas_svg = []
        y = top_pad
        for tipo_cultura in TipoCultura:
            pasado = resumen.para(tipo_cultura, Momento.PASADO)
            actual = resumen.para(tipo_cultura, Momento.ACTUAL)
            filas_svg.append(
                f'<text x="10" y="{y + bar_h + bar_gap / 2 + 4}" class="etiqueta-fila">'
                f"{_escapar(tipo_cultura.value)}</text>"
            )
            for r, color in ((pasado, COLOR_PASADO), (actual, COLOR_ACTUAL)):
                valor = r.promedio_ponderado if r else 0.0
                ancho_barra = (valor / MAX_ESCALA_PROMEDIO) * chart_w if r else 0
                texto_valor = f"{valor:.2f}" if r else "s/d"
                x_texto = label_w + ancho_barra + 6
                filas_svg.append(
                    f'<rect x="{label_w}" y="{y}" width="{max(ancho_barra, 1) if r else 0}" '
                    f'height="{bar_h}" rx="4" class="barra" fill="{color}"><title>'
                    f"{_escapar(tipo_cultura.value)} — {texto_valor}</title></rect>"
                )
                if r:
                    filas_svg.append(
                        f'<text x="{x_texto}" y="{y + bar_h - 3}" class="valor-barra">{texto_valor}</text>'
                    )
                y += bar_h + bar_gap
            y += group_gap
        alto = y + 10

        ticks = []
        for i in range(3):  # 0, 1, 2
            x = label_w + (i / (MAX_ESCALA_PROMEDIO)) * chart_w if MAX_ESCALA_PROMEDIO else label_w
            ticks.append(
                f'<line x1="{x}" y1="{top_pad - 10}" x2="{x}" y2="{alto - 10}" class="linea-guia" />'
                f'<text x="{x}" y="{top_pad - 14}" class="etiqueta-eje" text-anchor="middle">{i}</text>'
            )

        leyenda = (
            '<div class="leyenda">'
            f'<span class="leyenda-item"><i style="background:{COLOR_PASADO}"></i>PASADO</span>'
            f'<span class="leyenda-item"><i style="background:{COLOR_ACTUAL}"></i>ACTUAL</span>'
            "</div>"
        )
        svg = (
            f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            f'aria-label="Promedio ponderado por tipo de cultura, PASADO versus ACTUAL">'
            + "".join(ticks)
            + "".join(filas_svg)
            + "</svg>"
        )
        return leyenda + svg

    # -- gráfico B: brecha divergente -------------------------------------

    @staticmethod
    def _grafico_brecha(resumen: ResumenTaller) -> str:
        label_w, half_w, pad = 190, 210, 50
        bar_h, gap, top_pad = 20, 12, 24
        ancho = label_w + 2 * half_w + pad
        centro_x = label_w + half_w

        brechas = {tc: resumen.brecha(tc) for tc in TipoCultura}
        maximo = max(0.5, max(abs(v) for v in brechas.values()))

        filas_svg = []
        y = top_pad
        for tipo_cultura in TipoCultura:
            valor = brechas[tipo_cultura]
            ancho_barra = (abs(valor) / maximo) * half_w
            color = COLOR_POSITIVO if valor >= 0 else COLOR_NEGATIVO
            x_barra = centro_x if valor >= 0 else centro_x - ancho_barra
            filas_svg.append(
                f'<text x="10" y="{y + bar_h / 2 + 4}" class="etiqueta-fila">'
                f"{_escapar(tipo_cultura.value)}</text>"
            )
            filas_svg.append(
                f'<rect x="{x_barra}" y="{y}" width="{max(ancho_barra, 1)}" height="{bar_h}" '
                f'rx="4" class="barra" fill="{color}"><title>{_escapar(tipo_cultura.value)} — '
                f'{valor:+.2f}</title></rect>'
            )
            x_texto = x_barra + ancho_barra + 6 if valor >= 0 else x_barra - 6
            anchor = "start" if valor >= 0 else "end"
            filas_svg.append(
                f'<text x="{x_texto}" y="{y + bar_h - 5}" class="valor-barra" '
                f'text-anchor="{anchor}">{valor:+.2f}</text>'
            )
            y += bar_h + gap
        alto = y + 6

        linea_cero = f'<line x1="{centro_x}" y1="{top_pad - 8}" x2="{centro_x}" y2="{alto - 6}" class="linea-cero" />'
        svg = (
            f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            f'aria-label="Brecha entre el promedio ACTUAL y el promedio PASADO por tipo de cultura">'
            + linea_cero
            + "".join(filas_svg)
            + "</svg>"
        )
        return svg

    # -- gráfico C: distribución 100% apilada ------------------------------

    @staticmethod
    def _grafico_distribucion(resumen: ResumenTaller) -> str:
        label_w, chart_w, pad = 190, 420, 30
        bar_h, gap, top_pad = 16, 8, 20
        ancho = label_w + chart_w + pad

        filas_svg = []
        y = top_pad
        for r in resumen.resumenes:
            etiqueta = f"{r.tipo_cultura.value} · {r.momento.value}"
            filas_svg.append(
                f'<text x="10" y="{y + bar_h / 2 + 4}" class="etiqueta-fila etiqueta-fila--chica">'
                f"{_escapar(etiqueta)}</text>"
            )
            if r.total == 0:
                filas_svg.append(
                    f'<text x="{label_w}" y="{y + bar_h - 4}" class="valor-barra">sin datos</text>'
                )
                y += bar_h + gap
                continue

            x = label_w
            segmentos = (
                (r.conteo_por_valoracion.get(Valoracion.BAJO, 0), COLOR_BAJO, "Bajo (R)"),
                (r.conteo_por_valoracion.get(Valoracion.MEDIO, 0), COLOR_MEDIO, "Medio (A)"),
                (r.conteo_por_valoracion.get(Valoracion.ALTO, 0), COLOR_ALTO, "Alto (V)"),
            )
            for cantidad, color, nombre in segmentos:
                if cantidad == 0:
                    continue
                ancho_segmento = (cantidad / r.total) * chart_w
                filas_svg.append(
                    f'<rect x="{x:.1f}" y="{y}" width="{max(ancho_segmento - 2, 1):.1f}" '
                    f'height="{bar_h}" rx="3" class="barra" fill="{color}">'
                    f"<title>{_escapar(etiqueta)} — {nombre}: {cantidad}/{r.total}</title></rect>"
                )
                x += ancho_segmento
            y += bar_h + gap
        alto = y + 6

        leyenda = (
            '<div class="leyenda">'
            f'<span class="leyenda-item"><i style="background:{COLOR_BAJO}"></i>Bajo (R)</span>'
            f'<span class="leyenda-item"><i style="background:{COLOR_MEDIO}"></i>Medio (A)</span>'
            f'<span class="leyenda-item"><i style="background:{COLOR_ALTO}"></i>Alto (V)</span>'
            "</div>"
        )
        svg = (
            f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            f'aria-label="Distribución de valoraciones bajo, medio y alto por cultura y momento">'
            + "".join(filas_svg)
            + "</svg>"
        )
        return leyenda + svg

    # -- tablas accesibles -------------------------------------------------

    @staticmethod
    def _tabla_resumen(resumen: ResumenTaller) -> str:
        filas = []
        for r in resumen.resumenes:
            filas.append(
                "<tr>"
                f"<td>{_escapar(r.tipo_cultura.value)}</td>"
                f"<td>{_escapar(r.momento.value)}</td>"
                f"<td>{r.total}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.BAJO, 0)}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.MEDIO, 0)}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.ALTO, 0)}</td>"
                f"<td>{r.promedio_ponderado:.2f}</td>"
                f"<td>{r.porcentaje_valor_alto:.1f}%</td>"
                "</tr>"
            )
        return (
            '<div class="tabla-envoltorio"><table class="tabla">'
            "<thead><tr><th>Tipo de cultura</th><th>Momento</th><th>Total</th>"
            "<th>Bajo (R)</th><th>Medio (A)</th><th>Alto (V)</th>"
            "<th>Promedio (0-2)</th><th>% Alto</th></tr></thead>"
            f"<tbody>{''.join(filas)}</tbody></table></div>"
        )

    @staticmethod
    def _tabla_detalle_categoria(detalle) -> str:
        filas = []
        for r in detalle:
            filas.append(
                "<tr>"
                f"<td>{_escapar(r.categoria.value)}</td>"
                f"<td>{_escapar(r.tipo_cultura.value)}</td>"
                f"<td>{_escapar(r.momento.value)}</td>"
                f"<td>{r.total}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.BAJO, 0)}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.MEDIO, 0)}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.ALTO, 0)}</td>"
                f"<td>{r.promedio_ponderado:.2f}</td>"
                "</tr>"
            )
        if not filas:
            return '<p class="ayuda">No hay calificaciones registradas todavía.</p>'
        return (
            '<div class="tabla-envoltorio"><table class="tabla">'
            "<thead><tr><th>Categoría</th><th>Tipo de cultura</th><th>Momento</th>"
            "<th>Total</th><th>Bajo (R)</th><th>Medio (A)</th><th>Alto (V)</th>"
            "<th>Promedio (0-2)</th></tr></thead>"
            f"<tbody>{''.join(filas)}</tbody></table></div>"
        )


def _tarjeta_destacado(icono: str, color: str | None, etiqueta: str, cultura: str, valor: str) -> str:
    estilo_icono = f' style="color:{color}"' if color else ""
    return (
        '<div class="destacado">'
        f'<span class="destacado-icono"{estilo_icono}>{icono}</span>'
        '<div class="destacado-texto">'
        f'<span class="destacado-etiqueta">{_escapar(etiqueta)}</span>'
        f'<span class="destacado-cultura">{_escapar(cultura)}</span>'
        f'<span class="destacado-valor">{_escapar(valor)}</span>'
        "</div></div>"
    )


_CSS = """
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page-plane);
  color: var(--text-primary);
}
.viz-root {
  color-scheme: light;
  --page-plane:      #f9f9f7;
  --surface-1:       #fcfcfb;
  --text-primary:    #0b0b0b;
  --text-secondary:  #52514e;
  --text-muted:      #898781;
  --gridline:        #e1e0d9;
  --baseline:        #c3c2b7;
  --border:          rgba(11,11,11,0.10);
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --page-plane:      #0d0d0d;
    --surface-1:       #1a1a19;
    --text-primary:    #ffffff;
    --text-secondary:  #c3c2b7;
    --text-muted:      #898781;
    --gridline:        #2c2c2a;
    --baseline:        #383835;
    --border:          rgba(255,255,255,0.10);
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --page-plane:      #0d0d0d;
  --surface-1:       #1a1a19;
  --text-primary:    #ffffff;
  --text-secondary:  #c3c2b7;
  --text-muted:      #898781;
  --gridline:        #2c2c2a;
  --baseline:        #383835;
  --border:          rgba(255,255,255,0.10);
}
body { background: var(--page-plane); }
.encabezado { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.encabezado h1 { margin: 0 0 4px; font-size: 1.6rem; }
.subtitulo { margin: 0; color: var(--text-secondary); }
.marca-tiempo { margin: 4px 0 0; color: var(--text-muted); font-size: 0.8rem; }
.acciones-encabezado { display: flex; gap: 8px; flex-shrink: 0; }
.boton {
  border: 1px solid var(--border); background: var(--surface-1); color: var(--text-primary);
  border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 0.85rem;
  font-family: inherit; white-space: nowrap;
}
.boton:hover { filter: brightness(0.97); }
.boton-tema { font-size: 1rem; padding: 6px 10px; }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 8px; }
.kpi {
  flex: 1 1 180px; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 4px;
}
.kpi-valor { font-size: 1.6rem; font-weight: 600; }
.kpi-etiqueta { color: var(--text-secondary); font-size: 0.85rem; }
.seccion {
  margin-top: 24px; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px;
}
.seccion h2 { margin: 0 0 4px; font-size: 1.1rem; }
.ayuda { color: var(--text-secondary); margin-top: 0; font-size: 0.9rem; }
.grafico { width: 100%; height: auto; display: block; margin-top: 8px; }
.barra { transition: opacity 0.15s ease; }
.barra:hover { opacity: 0.8; }
.linea-guia { stroke: var(--gridline); stroke-width: 1; }
.linea-cero { stroke: var(--baseline); stroke-width: 1.5; }
.etiqueta-fila { fill: var(--text-secondary); font-size: 11px; }
.etiqueta-fila--chica { font-size: 10px; }
.etiqueta-eje { fill: var(--text-muted); font-size: 10px; }
.valor-barra { fill: var(--text-primary); font-size: 10px; font-variant-numeric: tabular-nums; }
.leyenda { display: flex; gap: 16px; margin-top: 8px; font-size: 0.85rem; color: var(--text-secondary); }
.leyenda-item { display: inline-flex; align-items: center; gap: 6px; }
.leyenda-item i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.destacados { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
.destacado {
  flex: 1 1 220px; display: flex; gap: 12px; align-items: flex-start;
  border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px;
}
.destacado-icono { font-size: 1.3rem; line-height: 1; color: var(--text-secondary); }
.destacado-texto { display: flex; flex-direction: column; gap: 2px; }
.destacado-etiqueta { color: var(--text-secondary); font-size: 0.78rem; }
.destacado-cultura { font-weight: 600; font-size: 0.95rem; }
.destacado-valor { font-variant-numeric: tabular-nums; color: var(--text-secondary); font-size: 0.85rem; }
.tabla-envoltorio { overflow-x: auto; margin-top: 8px; }
.tabla { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.tabla th, .tabla td {
  text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--gridline);
  font-variant-numeric: tabular-nums;
}
.tabla th { color: var(--text-secondary); font-weight: 600; position: sticky; top: 0; background: var(--surface-1); }
.tabla tbody tr:nth-child(even) { background: rgba(128, 128, 128, 0.07); }
.pie { margin-top: 32px; color: var(--text-muted); font-size: 0.8rem; text-align: center; }

@media print {
  .acciones-encabezado { display: none; }
  body, .viz-root {
    color-scheme: light;
    --page-plane:      #ffffff;
    --surface-1:       #ffffff;
    --text-primary:    #0b0b0b;
    --text-secondary:  #3a3a38;
    --text-muted:      #5c5b57;
    --gridline:        #cfcfc8;
    --baseline:        #8a8a84;
    --border:          #d8d8d2;
    background: #ffffff;
  }
  .viz-root { max-width: 100%; padding: 0; margin: 0; }
  .seccion, .kpi, .destacado, .tabla-envoltorio { break-inside: avoid; }
  .seccion { border: 1px solid #d8d8d2; }
  a[href]::after { content: ""; }
}
@page { size: A4; margin: 14mm 12mm; }
"""

_JS = """
(function () {
  var botonTema = document.getElementById('boton-tema');
  if (botonTema) {
    botonTema.addEventListener('click', function () {
      var raiz = document.documentElement;
      var actual = raiz.getAttribute('data-theme');
      raiz.setAttribute('data-theme', actual === 'dark' ? 'light' : 'dark');
    });
  }
  var botonPdf = document.getElementById('boton-pdf');
  if (botonPdf) {
    botonPdf.addEventListener('click', function () {
      window.print();
    });
  }
})();
"""
