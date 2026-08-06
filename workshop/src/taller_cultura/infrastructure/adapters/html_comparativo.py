"""Adaptador de salida: reporte comparativo entre dos sesiones del taller.

Implementa el puerto `ExportadorComparativo`. Responde una sola pregunta:
**¿en qué cambió la cultura entre la vez pasada y ahora?**

Comparte estructura con el reporte de una sesión —las mismas cinco
pestañas, la misma paleta, las mismas tartas— para que ambos documentos se
lean como una sola familia. Lo que cambia es el contenido: donde el reporte
individual muestra un valor, este muestra el par antes/ahora y su
variación.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from taller_cultura.application.ports import ExportadorComparativo
from taller_cultura.application.use_cases import ReporteComparativo, ReporteTaller
from taller_cultura.domain.model import CategoriaAspecto, TipoCultura, Valoracion
from taller_cultura.domain.services import ComparacionCategoria, ComparacionCultura

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
    _pestanas,
    _segmentos_de,
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
        # PASADO de ACTUAL; si cada sesión tiene un único juego de datos,
        # decir "momento PASADO" es ruido.
        distingue = antes.resumen.distingue_momentos or ahora.resumen.distingue_momentos
        detalle_momento = f"· momento {comparativo.momento.value} " if distingue else ""

        paneles = [
            ("resumen", "Resumen ejecutivo", self._panel_resumen(comparativo)),
            ("culturas", "Por cultura", self._panel_por_cultura(comparativo)),
            ("categorias", "Por categoría", self._panel_por_categoria(comparativo)),
            ("datos", "Datos", self._panel_datos(comparativo)),
            ("metodo", "Cómo leer esto", self._panel_metodo(comparativo)),
        ]

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
        &nbsp;&rarr;&nbsp;
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

  {_pestanas(paneles)}

  <footer class="pie">Generado automáticamente por el ETL del taller de cultura organizacional.</footer>
</div>
<script>{_JS}</script>
</body>
</html>
"""

    # -- paneles --------------------------------------------------------------

    def _panel_resumen(self, comparativo: ReporteComparativo) -> str:
        return f"""
    <section class="kpis">{self._kpis(comparativo)}</section>

    <div class="bloque">
      <h3>Qué se movió</h3>
      {self._destacados(comparativo)}
    </div>

    <div class="bloque">
      <h3>Variación por cultura</h3>
      <p class="ayuda">Cuánto subió o bajó cada cultura. Verde = avanzó, rojo = retrocedió.</p>
      {self._grafico_variacion(comparativo)}
    </div>

    <div class="bloque">
      <h3>Promedio por cultura: antes y ahora</h3>
      <p class="ayuda">Escala 0 (rojo) a 2 (verde). Cada cultura muestra sus dos mediciones.</p>
      {self._grafico_pares(comparativo)}
    </div>
"""

    def _panel_por_cultura(self, comparativo: ReporteComparativo) -> str:
        """Las tartas de cada cultura, en pareja: antes y ahora."""
        antes = _conteos_por_cultura(comparativo.antes)
        ahora = _conteos_por_cultura(comparativo.ahora)

        tarjetas = []
        for tipo_cultura in TipoCultura:
            comp = comparativo.comparacion.para(tipo_cultura)
            tarjetas.append(
                self._tarjeta_par(
                    titulo=tipo_cultura.value,
                    subtitulo=tipo_cultura.animal,
                    comparacion=comp,
                    conteo_antes=antes.get(tipo_cultura, {}),
                    conteo_ahora=ahora.get(tipo_cultura, {}),
                    etiquetas=(
                        f"v{comparativo.antes.sesion.numero_version}",
                        f"v{comparativo.ahora.sesion.numero_version}",
                    ),
                )
            )
        return (
            '<p class="ayuda">Cada cultura con su reparto del semáforo en las dos mediciones. '
            "El cambio de proporciones muestra hacia dónde se movió.</p>"
            f'<div class="rejilla-pares">{"".join(tarjetas)}</div>'
        )

    def _panel_por_categoria(self, comparativo: ReporteComparativo) -> str:
        """Lo mismo, abierto por categoría del taller."""
        antes = _conteos_por_categoria(comparativo.antes)
        ahora = _conteos_por_categoria(comparativo.ahora)
        por_clave = {(c.categoria, c.tipo_cultura): c for c in comparativo.comparacion_categoria}

        categorias = [c for c in CategoriaAspecto if any(k[0] is c for k in por_clave)]
        if not categorias:
            return '<p class="aviso">Todavía no hay valoraciones para desglosar.</p>'

        bloques = []
        for categoria in categorias:
            tarjetas = []
            for tipo_cultura in TipoCultura:
                clave = (categoria, tipo_cultura)
                if clave not in por_clave:
                    continue
                tarjetas.append(
                    self._tarjeta_par(
                        titulo=tipo_cultura.value,
                        subtitulo=None,
                        comparacion=por_clave[clave],
                        conteo_antes=antes.get(clave, {}),
                        conteo_ahora=ahora.get(clave, {}),
                        etiquetas=(
                            f"v{comparativo.antes.sesion.numero_version}",
                            f"v{comparativo.ahora.sesion.numero_version}",
                        ),
                        compacta=True,
                    )
                )
            if tarjetas:
                bloques.append(
                    f'<div class="bloque"><h3>{_escapar(categoria.value)}</h3>'
                    f'<div class="rejilla-pares">{"".join(tarjetas)}</div></div>'
                )
        return (
            '<p class="ayuda">El mismo contraste abierto por categoría, para ver en cuál de '
            "ellas se produjo el cambio.</p>" + "".join(bloques)
        )

    def _panel_datos(self, comparativo: ReporteComparativo) -> str:
        return f"""
    <div class="bloque">
      <h3>Comparativo por tipo de cultura</h3>
      {self._tabla(comparativo)}
    </div>

    <div class="bloque">
      <h3>Comparativo por categoría</h3>
      {self._tabla_categorias(comparativo)}
    </div>
"""

    def _panel_metodo(self, comparativo: ReporteComparativo) -> str:
        return self._notas(comparativo)

    # -- piezas ----------------------------------------------------------------

    @staticmethod
    def _tarjeta_par(
        *,
        titulo: str,
        subtitulo: str | None,
        comparacion,
        conteo_antes: dict[Valoracion, int],
        conteo_ahora: dict[Valoracion, int],
        etiquetas: tuple[str, str],
        compacta: bool = False,
    ) -> str:
        """Una cultura (o cultura×categoría) con sus dos tartas y su variación."""
        diametro = 120 if compacta else 140
        grosor = 28 if compacta else 32
        clase = " tarjeta-par--compacta" if compacta else ""

        def mitad(etiqueta: str, conteo: dict[Valoracion, int], promedio: float | None) -> str:
            valor = "s/d" if promedio is None else f"{promedio:.2f}"
            return (
                '<div class="mitad">'
                f'<span class="mitad-titulo">{_escapar(etiqueta)}</span>'
                f'<span class="mitad-valor">{valor}</span>'
                + grafico_tarta(
                    _segmentos_de(conteo),
                    titulo_accesible=f"{titulo} — {etiqueta}",
                    diametro=diametro,
                    grosor=grosor,
                )
                + "</div>"
            )

        return (
            f'<figure class="tarjeta-par{clase}">'
            f'<figcaption><span class="tarjeta-titulo">{_escapar(titulo)}</span>'
            + (f'<span class="tarjeta-animal">{_escapar(subtitulo)}</span>' if subtitulo else "")
            + f"{_insignia_variacion(comparacion)}</figcaption>"
            '<div class="par-tartas">'
            + mitad(etiquetas[0], conteo_antes, comparacion.promedio_antes)
            + mitad(etiquetas[1], conteo_ahora, comparacion.promedio_ahora)
            + "</div></figure>"
        )

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
                '<p class="aviso">Las dos sesiones no tienen ninguna cultura medida en común, '
                "así que no hay nada que comparar todavía.</p>"
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
    def _tabla(comparativo: ReporteComparativo) -> str:
        filas = "".join(
            "<tr>"
            f"<td>{_escapar(c.tipo_cultura.value)}</td>"
            f"<td>{_texto_promedio(c.promedio_antes)}</td>"
            f"<td>{_texto_promedio(c.promedio_ahora)}</td>"
            f"<td>{'—' if c.variacion is None else f'{c.variacion:+.2f}'}</td>"
            f"<td>{'—' if c.variacion_porcentual is None else f'{c.variacion_porcentual:+.1f}%'}</td>"
            f"<td>{_etiqueta_tendencia(c)}</td>"
            "</tr>"
            for c in comparativo.comparacion.comparaciones
        )
        return (
            '<div class="tabla-envoltorio"><table class="tabla">'
            "<thead><tr><th>Tipo de cultura</th><th>Antes</th><th>Ahora</th>"
            "<th>Variación</th><th>Variación %</th><th>Tendencia</th></tr></thead>"
            f"<tbody>{filas}</tbody></table></div>"
        )

    @staticmethod
    def _tabla_categorias(comparativo: ReporteComparativo) -> str:
        if not comparativo.comparacion_categoria:
            return '<p class="ayuda">No hay desglose por categoría todavía.</p>'
        filas = "".join(
            "<tr>"
            f"<td>{_escapar(c.categoria.value)}</td>"
            f"<td>{_escapar(c.tipo_cultura.value)}</td>"
            f"<td>{_texto_promedio(c.promedio_antes)}</td>"
            f"<td>{_texto_promedio(c.promedio_ahora)}</td>"
            f"<td>{'—' if c.variacion is None else f'{c.variacion:+.2f}'}</td>"
            f"<td>{_etiqueta_tendencia(c)}</td>"
            "</tr>"
            for c in comparativo.comparacion_categoria
        )
        return (
            '<div class="tabla-envoltorio"><table class="tabla">'
            "<thead><tr><th>Categoría</th><th>Tipo de cultura</th><th>Antes</th>"
            "<th>Ahora</th><th>Variación</th><th>Tendencia</th></tr></thead>"
            f"<tbody>{filas}</tbody></table></div>"
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
            "<strong>Colores:</strong> el semáforo del taller — rojo (R), amarillo (A) y "
            "verde (V)—, los mismos que usan las hojas FINAL y CULTURAS del libro original.",
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


# -- utilidades ------------------------------------------------------------------


def _conteos_por_cultura(reporte: ReporteTaller) -> dict[TipoCultura, dict[Valoracion, int]]:
    totales: dict[TipoCultura, dict[Valoracion, int]] = {}
    for r in reporte.resumen.resumenes:
        acumulado = totales.setdefault(r.tipo_cultura, {})
        for valoracion, cantidad in r.conteo_por_valoracion.items():
            acumulado[valoracion] = acumulado.get(valoracion, 0) + cantidad
    return totales


def _conteos_por_categoria(
    reporte: ReporteTaller,
) -> dict[tuple[CategoriaAspecto, TipoCultura], dict[Valoracion, int]]:
    totales: dict[tuple[CategoriaAspecto, TipoCultura], dict[Valoracion, int]] = {}
    for r in reporte.detalle_categoria:
        acumulado = totales.setdefault((r.categoria, r.tipo_cultura), {})
        for valoracion, cantidad in r.conteo_por_valoracion.items():
            acumulado[valoracion] = acumulado.get(valoracion, 0) + cantidad
    return totales


def _texto_promedio(valor: float | None) -> str:
    return "s/d" if valor is None else f"{valor:.2f}"


def _texto_variacion(comp: ComparacionCultura) -> str:
    if comp.variacion_porcentual is None:
        return f"{comp.variacion:+.2f}"
    return f"{comp.variacion:+.2f} ({comp.variacion_porcentual:+.1f}%)"


def _insignia_variacion(comp: ComparacionCultura | ComparacionCategoria) -> str:
    if not comp.es_comparable:
        return '<span class="insignia">sin comparar</span>'
    if comp.mejoro:
        return f'<span class="insignia" style="color:{COLOR_BUENO}">▲ {comp.variacion:+.2f}</span>'
    if comp.empeoro:
        return f'<span class="insignia" style="color:{COLOR_CRITICO}">▼ {comp.variacion:+.2f}</span>'
    return '<span class="insignia">= sin cambio</span>'


def _etiqueta_tendencia(comp: ComparacionCultura | ComparacionCategoria) -> str:
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
.rejilla-pares {
  display: grid; gap: 16px; margin-top: 12px;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
}
.tarjeta-par {
  margin: 0; padding: 14px; border: 1px solid var(--border); border-radius: 10px;
  background: var(--surface-1);
}
.tarjeta-par figcaption {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; margin-bottom: 10px;
}
.insignia {
  margin-left: auto; font-weight: 600; font-size: 0.85rem; white-space: nowrap;
  font-variant-numeric: tabular-nums; color: var(--text-secondary);
}
.par-tartas { display: flex; gap: 14px; flex-wrap: wrap; }
.mitad { flex: 1 1 150px; display: flex; flex-direction: column; gap: 2px; }
.mitad-titulo { color: var(--text-secondary); font-size: 0.78rem; font-weight: 600; }
.mitad-valor { font-size: 1.05rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.mitad .tarta-bloque { flex-direction: column; align-items: flex-start; gap: 6px; margin-top: 4px; }
.mitad .tarta-leyenda { flex: 1 1 auto; width: 100%; }
.mitad .tarta-leyenda li { padding: 3px 0; font-size: 0.76rem; }
.tarjeta-par--compacta .mitad-valor { font-size: 0.95rem; }
.tendencia { font-weight: 600; white-space: nowrap; }
"""
