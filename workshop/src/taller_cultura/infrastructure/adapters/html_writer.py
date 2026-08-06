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

import math
from datetime import datetime
from pathlib import Path

from taller_cultura.application.ports import ExportadorReporte
from taller_cultura.application.use_cases import ReporteTaller
from taller_cultura.domain.model import CategoriaAspecto, Momento, TipoCultura, Valoracion
from taller_cultura.domain.services import ResumenTaller

# -- paleta (paridad con la skill de dataviz del proyecto) -----------------

# Semáforo del taller. Son los colores del propio libro original: los de las
# tartas de las hojas FINAL y CULTURAS, que coinciden en significado con el
# formato condicional de PRESENTACION (R rojo, A amarillo, V verde). Se
# conservan tal cual para que el reporte hable el mismo idioma visual que el
# material que la empresa ya conoce.
COLOR_BAJO = "#ED3737"  # R — rojo
COLOR_MEDIO = "#F7F732"  # A — amarillo
COLOR_ALTO = "#60C541"  # V — verde

# El amarillo no da contraste suficiente sobre fondo claro para texto ni para
# trazos finos; para esos usos se emplea una versión entintada del mismo tono.
COLOR_MEDIO_TEXTO = "#8a7a00"

COLOR_PASADO = "#2a78d6"  # categórico slot 1 (azul)
COLOR_ACTUAL = "#eb6834"  # categórico slot 2 (naranja)
COLOR_POSITIVO = "#2a78d6"  # brecha que mejora (par divergente, polo azul)
COLOR_NEGATIVO = "#e34948"  # brecha que retrocede (par divergente, polo rojo)
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


def grafico_tarta(
    segmentos: list[tuple[str, int, str]],
    *,
    titulo_accesible: str,
    diametro: int = 210,
    grosor: int = 46,
) -> str:
    """Gráfico de tarta (dona) para una distribución parte-todo.

    Se usa aquí porque el caso lo permite: son tres categorías ordenadas
    que suman el 100 % de las respuestas. El agujero central aloja el
    total, y cada porción lleva su porcentaje en la leyenda —no dentro del
    arco— para que se lea sin depender del color.

    `segmentos` son tuplas (etiqueta, cantidad, color).
    """
    total = sum(cantidad for _, cantidad, _ in segmentos)
    if total == 0:
        return '<p class="aviso">Sin datos para graficar.</p>'

    radio = diametro / 2
    radio_medio = radio - grosor / 2
    perimetro = 2 * math.pi * radio_medio

    arcos = []
    recorrido = 0.0
    for etiqueta, cantidad, color in segmentos:
        if cantidad == 0:
            continue
        fraccion = cantidad / total
        # Un hueco de 2px en el color del fondo separa las porciones, igual
        # que en las barras apiladas; nunca un borde dibujado.
        largo = max(fraccion * perimetro - 2, 1)
        arcos.append(
            f'<circle cx="{radio}" cy="{radio}" r="{radio_medio}" fill="none" '
            f'stroke="{color}" stroke-width="{grosor}" '
            f'stroke-dasharray="{largo:.2f} {perimetro - largo:.2f}" '
            f'stroke-dashoffset="{-recorrido:.2f}" '
            f'transform="rotate(-90 {radio} {radio})">'
            f"<title>{_escapar(etiqueta)}: {cantidad} de {total} "
            f"({100 * fraccion:.1f}%)</title></circle>"
        )
        recorrido += fraccion * perimetro

    centro = (
        f'<text x="{radio}" y="{radio - 2}" text-anchor="middle" class="tarta-total">{total}</text>'
        f'<text x="{radio}" y="{radio + 16}" text-anchor="middle" class="tarta-rotulo">'
        "valoraciones</text>"
    )
    svg = (
        f'<svg viewBox="0 0 {diametro} {diametro}" class="tarta" role="img" '
        f'aria-label="{_escapar(titulo_accesible)}">' + "".join(arcos) + centro + "</svg>"
    )

    filas = "".join(
        f'<li><i style="background:{color}"></i>'
        f'<span class="tarta-etiqueta">{_escapar(etiqueta)}</span>'
        f'<span class="tarta-cifra">{cantidad}</span>'
        f'<span class="tarta-pct">{100 * cantidad / total:.1f}%</span></li>'
        for etiqueta, cantidad, color in segmentos
    )
    return f'<div class="tarta-bloque">{svg}<ul class="tarta-leyenda">{filas}</ul></div>'


SEGMENTOS_SEMAFORO = (
    ("Rojo (R)", Valoracion.BAJO, COLOR_BAJO),
    ("Amarillo (A)", Valoracion.MEDIO, COLOR_MEDIO),
    ("Verde (V)", Valoracion.ALTO, COLOR_ALTO),
)


def _segmentos_de(conteo: dict[Valoracion, int]) -> list[tuple[str, int, str]]:
    """Traduce un conteo por valoración a los segmentos del semáforo."""
    return [
        (etiqueta, conteo.get(valoracion, 0), color)
        for etiqueta, valoracion, color in SEGMENTOS_SEMAFORO
    ]


def _promedio_de(conteo: dict[Valoracion, int]) -> float | None:
    """Promedio ponderado (0–2) de un conteo suelto por valoración."""
    total = sum(conteo.values())
    if total == 0:
        return None
    return round(sum(v.peso * n for v, n in conteo.items()) / total, 2)


def _pestanas(paneles: list[tuple[str, str, str]]) -> str:
    """Arma la navegación por pestañas del reporte.

    `paneles` son tuplas (id, título, contenido HTML). La primera queda
    activa. Sin JavaScript el navegador muestra todos los paneles seguidos,
    así que el reporte impreso y el guardado como PDF salen completos.
    """
    botones = "".join(
        f'<button class="pestana{" pestana--activa" if i == 0 else ""}" '
        f'type="button" role="tab" aria-controls="panel-{ident}" '
        f'aria-selected="{"true" if i == 0 else "false"}" data-panel="panel-{ident}">'
        f"{_escapar(titulo)}</button>"
        for i, (ident, titulo, _) in enumerate(paneles)
    )
    contenidos = "".join(
        f'<section class="panel{" panel--activo" if i == 0 else ""}" id="panel-{ident}" '
        f'role="tabpanel"><h2 class="panel-titulo">{_escapar(titulo)}</h2>{contenido}</section>'
        for i, (ident, titulo, contenido) in enumerate(paneles)
    )
    return f'<nav class="pestanas" role="tablist">{botones}</nav><div class="paneles">{contenidos}</div>'


def _leyenda_momentos(momentos: tuple[Momento, ...]) -> str:
    """Aclaración sobre los momentos, solo cuando hay más de uno.

    Con una única medición no se nombra el momento: hay un solo valor por
    cultura y llamarlo "PASADO" no aporta nada.
    """
    if len(momentos) == 2:
        return "Se comparan el momento PASADO y el ACTUAL."
    return ""


def _culturas_comparables(resumen: ResumenTaller) -> list[TipoCultura]:
    """Culturas con datos en ambos momentos: las únicas donde la brecha
    significa algo.
    """
    comparables = []
    for tipo_cultura in TipoCultura:
        pasado = resumen.para(tipo_cultura, Momento.PASADO)
        actual = resumen.para(tipo_cultura, Momento.ACTUAL)
        if pasado and actual and pasado.total > 0 and actual.total > 0:
            comparables.append(tipo_cultura)
    return comparables


class ExportadorReporteHTML(ExportadorReporte):
    """Genera un reporte `.html` autocontenido con el resumen del taller."""

    def exportar_reporte(self, reporte: ReporteTaller, ruta_destino: str) -> None:
        html = self._construir_html(reporte)
        ruta = Path(ruta_destino)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(html, encoding="utf-8")

    # -- ensamblado ---------------------------------------------------

    def _construir_html(self, reporte: ReporteTaller) -> str:
        generado_en = datetime.now().strftime("%Y-%m-%d %H:%M")
        paneles = [
            ("resumen", "Resumen ejecutivo", self._panel_resumen(reporte)),
            ("culturas", "Por cultura", self._panel_por_cultura(reporte)),
            ("categorias", "Por categoría", self._panel_por_categoria(reporte)),
            ("datos", "Datos", self._panel_datos(reporte)),
            ("metodo", "Cómo leer esto", self._panel_metodo(reporte)),
        ]

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
      <p class="marca-tiempo">
        Taller del {reporte.sesion.fecha_taller.isoformat()} · versión {reporte.sesion.numero_version}
        · base de cálculo: {_escapar(reporte.base_calculo)}<br />
        Reporte generado el {generado_en}
      </p>
    </div>
    <div class="acciones-encabezado">
      <button class="boton boton-pdf" id="boton-pdf" type="button">⬇ Descargar como PDF</button>
      <button class="boton boton-tema" id="boton-tema" type="button" aria-label="Cambiar tema claro/oscuro">🌓</button>
    </div>
  </header>

  {_pestanas(paneles)}

  <footer class="pie">Generado automáticamente por el ETL del taller de cultura organizacional.</footer>
</div>
<script>{_JS}</script>
</body>
</html>
"""

    # -- paneles ---------------------------------------------------------

    def _panel_resumen(self, reporte: ReporteTaller) -> str:
        """Lo que se mira primero: cifras clave, hallazgos y el reparto global."""
        momentos = reporte.resumen.momentos_con_datos
        return f"""
    <section class="kpis">{self._construir_kpis(reporte)}</section>

    <div class="bloque">
      <h3>Aspectos destacados</h3>
      {self._construir_destacados(reporte.resumen, momentos)}
    </div>

    <div class="bloque">
      <h3>Reparto global del semáforo</h3>
      <p class="ayuda">Cómo se reparten todas las valoraciones del taller entre los tres colores.</p>
      {self._tarta_global(reporte.resumen)}
    </div>

    <div class="bloque">
      <h3>Promedio por tipo de cultura</h3>
      <p class="ayuda">Escala 0 (rojo) a 2 (verde). {_escapar(_leyenda_momentos(momentos))}</p>
      {self._grafico_barras_agrupadas(reporte.resumen, momentos)}
    </div>

    {self._seccion_brecha(reporte.resumen, momentos, reporte.sesion.numero_version)}
"""

    def _panel_por_cultura(self, reporte: ReporteTaller) -> str:
        """Una tarta por tipo de cultura, como la hoja CULTURAS del libro."""
        conteos: dict[TipoCultura, dict[Valoracion, int]] = {}
        for r in reporte.resumen.resumenes:
            acumulado = conteos.setdefault(r.tipo_cultura, {})
            for valoracion, cantidad in r.conteo_por_valoracion.items():
                acumulado[valoracion] = acumulado.get(valoracion, 0) + cantidad

        tarjetas = []
        for tipo_cultura in TipoCultura:
            conteo = conteos.get(tipo_cultura, {})
            promedio = _promedio_de(conteo)
            tarjetas.append(
                '<figure class="tarjeta-tarta">'
                f'<figcaption><span class="tarjeta-titulo">{_escapar(tipo_cultura.value)}</span>'
                f'<span class="tarjeta-animal">{_escapar(tipo_cultura.animal)}</span>'
                + (
                    f'<span class="tarjeta-promedio">promedio {promedio:.2f} / 2.00</span>'
                    if promedio is not None
                    else '<span class="tarjeta-promedio">sin valoraciones</span>'
                )
                + "</figcaption>"
                + grafico_tarta(
                    _segmentos_de(conteo),
                    titulo_accesible=f"Reparto de valoraciones de la cultura {tipo_cultura.value}",
                    diametro=170,
                    grosor=38,
                )
                + "</figure>"
            )
        return (
            '<p class="ayuda">Cada cultura con el reparto de sus valoraciones, igual que '
            "las tartas de la hoja CULTURAS del libro original.</p>"
            f'<div class="rejilla-tartas">{"".join(tarjetas)}</div>'
        )

    def _panel_por_categoria(self, reporte: ReporteTaller) -> str:
        """Una tarta por cultura dentro de cada categoría, como la hoja FINAL."""
        conteos: dict[tuple[CategoriaAspecto, TipoCultura], dict[Valoracion, int]] = {}
        for detalle in reporte.detalle_categoria:
            clave = (detalle.categoria, detalle.tipo_cultura)
            acumulado = conteos.setdefault(clave, {})
            for valoracion, cantidad in detalle.conteo_por_valoracion.items():
                acumulado[valoracion] = acumulado.get(valoracion, 0) + cantidad

        categorias_presentes = [c for c in CategoriaAspecto if any(k[0] is c for k in conteos)]
        if not categorias_presentes:
            return '<p class="aviso">Todavía no hay valoraciones para desglosar.</p>'

        bloques = []
        for categoria in categorias_presentes:
            tarjetas = []
            for tipo_cultura in TipoCultura:
                conteo = conteos.get((categoria, tipo_cultura), {})
                if not conteo:
                    continue
                promedio = _promedio_de(conteo)
                tarjetas.append(
                    '<figure class="tarjeta-tarta tarjeta-tarta--chica">'
                    f'<figcaption><span class="tarjeta-titulo">{_escapar(tipo_cultura.value)}</span>'
                    + (
                        f'<span class="tarjeta-promedio">{promedio:.2f} / 2.00</span>'
                        if promedio is not None
                        else ""
                    )
                    + "</figcaption>"
                    + grafico_tarta(
                        _segmentos_de(conteo),
                        titulo_accesible=(
                            f"Reparto de {categoria.value} en la cultura {tipo_cultura.value}"
                        ),
                        diametro=140,
                        grosor=32,
                    )
                    + "</figure>"
                )
            if tarjetas:
                bloques.append(
                    f'<div class="bloque"><h3>{_escapar(categoria.value)}</h3>'
                    f'<div class="rejilla-tartas">{"".join(tarjetas)}</div></div>'
                )
        return (
            '<p class="ayuda">El mismo reparto abierto por categoría del taller, igual que '
            "las tartas de la hoja FINAL del libro original.</p>" + "".join(bloques)
        )

    def _panel_datos(self, reporte: ReporteTaller) -> str:
        return f"""
    <div class="bloque">
      <h3>Resumen por tipo de cultura</h3>
      {self._tabla_resumen(reporte.resumen)}
    </div>

    <div class="bloque">
      <h3>Distribución por tipo de cultura</h3>
      {self._grafico_distribucion(reporte.resumen)}
    </div>

    <div class="bloque">
      <h3>Detalle por categoría</h3>
      {self._tabla_detalle_categoria(reporte.detalle_categoria, reporte.resumen.distingue_momentos)}
    </div>
"""

    def _panel_metodo(self, reporte: ReporteTaller) -> str:
        return self._construir_notas(reporte, reporte.resumen.momentos_con_datos)

    # -- KPIs -----------------------------------------------------------

    @staticmethod
    def _construir_kpis(reporte: ReporteTaller) -> str:
        total_respuestas = sum(r.total for r in reporte.resumen.resumenes)
        diagnostico = reporte.diagnostico
        tiles = [
            ("Respuestas consideradas", str(total_respuestas)),
            (
                "Ítems calificados",
                f"{diagnostico.aspectos_calificados} / {diagnostico.total_aspectos}",
            ),
            ("Cobertura del taller", f"{diagnostico.porcentaje_cobertura:.0f}%"),
            ("Calificadores participantes", str(reporte.calificadores_participantes)),
        ]
        return "\n".join(
            f'<div class="kpi"><span class="kpi-valor">{valor}</span>'
            f'<span class="kpi-etiqueta">{_escapar(etiqueta)}</span></div>'
            for etiqueta, valor in tiles
        )

    # -- tarta: distribución global -----------------------------------------

    @staticmethod
    def _tarta_global(resumen: ResumenTaller) -> str:
        totales = {v: 0 for v in (Valoracion.BAJO, Valoracion.MEDIO, Valoracion.ALTO)}
        for r in resumen.resumenes:
            for valoracion, cantidad in r.conteo_por_valoracion.items():
                totales[valoracion] += cantidad

        return grafico_tarta(
            [
                ("Bajo (R)", totales[Valoracion.BAJO], COLOR_BAJO),
                ("Medio (A)", totales[Valoracion.MEDIO], COLOR_MEDIO),
                ("Alto (V)", totales[Valoracion.ALTO], COLOR_ALTO),
            ],
            titulo_accesible="Distribución global de valoraciones bajo, medio y alto",
        )

    # -- notas metodológicas ------------------------------------------------

    @staticmethod
    def _construir_notas(reporte: ReporteTaller, momentos: tuple[Momento, ...]) -> str:
        d = reporte.diagnostico
        unidad = "por ítem, cultura y momento" if len(momentos) > 1 else "por ítem y cultura"
        notas = [
            f"<strong>Base de cálculo:</strong> {_escapar(reporte.base_calculo)}. "
            f"El consenso es la unidad de análisis del taller: una valoración acordada "
            f"{unidad}. Así es como agrega también el libro original.",
            "<strong>Escala:</strong> cada valoración usa los símbolos R, A y V con pesos "
            "0, 1 y 2 respectivamente, replicando la fórmula de la planilla "
            "(<code>R=0, A=0,5, V=1</code>, aquí reescalada a 0–2). El promedio ponderado "
            "va de 0 a 2.",
            f"<strong>Cobertura:</strong> {d.aspectos_calificados} de {d.total_aspectos} ítems "
            f"tienen al menos una valoración ({d.porcentaje_cobertura:.0f}%). "
            f"Quedan {d.aspectos_sin_calificar} ítems sin calificar; las culturas o categorías "
            "con pocas respuestas deben leerse con cautela.",
            f"<strong>Respuestas en el archivo:</strong> {d.respuestas_consenso} de consenso y "
            f"{d.respuestas_individuales} individuales.",
        ]
        if len(momentos) < 2:
            notas.append(
                "<strong>Una sola medición:</strong> este taller registró un único juego de "
                "valoraciones por cultura, así que cada cifra es un valor y no una "
                "comparación. La evolución se obtiene repitiendo el taller y usando el "
                "reporte comparativo."
            )
        return "<ul class='notas'>" + "".join(f"<li>{n}</li>" for n in notas) + "</ul>"

    # -- resumen ejecutivo -------------------------------------------------

    @staticmethod
    def _construir_destacados(resumen: ResumenTaller, momentos: tuple[Momento, ...]) -> str:
        if not momentos:
            return '<p class="ayuda">Todavía no hay calificaciones para destacar hallazgos.</p>'

        # El momento de referencia es ACTUAL si tiene datos; si no, el único
        # que haya. Solo se nombra cuando el taller distingue los dos.
        referencia = momentos[-1]
        sufijo = f" ({referencia.value})" if resumen.distingue_momentos else ""
        puntajes = [
            (tc, r.promedio_ponderado)
            for tc in TipoCultura
            if (r := resumen.para(tc, referencia)) is not None and r.total > 0
        ]

        tarjetas = []
        if puntajes:
            mejor = max(puntajes, key=lambda t: t[1])
            peor = min(puntajes, key=lambda t: t[1])
            tarjetas.append(
                _tarjeta_destacado(
                    "★", COLOR_BUENO, f"Cultura más presente{sufijo}",
                    mejor[0].value, f"{mejor[1]:.2f} / 2.00",
                )
            )
            if peor[0] is not mejor[0]:
                tarjetas.append(
                    _tarjeta_destacado(
                        "○", COLOR_CRITICO, f"Cultura menos presente{sufijo}",
                        peor[0].value, f"{peor[1]:.2f} / 2.00",
                    )
                )

        comparables = _culturas_comparables(resumen)
        if comparables:
            brechas = [(tc, resumen.brecha(tc)) for tc in comparables]
            mayor_progreso = max(brechas, key=lambda t: t[1])
            if mayor_progreso[1] > 0:
                tarjetas.append(
                    _tarjeta_destacado(
                        "▲", COLOR_BUENO, "Mayor progreso",
                        mayor_progreso[0].value, f"{mayor_progreso[1]:+.2f}",
                    )
                )

        if not tarjetas:
            return '<p class="ayuda">Todavía no hay suficientes calificaciones para destacar hallazgos.</p>'
        return f'<div class="destacados">{"".join(tarjetas)}</div>'

    # -- sección de brecha (solo si tiene sentido) ---------------------------

    def _seccion_brecha(
        self, resumen: ResumenTaller, momentos: tuple[Momento, ...], version: int
    ) -> str:
        """La sección de brecha solo aparece si hay dos momentos que comparar.

        Con una única medición no se menciona ningún momento: en su lugar se
        explica de dónde saldrá la comparación (repetir el taller y usar el
        reporte comparativo).
        """
        comparables = _culturas_comparables(resumen)
        if len(momentos) < 2 or not comparables:
            if version > 1:
                pista = (
                    "Esta empresa ya tiene mediciones anteriores: usa el "
                    "<strong>reporte comparativo</strong> para ver la evolución entre ellas."
                )
            else:
                pista = (
                    "Esta es la primera medición de la empresa, así que todavía no hay "
                    "contra qué compararla. Cuando se repita el taller, el "
                    "<strong>reporte comparativo</strong> mostrará cuánto cambió cada cultura."
                )
            return (
                '<section class="seccion">'
                "<h2>Evolución</h2>"
                f'<p class="aviso">{pista}</p>'
                "</section>"
            )
        return (
            '<section class="seccion">'
            "<h2>Brecha ACTUAL − PASADO</h2>"
            '<p class="ayuda">Diferencia del promedio ponderado. Azul = mejora, rojo = retrocede. '
            f"Se muestran las {len(comparables)} culturas con datos en ambos momentos.</p>"
            f"{self._grafico_brecha(resumen, comparables)}"
            "</section>"
        )

    # -- gráfico A: barras agrupadas PASADO/ACTUAL -----------------------

    @staticmethod
    def _grafico_barras_agrupadas(resumen: ResumenTaller, momentos: tuple[Momento, ...]) -> str:
        if not momentos:
            return '<p class="aviso">Sin datos para graficar.</p>'

        color_de = {Momento.PASADO: COLOR_PASADO, Momento.ACTUAL: COLOR_ACTUAL}
        label_w, chart_w, pad_right = 190, 420, 50
        bar_h, bar_gap, group_gap = 16, 4, 14
        top_pad = 28
        ancho = label_w + chart_w + pad_right + 20

        # Las culturas se ordenan por el momento de referencia: el reporte se
        # lee como un ranking, no como una lista arbitraria.
        referencia = momentos[-1]
        culturas = sorted(
            TipoCultura,
            key=lambda tc: (r.promedio_ponderado if (r := resumen.para(tc, referencia)) else -1),
            reverse=True,
        )

        filas_svg = []
        y = top_pad
        for tipo_cultura in culturas:
            centro = y + (len(momentos) * (bar_h + bar_gap) - bar_gap) / 2
            filas_svg.append(
                f'<text x="10" y="{centro + 4:.1f}" class="etiqueta-fila">'
                f"{_escapar(tipo_cultura.value)}</text>"
            )
            for momento in momentos:
                r = resumen.para(tipo_cultura, momento)
                tiene = r is not None and r.total > 0
                valor = r.promedio_ponderado if tiene else 0.0
                ancho_barra = (valor / MAX_ESCALA_PROMEDIO) * chart_w if tiene else 0
                texto_valor = f"{valor:.2f}" if tiene else "s/d"
                if tiene:
                    # El momento solo entra en el tooltip si hay dos que distinguir.
                    detalle = f" · {momento.value}" if len(momentos) > 1 else ""
                    filas_svg.append(
                        f'<rect x="{label_w}" y="{y}" width="{max(ancho_barra, 1):.1f}" '
                        f'height="{bar_h}" rx="4" class="barra" fill="{color_de[momento]}"><title>'
                        f"{_escapar(tipo_cultura.value)}{detalle} — {texto_valor} "
                        f"({r.total} respuestas)</title></rect>"
                    )
                filas_svg.append(
                    f'<text x="{label_w + ancho_barra + 6:.1f}" y="{y + bar_h - 3}" '
                    f'class="valor-barra">{texto_valor}</text>'
                )
                y += bar_h + bar_gap
            y += group_gap
        alto = y + 10

        ticks = []
        for i in range(3):  # 0, 1, 2
            x = label_w + (i / MAX_ESCALA_PROMEDIO) * chart_w
            ticks.append(
                f'<line x1="{x}" y1="{top_pad - 10}" x2="{x}" y2="{alto - 10}" class="linea-guia" />'
                f'<text x="{x}" y="{top_pad - 14}" class="etiqueta-eje" text-anchor="middle">{i}</text>'
            )

        leyenda = ""
        if len(momentos) > 1:
            leyenda = (
                '<div class="leyenda">'
                + "".join(
                    f'<span class="leyenda-item"><i style="background:{color_de[m]}"></i>'
                    f"{m.value}</span>"
                    for m in momentos
                )
                + "</div>"
            )
        svg = (
            f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            f'aria-label="Promedio ponderado por tipo de cultura">'
            + "".join(ticks)
            + "".join(filas_svg)
            + "</svg>"
        )
        return leyenda + svg

    # -- gráfico B: brecha divergente -------------------------------------

    @staticmethod
    def _grafico_brecha(resumen: ResumenTaller, culturas: list[TipoCultura]) -> str:
        label_w, half_w, pad = 190, 210, 50
        bar_h, gap, top_pad = 20, 12, 24
        ancho = label_w + 2 * half_w + pad
        centro_x = label_w + half_w

        brechas = {tc: resumen.brecha(tc) for tc in culturas}
        maximo = max(0.5, max(abs(v) for v in brechas.values()))

        filas_svg = []
        y = top_pad
        for tipo_cultura in culturas:
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

        distingue = resumen.distingue_momentos
        filas_svg = []
        y = top_pad
        for r in resumen.resumenes:
            etiqueta = f"{r.tipo_cultura.value} · {r.momento.value}" if distingue else r.tipo_cultura.value
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
        alcance = "por cultura y momento" if distingue else "por tipo de cultura"
        svg = (
            f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            f'aria-label="Distribución de valoraciones bajo, medio y alto {alcance}">'
            + "".join(filas_svg)
            + "</svg>"
        )
        return leyenda + svg

    # -- tablas accesibles -------------------------------------------------

    @staticmethod
    def _tabla_resumen(resumen: ResumenTaller) -> str:
        distingue = resumen.distingue_momentos
        columna_momento = "<th>Momento</th>" if distingue else ""
        filas = []
        for r in resumen.resumenes:
            filas.append(
                "<tr>"
                f"<td>{_escapar(r.tipo_cultura.value)}</td>"
                + (f"<td>{_escapar(r.momento.value)}</td>" if distingue else "")
                + f"<td>{r.total}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.BAJO, 0)}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.MEDIO, 0)}</td>"
                f"<td>{r.conteo_por_valoracion.get(Valoracion.ALTO, 0)}</td>"
                f"<td>{r.promedio_ponderado:.2f}</td>"
                f"<td>{r.porcentaje_valor_alto:.1f}%</td>"
                "</tr>"
            )
        return (
            '<div class="tabla-envoltorio"><table class="tabla">'
            f"<thead><tr><th>Tipo de cultura</th>{columna_momento}<th>Total</th>"
            "<th>Bajo (R)</th><th>Medio (A)</th><th>Alto (V)</th>"
            "<th>Promedio (0-2)</th><th>% Alto</th></tr></thead>"
            f"<tbody>{''.join(filas)}</tbody></table></div>"
        )

    @staticmethod
    def _tabla_detalle_categoria(detalle, distingue_momentos: bool) -> str:
        columna_momento = "<th>Momento</th>" if distingue_momentos else ""
        filas = []
        for r in detalle:
            filas.append(
                "<tr>"
                f"<td>{_escapar(r.categoria.value)}</td>"
                f"<td>{_escapar(r.tipo_cultura.value)}</td>"
                + (f"<td>{_escapar(r.momento.value)}</td>" if distingue_momentos else "")
                + f"<td>{r.total}</td>"
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
            f"<thead><tr><th>Categoría</th><th>Tipo de cultura</th>{columna_momento}"
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
/* -- pestañas -------------------------------------------------------- */
.pestanas {
  display: flex; flex-wrap: wrap; gap: 4px; margin: 24px 0 0;
  border-bottom: 1px solid var(--border);
}
.pestana {
  border: 1px solid transparent; border-bottom: none; background: none;
  color: var(--text-secondary); font: inherit; font-size: 0.9rem; cursor: pointer;
  padding: 9px 16px; border-radius: 8px 8px 0 0; margin-bottom: -1px;
}
.pestana:hover { background: rgba(128,128,128,0.10); }
.pestana--activa {
  background: var(--surface-1); border-color: var(--border);
  color: var(--text-primary); font-weight: 600;
}
.panel { display: none; padding-top: 20px; }
.panel--activo { display: block; }
.panel-titulo { position: absolute; left: -9999px; }
.bloque {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 12px; padding: 18px 22px; margin-bottom: 16px;
}
.bloque h3 { margin: 0 0 4px; font-size: 1.02rem; }

/* -- rejilla de tartas ------------------------------------------------ */
.rejilla-tartas {
  display: grid; gap: 16px; margin-top: 12px;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
}
.tarjeta-tarta {
  margin: 0; padding: 14px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface-1);
}
.tarjeta-tarta figcaption { margin-bottom: 6px; display: flex; flex-direction: column; gap: 1px; }
.tarjeta-titulo { font-weight: 600; font-size: 0.92rem; }
.tarjeta-animal { color: var(--text-secondary); font-size: 0.82rem; font-style: italic; }
.tarjeta-promedio {
  color: var(--text-secondary); font-size: 0.8rem; font-variant-numeric: tabular-nums;
}
.tarjeta-tarta .tarta-bloque { gap: 14px; margin-top: 4px; }
.tarjeta-tarta .tarta-leyenda li { padding: 5px 0; font-size: 0.82rem; }
.tarjeta-tarta--chica .tarta-leyenda li { padding: 4px 0; font-size: 0.78rem; }

.tarta-bloque { display: flex; flex-wrap: wrap; align-items: center; gap: 28px; margin-top: 12px; }
.tarta { width: 210px; height: 210px; flex-shrink: 0; }
.tarta-total { fill: var(--text-primary); font-size: 30px; font-weight: 600; }
.tarta-rotulo { fill: var(--text-muted); font-size: 11px; }
.tarta-leyenda { list-style: none; margin: 0; padding: 0; flex: 1 1 240px; }
.tarta-leyenda li {
  display: flex; align-items: center; gap: 10px; padding: 8px 0;
  border-bottom: 1px solid var(--gridline); font-size: 0.9rem;
}
.tarta-leyenda li:last-child { border-bottom: none; }
.tarta-leyenda i { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }
.tarta-etiqueta { flex: 1; color: var(--text-secondary); }
.tarta-cifra { font-variant-numeric: tabular-nums; color: var(--text-secondary); }
.tarta-pct { font-variant-numeric: tabular-nums; font-weight: 600; min-width: 56px; text-align: right; }
.aviso {
  margin: 8px 0 0; padding: 12px 14px; border-radius: 8px; font-size: 0.88rem;
  color: var(--text-secondary); background: rgba(128,128,128,0.10);
  border-left: 3px solid var(--baseline);
}
.notas { margin: 8px 0 0; padding-left: 20px; color: var(--text-secondary); font-size: 0.88rem; line-height: 1.6; }
.notas li { margin-bottom: 8px; }
.notas code { font-size: 0.85em; background: rgba(128,128,128,0.12); padding: 1px 4px; border-radius: 3px; }
.pie { margin-top: 32px; color: var(--text-muted); font-size: 0.8rem; text-align: center; }

@media print {
  .acciones-encabezado, .pestanas { display: none; }
  /* En papel no hay pestañas que pulsar: se imprimen todos los paneles,
     cada uno encabezado por su título y empezando en página nueva. */
  .panel { display: block !important; page-break-before: always; padding-top: 0; }
  .panel:first-of-type { page-break-before: auto; }
  .panel-titulo {
    position: static; left: auto; font-size: 1.25rem; margin: 0 0 12px;
    padding-bottom: 6px; border-bottom: 2px solid #d8d8d2;
  }
  .rejilla-tartas { grid-template-columns: repeat(2, 1fr); }
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
  .seccion, .bloque, .kpi, .destacado, .tarjeta-tarta, .tabla-envoltorio { break-inside: avoid; }
  .seccion { border: 1px solid #d8d8d2; }
  a[href]::after { content: ""; }
}
@page { size: A4; margin: 14mm 12mm; }
"""

_JS = """
(function () {
  // Pestañas: sin JavaScript el CSS deja visible solo la primera, pero al
  // imprimir se muestran todas, así que el PDF nunca pierde contenido.
  var pestanas = document.querySelectorAll('.pestana');
  Array.prototype.forEach.call(pestanas, function (boton) {
    boton.addEventListener('click', function () {
      Array.prototype.forEach.call(pestanas, function (otro) {
        otro.classList.remove('pestana--activa');
        otro.setAttribute('aria-selected', 'false');
      });
      Array.prototype.forEach.call(document.querySelectorAll('.panel'), function (panel) {
        panel.classList.remove('panel--activo');
      });
      boton.classList.add('pestana--activa');
      boton.setAttribute('aria-selected', 'true');
      var panel = document.getElementById(boton.getAttribute('data-panel'));
      if (panel) { panel.classList.add('panel--activo'); }
    });
  });

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
