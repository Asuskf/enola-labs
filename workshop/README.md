# Taller de Cultura — arquitectura hexagonal

Aplicación para el "Taller de diagnóstico de cultura organizacional": valida
el Excel del taller, lo registra como una **sesión** (empresa + fecha), lo
persiste en SQLite y produce los entregables.

**La regla que organiza todo:** del libro de Excel **solo se reparte la hoja
TALLER** (con su roster `CALIFICADORES`). Todo lo demás —`RESUMEN`,
`PRESENTACION`, `PRESENTACION 2`, `FINAL`, `CULTURAS`— es material derivado,
y su contenido vive en el **reporte** que genera esta aplicación, no en el
archivo que se envía.

| Entregable | Qué es | Cómo se genera |
|---|---|---|
| **Plantilla** (`.xlsx`) | Solo la hoja TALLER + roster. Es lo único que se envía. | «Plantilla para enviar» / `plantilla` |
| **Reporte** (`.html` / `.xlsx`) | El análisis de una sesión: KPIs, tarta, gráficos, tablas, notas. | «Reporte HTML/Excel» / `reporte` |
| **Comparativo** (`.html`) | Antes vs ahora entre dos sesiones de la misma empresa. | «Comparar versiones» / `comparar` |

## El flujo de trabajo

```
    ¿Taller nuevo o nueva versión?
              │
      ┌───────┴────────┐
   NUEVO            NUEVA VERSIÓN
   pide empresa     elige la empresa ya registrada
   y fecha          y pide la fecha (la versión se numera sola)
      └───────┬────────┘
              ▼
      elegir el archivo  →  VALIDAR  →  procesar
              │                            │
              │                     ┌──────┴───────┐
              │                  reporte      comparativo
              │                 (1 sesión)   (2 sesiones)
```

Una empresa puede repetir el taller cuantas veces quiera: cada aplicación es
una **sesión** con su fecha y su número de versión (v1, v2, …). Comparar dos
sesiones de la misma empresa es lo que produce el reporte de "antes y ahora".

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
`CULTURAS` cuentan **una sola fila —la de consenso— por ítem**. Por eso los
reportes usan el consenso por defecto; `--todas` incluye además las
respuestas individuales.

**Los momentos solo se nombran si existen.** Un taller que se hace por
primera vez registra un único juego de valoraciones por cultura: hay un
solo número y llamarlo "PASADO" no aporta nada. En ese caso el reporte
—HTML, Excel, CLI y la tabla de la interfaz— omite por completo las
palabras PASADO, ACTUAL, Momento y Brecha, y en su lugar explica que la
evolución se obtiene repitiendo el taller. Solo cuando ambos momentos
tienen datos aparecen las columnas, la leyenda y la sección de brecha.

## Arquitectura

```
src/taller_cultura/
├── domain/            # Núcleo: entidades y reglas. Sin I/O, sin dependencias.
│   ├── model.py        (TipoCultura, CategoriaAspecto, Momento, Valoracion,
│   │                    SesionTaller, Calificador, Aspecto, Calificacion)
│   ├── services.py      (CalculadoraResumen, ComparadorSesiones, ResumenTaller,
│   │                     ComparacionTaller, DiagnosticoTaller)
│   └── exceptions.py
├── application/        # Casos de uso + puertos (contratos hacia infraestructura)
│   ├── ports.py         (LectorTaller, RepositorioTaller, ExportadorReporte,
│   │                     ExportadorComparativo, ExportadorPlantilla)
│   ├── validacion.py    (Severidad, Hallazgo, ResultadoValidacion)
│   └── use_cases.py     (ValidarArchivoTaller, ImportarSesionTaller,
│                         ListarSesiones, CalcularReporteTaller,
│                         CompararSesiones, Exportar*)
├── infrastructure/     # Adaptadores: SÍ conocen pandas/openpyxl/sqlite3/tkinter
│   ├── adapters/
│   │   ├── excel_reader.py     (LectorTallerExcel — parsea y valida el .xlsx)
│   │   ├── sqlite_repo.py      (RepositorioTallerSQLite — multi-sesión)
│   │   ├── excel_writer.py     (ExportadorReporteExcel)
│   │   ├── html_writer.py      (ExportadorReporteHTML — con tarta y PDF)
│   │   ├── html_comparativo.py (ExportadorComparativoHTML — antes vs ahora)
│   │   └── plantilla_writer.py (ExportadorPlantillaExcel — solo hoja TALLER)
│   └── gui/
│       └── app.py       (adaptador primario: interfaz de escritorio en tkinter)
└── main.py             # Composición (inyección de dependencias) + CLI
```

El dominio no importa nada de `infrastructure`; los puertos en
`application/ports.py` son la frontera del hexágono. La GUI y la CLI son dos
adaptadores primarios sobre los mismos casos de uso.

## Instalación

Funciona igual en **Windows, Linux y macOS** con Python 3.10 o superior.

```bash
pip install -r requirements.txt
```

En Linux, la interfaz gráfica necesita tkinter, que en muchas
distribuciones viene en un paquete aparte (en Windows y macOS ya viene con
Python):

```bash
sudo apt install python3-tk
```

Si falta, la CLI sigue funcionando sin problema y el comando `gui` explica
cómo instalarlo. Detalles que se cuidan para que el comportamiento sea el
mismo en los tres sistemas —y que los tests verifican:

- Todas las rutas se construyen con `pathlib`; no hay rutas absolutas ni
  separadores escritos a mano.
- Toda lectura y escritura de texto declara `encoding="utf-8"` (si no,
  Python usaría cp1252 en Windows y se corromperían los acentos).
- La salida por consola tolera terminales que no son UTF-8.
- La interfaz elige el tema nativo disponible (`aqua` en macOS, `vista` en
  Windows, `clam` en Linux) en lugar de asumir uno.
- Los filtros de los diálogos usan `*` y no `*.*`, que fuera de Windows
  deja fuera los archivos sin extensión.

## Uso — interfaz gráfica

```bash
python -m taller_cultura gui
```

## Uso — línea de comandos

Revisar el archivo sin importarlo:

```bash
python -m taller_cultura validar --excel "Taller.xlsx"
```

Registrar un taller (la versión se numera sola si la empresa ya existe):

```bash
python -m taller_cultura importar --excel "Taller.xlsx" --empresa "ACME" --fecha 2026-03-14
```

Ver las sesiones registradas y generar el reporte de una:

```bash
python -m taller_cultura sesiones
```

```bash
python -m taller_cultura reporte --sesion 1 --salida data/reporte.html
```

Comparar dos sesiones (antes y ahora):

```bash
python -m taller_cultura comparar --antes 1 --ahora 2 --salida data/comparativo.html
```

Generar el archivo que se reparte (solo la hoja TALLER):

```bash
python -m taller_cultura plantilla --excel "Taller.xlsx" --salida "TALLER para enviar.xlsx"
```

Los reportes HTML son archivos únicos sin dependencias externas (funcionan
sin conexión) e incluyen un botón **«Descargar como PDF»** que abre el
diálogo de impresión con estilos A4 ya preparados.

## Validación del archivo

Antes de procesar, el archivo se revisa y se reporta lo que se encuentre:

- **ERROR** — no se puede procesar y la importación se detiene: falta la hoja
  `TALLER`, o su estructura no corresponde a la del taller.
- **AVISO** — se procesa, pero conviene saberlo al leer el reporte: no hay
  filas de consenso, falta un momento (PASADO/ACTUAL), la cobertura es baja,
  o hay ítems repetidos que pesan doble en los promedios.

## Sobre la fidelidad de los datos

El parser se validó celda por celda contra el libro original: captura
**todas** las respuestas de la hoja TALLER, sin perder ninguna y sin contar
dos veces las filas de eco (los `VLOOKUP` que repiten el consenso).

Al contrastar los agregados contra las hojas `FINAL` y `CULTURAS` del propio
Excel, **Comportamientos y Sistemas coinciden al 100 %**. Las diferencias que
aparecen en Símbolos provienen de fórmulas rotas en el libro original, no del
cálculo de esta aplicación:

- `FINAL!F38:L39` (los conteos de R y V de Símbolos) usan
  `COUNTIF(F32:F35, …)` —un rango local de 4 celdas de la propia hoja
  `FINAL`— en lugar de contar las filas de consenso de `TALLER`, como sí hace
  correctamente la columna D.
- `CULTURAS!H6` suma `FINAL!H14+H38+H67` (columna de EQUIPO UNICO) cuando
  debería sumar la columna `L` (LAS PERSONAS PRIMERO), de modo que ambas
  culturas muestran el mismo valor de R.
- `FINAL!D66` omite la fila 518, uno de los ítems de Sistemas.

Esta aplicación calcula directamente desde la hoja TALLER, así que no
arrastra ninguno de esos errores.

## Tests

```bash
pytest
```

Los tests de integración se saltan solos si el Excel no está presente. Dos
fijan invariantes que bugs reales llegaron a romper:

- `test_captura_todas_las_respuestas_de_la_hoja` — el detector de bloques
  exigía una etiqueta de categoría en la columna B, pero **solo el primer
  ítem de cada categoría la lleva**; los demás la heredan, así que se perdía
  la mayoría de los ítems y sus calificaciones.
- `test_la_plantilla_conserva_todas_las_respuestas` — al limpiar las fórmulas
  rotas (`#ERROR!`) de la columna B, esos huecos cortaban la racha de filas
  de respuesta y se perdían las filas CONSENSO siguientes.
