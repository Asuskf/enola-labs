# Taller de Cultura — arquitectura hexagonal

Aplicación para el "Taller de diagnóstico de cultura organizacional": lee
el Excel del taller, lo persiste en SQLite, calcula el resumen y produce
dos entregables distintos.

**La regla que organiza todo:** del libro de Excel **solo se reparte la hoja
TALLER** (con su roster `CALIFICADORES`). Todo lo demás —`RESUMEN`,
`PRESENTACION`, `PRESENTACION 2`, `FINAL`, `CULTURAS`— es material derivado,
y su contenido vive en el **reporte** que genera esta aplicación, no en el
archivo que se envía.

| Entregable | Qué es | Cómo se genera |
|---|---|---|
| **Plantilla** (`.xlsx`) | Solo la hoja TALLER + roster. Es lo único que se envía. | botón «Plantilla para enviar» / `plantilla` |
| **Reporte** (`.html` o `.xlsx`) | Todo el análisis: KPIs, gráficos, tablas, notas. | botón «Reporte HTML/Excel» / `resumen --reporte` |

## El dominio de negocio

El taller evalúa 5 **tipos de cultura** (LOGRO, CENTRADA EN EL CLIENTE,
EQUIPO UNICO, INNOVADORA, LAS PERSONAS PRIMERO) en 4 **categorías** (Tipo de
cultura, Comportamientos, Símbolos, Sistemas). Cada categoría tiene varios
**ítems** (frases), y cada ítem se califica con un semáforo de tres
símbolos —`R`, `A`, `V`— en dos **momentos**: PASADO y ACTUAL.

Los pesos (`R=0, A=1, V=2`, escala 0–2) replican la fórmula original de la
planilla (`R=0, A=0,5, V=1`, escala 0–1), solo reescalada.

**El consenso es la unidad de análisis.** Cada ítem se califica
individualmente (hasta 12 personas) y luego el grupo acuerda una fila
CONSENSO. El libro original agrega exactamente así: sus hojas `FINAL` y
`CULTURAS` cuentan **una sola fila —la de consenso— por ítem**. Por eso el
reporte usa el consenso por defecto; `--todas` incluye además las
respuestas individuales.

## Arquitectura

```
src/taller_cultura/
├── domain/            # Núcleo: entidades y reglas. Sin I/O, sin dependencias.
│   ├── model.py        (TipoCultura, CategoriaAspecto, Momento, Valoracion,
│   │                    Empresa, Calificador, Aspecto, Calificacion)
│   ├── services.py      (CalculadoraResumen, ResumenTaller, ResumenCultura,
│   │                     ResumenCategoria, DiagnosticoTaller)
│   └── exceptions.py
├── application/        # Casos de uso + puertos (contratos hacia infraestructura)
│   ├── ports.py         (LectorTaller, RepositorioTaller, ExportadorReporte,
│   │                     ExportadorPlantilla)
│   └── use_cases.py     (ImportarTallerDesdeExcel, CalcularResumenTaller,
│                         CalcularReporteTaller, ExportarReporteTaller,
│                         ExportarPlantillaTaller)
├── infrastructure/     # Adaptadores: SÍ conocen pandas/openpyxl/sqlite3/tkinter
│   ├── adapters/
│   │   ├── excel_reader.py     (LectorTallerExcel — parsea el .xlsx original)
│   │   ├── sqlite_repo.py      (RepositorioTallerSQLite)
│   │   ├── excel_writer.py     (ExportadorReporteExcel)
│   │   ├── html_writer.py      (ExportadorReporteHTML — autocontenido, con PDF)
│   │   └── plantilla_writer.py (ExportadorPlantillaExcel — solo hoja TALLER)
│   └── gui/
│       └── app.py       (adaptador primario: interfaz de escritorio en tkinter)
└── main.py             # Composición (inyección de dependencias) + CLI
```

El dominio no importa nada de `infrastructure`; los puertos en
`application/ports.py` son la frontera del hexágono. La GUI y la CLI son dos
adaptadores primarios distintos sobre los mismos casos de uso, y
`ExportadorReporte` es un puerto con dos adaptadores intercambiables (Excel
y HTML) que `main.py` elige según la extensión del archivo.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso — interfaz gráfica

```bash
python -m taller_cultura gui
```

Elegir el Excel → «Importar taller» → generar el reporte y/o la plantilla.
La casilla «Calcular solo con el consenso del grupo» cambia la base de
cálculo y el resumen en pantalla se actualiza al instante.

## Uso — línea de comandos

```bash
python -m taller_cultura importar --excel "Taller.xlsx" --bd data/taller.db
```

```bash
python -m taller_cultura resumen --bd data/taller.db --reporte data/reporte.html
```

Incluir también las calificaciones individuales, no solo el consenso:

```bash
python -m taller_cultura resumen --bd data/taller.db --todas
```

Generar el archivo que se reparte (solo la hoja TALLER):

```bash
python -m taller_cultura plantilla --excel "Taller.xlsx" --salida "TALLER para enviar.xlsx"
```

El reporte HTML es un archivo único sin dependencias externas (funciona sin
conexión) e incluye un botón **«Descargar como PDF»** que abre el diálogo de
impresión con estilos de papel A4 ya preparados.

## Sobre la fidelidad de los datos

El parser se validó celda por celda contra el libro original: captura
**todas** las respuestas de la hoja TALLER, sin perder ninguna y sin contar
dos veces las filas de eco (los `VLOOKUP` que repiten el consenso).

Al contrastar los agregados contra las hojas `FINAL` y `CULTURAS` del propio
Excel, **Comportamientos y Sistemas coinciden al 100 %**. Las diferencias
que aparecen en Símbolos provienen de fórmulas rotas en el libro original,
no del cálculo de esta aplicación:

- `FINAL!F38:L39` (los conteos de R y V de Símbolos) usan
  `COUNTIF(F32:F35, …)` —un rango local de 4 celdas de la propia hoja
  `FINAL`— en lugar de contar las filas de consenso de `TALLER`, como sí
  hace correctamente la columna D.
- `CULTURAS!H6` suma `FINAL!H14+H38+H67` (columna de EQUIPO UNICO) cuando
  debería sumar la columna `L` (LAS PERSONAS PRIMERO), de modo que ambas
  culturas muestran el mismo valor de R.
- `FINAL!D66` omite la fila 518, uno de los 11 ítems de Sistemas.

Esta aplicación calcula directamente desde la hoja TALLER, así que no
arrastra ninguno de esos errores.

## Tests

```bash
pytest
```

Los tests de integración se saltan solos si el Excel no está presente. El
más importante, `test_captura_todas_las_respuestas_de_la_hoja`, fija la
invariante que un bug real llegó a romper: el detector de bloques exigía
una etiqueta de categoría en la columna B, pero **solo el primer ítem de
cada categoría la lleva** —los demás la heredan—, así que se perdía la
mayoría de los ítems y sus calificaciones.
