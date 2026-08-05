# Taller de Cultura — arquitectura hexagonal

ETL y cálculo del "Taller de diagnóstico de cultura organizacional" (el
Excel `Taller para pasar a David.xlsx`): lee el archivo original, lo
persiste en SQLite y calcula un resumen agregado (por tipo de cultura y
momento PASADO/ACTUAL), exportable a un nuevo `.xlsx` limpio.

## El dominio de negocio (qué hace el Excel original)

El taller evalúa 5 **tipos de cultura** organizacional (LOGRO, CENTRADA EN
EL CLIENTE, EQUIPO UNICO, INNOVADORA, LAS PERSONAS PRIMERO) en varias
**categorías** (Tipo de cultura, Comportamientos, Símbolos, Sistemas).
Cada categoría tiene varios **ítems** (frases descriptivas), y cada ítem
lo califica un grupo de **calificadores** (hasta 12 personas + un
"CONSENSO") en dos **momentos**: PASADO y ACTUAL, usando un semáforo de
tres símbolos: `R` (bajo), `A` (medio), `V` (alto) — pesos 0/1/2,
replicando exactamente la fórmula original de la hoja de cálculo.

El archivo original entregado es una **plantilla en blanco** (sin
respuestas reales cargadas, salvo un puñado de celdas de ejemplo), pensada
para llenarse durante un taller en vivo. Esta aplicación funciona igual
con cualquier copia de esa plantilla, esté vacía o llena.

## Arquitectura

```
src/taller_cultura/
├── domain/            # Núcleo: entidades, value objects, servicios. Sin I/O.
│   ├── model.py        (TipoCultura, CategoriaAspecto, Momento, Valoracion,
│   │                    Empresa, Calificador, Aspecto, Calificacion)
│   ├── services.py      (CalculadoraResumen, ResumenTaller, ResumenCultura)
│   └── exceptions.py
├── application/        # Casos de uso + puertos (contratos hacia infraestructura)
│   ├── ports.py         (LectorTaller, RepositorioTaller, ExportadorReporte)
│   └── use_cases.py     (ImportarTallerDesdeExcel, CalcularResumenTaller,
│                         CalcularReporteTaller, ExportarReporteTaller)
├── infrastructure/     # Adaptadores concretos: SÍ conocen pandas/openpyxl/sqlite3
│   └── adapters/
│       ├── excel_reader.py   (LectorTallerExcel — parsea el .xlsx original)
│       ├── sqlite_repo.py    (RepositorioTallerSQLite)
│       ├── excel_writer.py   (ExportadorReporteExcel)
│       └── html_writer.py    (ExportadorReporteHTML — reporte visual autocontenido)
└── main.py             # Composición (inyección de dependencias) + CLI
```

`ExportadorReporte` es un puerto único con dos adaptadores intercambiables
(Excel y HTML); `main.py` elige uno u otro según la extensión que se le pase
a `--reporte` (`.xlsx` o `.html`), sin que el dominio ni los casos de uso se
enteren de la diferencia.

El dominio no importa nada de `infrastructure`; los puertos en
`application/ports.py` son la frontera del hexágono. Cambiar de SQLite a
otra base de datos, o de Excel a CSV, solo requiere un nuevo adaptador que
implemente el puerto correspondiente — el dominio y los casos de uso no
se tocan.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso (CLI)

Importar el Excel original a una base SQLite:

```bash
python -m taller_cultura importar --excel "Taller para pasar a David (1).xlsx" --bd taller.db
```

Calcular y mostrar el resumen (y opcionalmente exportarlo a Excel o a un
reporte HTML visual con gráficos):

```bash
python -m taller_cultura resumen --bd taller.db --reporte reporte_resumen.xlsx
python -m taller_cultura resumen --bd taller.db --reporte reporte.html
```

Usar solo las calificaciones de consenso:

```bash
python -m taller_cultura resumen --bd taller.db --consenso
```

## Tests

```bash
pytest
```
