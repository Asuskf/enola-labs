"""Adaptador de salida: reporte comparativo entre dos sesiones del taller.

Implementa el puerto `ExportadorComparativo`. Responde una sola pregunta:
**¿en qué cambió la cultura entre la vez pasada y ahora?** Por eso su forma
es distinta a la del reporte de una sesión: aquí lo que importa no es el
nivel de cada cultura sino el movimiento entre dos mediciones.

Reutiliza la paleta, la tarta y los estilos del reporte individual
(`html_writer`) para que ambos documentos se lean como una misma familia.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from taller_cultura.application.ports import ExportadorComparativo
from taller_cultura.application.use_cases import ReporteComparativo
from taller_cultura.domain.model import TipoCultura, Valoracion
from taller_cultura.domain.services import ComparacionCultura

from .html_writer import (
    _CSS,
    _JS,
    COLOR_ACTUAL,
    COLOR_ALTO,
    COLOR_BAJO,
    COLOR_BUENO,
    COLOR_CRITICO,
    COLOR_MEDIO,
    COLOR_PASADO,
    MAX_ESCALA_PROMEDIO,
    _escapar,
    grafico_tarta,
)

COLOR_ANTES = COLOR_PASADO
COLOR_AHORA = COLOR_ACTUAL


class ExportadorComparativoHTML(ExportadorComparativo):
    """Genera el reporte `.html` de "antes y ahora" entre dos sesiones."""

    def exportar_comparativo(self, comparativo: ReporteComparativo, ruta_destino: str) -> None:
        html = self._construir_html(comparativo)
        ruta = Path(ruta_destino)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(html, encoding="utf-8")

    # -- ensamblado ---------------------------------------------------------

    def _construir_html(self, comparativo: ReporteComparativo) -> str:
        antes, ahora = comparativo.antes, comparativo.ahora
        generado_en = datetime.now().strftime("%Y-%m-%d %H:%M")
        # El momento solo se nombra si alguna de las dos mediciones distingue
        # PASADO de ACTUAL; si cada sesión tiene un único juego de datos, decir
        # "momento PASADO" es ruido.
        distingue = antes.resumen.distingue_momentos or ahora.resumen.distingue_momentos
        detalle_momento = f"· momento {comparativo.momento.value} " if distingue else ""

        return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_escapar(comparativo.empresa)} — Comparativo del taller de cultura</title>
<style>{_CSS}{_CSS_EXTRA}</style>
</head>
<body>
<div class="viz-root">
  <header class="encabezado">
    <div>
      <h1>{_escapar(comparativo.empresa)}</h1>
      <p class="subtitulo">Comparativo del taller de cultura organizacional</p>
      <p class="marca-tiempo">
        Antes: v{antes.sesion.numero_version} del {antes.sesion.fecha_taller.isoformat()}
        &nbsp;→&nbsp;
        Ahora: v{ahora.sesion.numero_version} del {ahora.sesion.fecha_taller.isoformat()}
        {detalle_momento}· {_escapar(ahora.base_calculo).lower()}<br />
        Reporte generado el {generado_en}
      </p>
    </div>
    <div class="acciones-encabezado">
      <button class="boton boton-pdf" id="boton-pdf" type="button">⬇ Descargar como PDF</button>
      <button class="boton boton-tema" id="boton-tema" type="button" aria-label="Cambiar tema claro/oscuro">🌓</button>
    </div>
  </header>

  <section class="kpis">
    {self._kpis(comparativo)}
  </section>

  <section class="seccion">
    <h2>Qué se movió</h2>
    {self._destacados(comparativo)}
  </section>

  <section class="seccion">
    <h2>Promedio por cultura: antes y ahora</h2>
    <p class="ayuda">Escala 0 (bajo) a 2 (alto). Cada cultura muestra sus dos mediciones.</p>
    {self._grafico_pares(comparativo)}
  </section>

  <section class="seccion">
    <h2>Variación por cultura</h2>
    <p class="ayuda">Cuánto subió o bajó cada cultura. Verde = avanzó, rojo = retrocedió.</p>
    {self._grafico_variacion(comparativo)}
  </section>

  <section class="seccion">
    <h2>Cómo cambió el reparto de valoraciones</h2>
    <p class="ayuda">La distribución global de símbolos en cada medición.</p>
    <div class="tartas-par">
      <figure>
        <figcaption>Antes · v{antes.sesion.numero_version} ({antes.sesion.fecha_taller.isoformat()})</figcaption>
        {self._tarta(antes)}
      </figure>
      <figure>
        <figcaption>Ahora · v{ahora.sesion.numero_version} ({ahora.sesion.fecha_taller.isoformat()})</figcaption>
        {self._tarta(ahora)}
      </figure>
    </div>
  </section>

  <section class="seccion">
    <h2>Tabla comparativa</h2>
    {self._tabla(comparativo)}
  </section>

  <section class="seccion">
    <h2>Cómo leer este comparativo</h2>
    {self._notas(comparativo)}
  </section>

  <footer class="pie">Generado automáticamente por el ETL del taller de cultura organizacional.</footer>
</div>
<script>{_JS}</script>
</body>
</html>
"""

    # -- piezas --------------------------------------------------------------

    @staticmethod
    def _kpis(comparativo: ReporteComparativo) -> str:
        comparables = comparativo.comparacion.comparables
        avanzaron = sum(1 for c in comparables if c.mejoro)
        retrocedieron = sum(1 for c in comparables if c.empeoro)
        promedio_variacion = (
            round(sum(c.variacion for c in comparables) / len(comparables), 2)
            if comparables
            else 0.0
        )
        tiles = [
            ("Culturas comparables", f"{len(comparables)} / {len(TipoCultura)}"),
            ("Avanzaron", str(avanzaron)),
            ("Retrocedieron", str(retrocedieron)),
            ("Variación promedio", f"{promedio_variacion:+.2f}"),
        ]
        return "\n".join(
            f'<div class="kpi"><span class="kpi-valor">{valor}</span>'
            f'<span class="kpi-etiqueta">{_escapar(etiqueta)}</span></div>'
            for etiqueta, valor in tiles
        )

    @staticmethod
    def _destacados(comparativo: ReporteComparativo) -> str:
        comparacion = comparativo.comparacion
        if not comparacion.comparables:
            return (
                '<p class="aviso">Las dos sesiones no tienen ninguna cultura medida en común '
                "para el mismo momento, así que no hay nada que comparar todavía.</p>"
            )

        tarjetas = []
        avance = comparacion.mayor_avance
        retroceso = comparacion.mayor_retroceso
        if avance:
            tarjetas.append(
                _tarjeta("▲", COLOR_BUENO, "Mayor avance", avance.tipo_cultura.value,
                         _texto_variacion(avance))
            )
        if retroceso:
            tarjetas.append(
                _tarjeta("▼", COLOR_CRITICO, "Mayor retroceso", retroceso.tipo_cultura.value,
                         _texto_variacion(retroceso))
            )
        estables = [c for c in comparacion.comparables if c.variacion == 0]
        if estables:
            tarjetas.append(
                _tarjeta("=", None, "Sin cambios",
                         ", ".join(c.tipo_cultura.value for c in estables[:2]),
                         f"{len(estables)} cultura(s)")
            )
        if not tarjetas:
            return '<p class="aviso">Ninguna cultura cambió entre las dos mediciones.</p>'
        return f'<div class="destacados">{"".join(tarjetas)}</div>'

    @staticmethod
    def _grafico_pares(comparativo: ReporteComparativo) -> str:
        label_w, chart_w, pad = 190, 400, 60
        bar_h, bar_gap, group_gap, top_pad = 15, 3, 14, 28
        ancho = label_w + chart_w + pad

        culturas = sorted(
            comparativo.comparacion.comparaciones,
            key=lambda c: (c.promedio_ahora if c.promedio_ahora is not None else -1),
            reverse=True,
        )

        filas, y = [], top_pad
        for comp in culturas:
            centro = y + (2 * (bar_h + bar_gap) - bar_gap) / 2
            filas.append(
                f'<text x="10" y="{centro + 4:.1f}" class="etiqueta-fila">'
                f"{_escapar(comp.tipo_cultura.value)}</text>"
            )
            for valor, color, etiqueta in (
                (comp.promedio_antes, COLOR_ANTES, "Antes"),
                (comp.promedio_ahora, COLOR_AHORA, "Ahora"),
            ):
                tiene = valor is not None
                largo = (valor / MAX_ESCALA_PROMEDIO) * chart_w if tiene else 0
                texto = f"{valor:.2f}" if tiene else "s/d"
                if tiene:
                    filas.append(
                        f'<rect x="{label_w}" y="{y}" width="{max(largo, 1):.1f}" '
                        f'height="{bar_h}" rx="4" class="barra" fill="{color}">'
                        f"<title>{_escapar(comp.tipo_cultura.value)} · {etiqueta}: {texto}"
                        "</title></rect>"
                    )
                filas.append(
                    f'<text x="{label_w + largo + 6:.1f}" y="{y + bar_h - 3}" '
                    f'class="valor-barra">{texto}</text>'
                )
                y += bar_h + bar_gap
            y += group_gap
        alto = y + 10

        ticks = "".join(
            f'<line x1="{label_w + (i / MAX_ESCALA_PROMEDIO) * chart_w}" y1="{top_pad - 10}" '
            f'x2="{label_w + (i / MAX_ESCALA_PROMEDIO) * chart_w}" y2="{alto - 10}" '
            f'class="linea-guia" />'
            f'<text x="{label_w + (i / MAX_ESCALA_PROMEDIO) * chart_w}" y="{top_pad - 14}" '
            f'class="etiqueta-eje" text-anchor="middle">{i}</text>'
            for i in range(3)
        )
        leyenda = (
            '<div class="leyenda">'
            f'<span class="leyenda-item"><i style="background:{COLOR_ANTES}"></i>Antes</span>'
            f'<span class="leyenda-item"><i style="background:{COLOR_AHORA}"></i>Ahora</span>'
            "</div>"
        )
        return (
            leyenda
            + f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            'aria-label="Promedio por cultura en la medición anterior y la actual">'
            + ticks
            + "".join(filas)
            + "</svg>"
        )

    @staticmethod
    def _grafico_variacion(comparativo: ReporteComparativo) -> str:
        comparables = comparativo.comparacion.comparables
        if not comparables:
            return '<p class="aviso">No hay culturas comparables entre las dos sesiones.</p>'

        label_w, half_w, pad = 190, 200, 60
        bar_h, gap, top_pad = 20, 12, 24
        ancho = label_w + 2 * half_w + pad
        centro_x = label_w + half_w
        maximo = max(0.25, max(abs(c.variacion) for c in comparables))

        filas, y = [], top_pad
        for comp in sorted(comparables, key=lambda c: c.variacion, reverse=True):
            largo = (abs(comp.variacion) / maximo) * half_w
            color = COLOR_BUENO if comp.variacion > 0 else (
                COLOR_CRITICO if comp.variacion < 0 else "#898781"
            )
            x = centro_x if comp.variacion >= 0 else centro_x - largo
            filas.append(
                f'<text x="10" y="{y + bar_h / 2 + 4}" class="etiqueta-fila">'
                f"{_escapar(comp.tipo_cultura.value)}</text>"
                f'<rect x="{x:.1f}" y="{y}" width="{max(largo, 1):.1f}" height="{bar_h}" '
                f'rx="4" class="barra" fill="{color}"><title>'
                f"{_escapar(comp.tipo_cultura.value)}: {comp.variacion:+.2f}</title></rect>"
                f'<text x="{(x + largo + 6) if comp.variacion >= 0 else (x - 6):.1f}" '
                f'y="{y + bar_h - 5}" class="valor-barra" '
                f'text-anchor="{"start" if comp.variacion >= 0 else "end"}">'
                f"{comp.variacion:+.2f}</text>"
            )
            y += bar_h + gap
        alto = y + 6

        return (
            f'<svg viewBox="0 0 {ancho} {alto}" class="grafico" role="img" '
            'aria-label="Variación del promedio de cada cultura entre las dos mediciones">'
            f'<line x1="{centro_x}" y1="{top_pad - 8}" x2="{centro_x}" y2="{alto - 6}" '
            'class="linea-cero" />' + "".join(filas) + "</svg>"
        )

    @staticmethod
    def _tarta(reporte) -> str:
        totales = {v: 0 for v in (Valoracion.BAJO, Valoracion.MEDIO, Valoracion.ALTO)}
        for r in reporte.resumen.resumenes:
            for valoracion, cantidad in r.conteo_por_valoracion.items():
                totales[valoracion] += cantidad
        return grafico_tarta(
            [
                ("Bajo (R)", totales[Valoracion.BAJO], COLOR_BAJO),
                ("Medio (A)", totales[Valoracion.MEDIO], COLOR_MEDIO),
                ("Alto (V)", totales[Valoracion.ALTO], COLOR_ALTO),
            ],
            titulo_accesible=f"Distribución de valoraciones de {reporte.sesion.etiqueta}",
            diametro=170,
            grosor=38,
        )

    @staticmethod
    def _tabla(comparativo: ReporteComparativo) -> str:
        filas = []
        for comp in comparativo.comparacion.comparaciones:
            antes = "s/d" if comp.promedio_antes is None else f"{comp.promedio_antes:.2f}"
            ahora = "s/d" if comp.promedio_ahora is None else f"{comp.promedio_ahora:.2f}"
            variacion = "—" if comp.variacion is None else f"{comp.variacion:+.2f}"
            porcentual = (
                "—" if comp.variacion_porcentual is None else f"{comp.variacion_porcentual:+.1f}%"
            )
            filas.append(
                "<tr>"
                f"<td>{_escapar(comp.tipo_cultura.value)}</td>"
                f"<td>{antes}</td><td>{ahora}</td><td>{variacion}</td><td>{porcentual}</td>"
                f"<td>{_etiqueta_tendencia(comp)}</td>"
                "</tr>"
            )
        return (
            '<div class="tabla-envoltorio"><table class="tabla">'
            "<thead><tr><th>Tipo de cultura</th><th>Antes</th><th>Ahora</th>"
            "<th>Variación</th><th>Variación %</th><th>Tendencia</th></tr></thead>"
            f"<tbody>{''.join(filas)}</tbody></table></div>"
        )

    @staticmethod
    def _notas(comparativo: ReporteComparativo) -> str:
        antes, ahora = comparativo.antes, comparativo.ahora
        distingue = antes.resumen.distingue_momentos or ahora.resumen.distingue_momentos
        if distingue:
            que_se_compara = (
                f"<strong>Qué se compara:</strong> el momento "
                f"<strong>{comparativo.momento.value}</strong> de ambas sesiones. Comparar el "
                "PASADO de una contra el ACTUAL de la otra mezclaría dos preguntas distintas."
            )
        else:
            que_se_compara = (
                "<strong>Qué se compara:</strong> la medición de cada sesión, una contra otra. "
                "Cada taller registró un único juego de valoraciones por cultura, así que la "
                "comparación es directa entre las dos fechas."
            )
        notas = [
            que_se_compara,
            f"<strong>Cobertura de cada medición:</strong> antes "
            f"{antes.diagnostico.aspectos_calificados}/{antes.diagnostico.total_aspectos} ítems "
            f"({antes.diagnostico.porcentaje_cobertura:.0f}%), ahora "
            f"{ahora.diagnostico.aspectos_calificados}/{ahora.diagnostico.total_aspectos} ítems "
            f"({ahora.diagnostico.porcentaje_cobertura:.0f}%). Si una de las dos tiene poca "
            "cobertura, la variación es menos confiable.",
            "<strong>Escala:</strong> promedio ponderado de 0 a 2 (R=0, A=1, V=2). Una variación "
            "de +0,20 significa que la cultura subió una quinta parte de un escalón.",
        ]
        if antes.diagnostico.total_aspectos != ahora.diagnostico.total_aspectos:
            notas.append(
                "<strong>Ojo:</strong> las dos sesiones no tienen el mismo número de ítems "
                f"({antes.diagnostico.total_aspectos} vs {ahora.diagnostico.total_aspectos}), "
                "así que el taller cambió entre una y otra. La comparación sigue siendo válida "
                "porque se hace sobre promedios, pero conviene tenerlo presente."
            )
        return "<ul class='notas'>" + "".join(f"<li>{n}</li>" for n in notas) + "</ul>"


def _texto_variacion(comp: ComparacionCultura) -> str:
    if comp.variacion_porcentual is None:
        return f"{comp.variacion:+.2f}"
    return f"{comp.variacion:+.2f} ({comp.variacion_porcentual:+.1f}%)"


def _etiqueta_tendencia(comp: ComparacionCultura) -> str:
    if not comp.es_comparable:
        return '<span class="tendencia">sin comparar</span>'
    if comp.mejoro:
        return f'<span class="tendencia" style="color:{COLOR_BUENO}">▲ avanzó</span>'
    if comp.empeoro:
        return f'<span class="tendencia" style="color:{COLOR_CRITICO}">▼ retrocedió</span>'
    return '<span class="tendencia">= igual</span>'


def _tarjeta(icono: str, color: str | None, etiqueta: str, cultura: str, valor: str) -> str:
    estilo = f' style="color:{color}"' if color else ""
    return (
        '<div class="destacado">'
        f'<span class="destacado-icono"{estilo}>{icono}</span>'
        '<div class="destacado-texto">'
        f'<span class="destacado-etiqueta">{_escapar(etiqueta)}</span>'
        f'<span class="destacado-cultura">{_escapar(cultura)}</span>'
        f'<span class="destacado-valor">{_escapar(valor)}</span>'
        "</div></div>"
    )


_CSS_EXTRA = """
.tartas-par { display: flex; flex-wrap: wrap; gap: 32px; margin-top: 8px; }
.tartas-par figure { margin: 0; flex: 1 1 320px; }
.tartas-par figcaption {
  font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 8px; font-weight: 600;
}
.tendencia { font-weight: 600; white-space: nowrap; }
"""
