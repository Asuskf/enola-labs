"""Taller de diagnóstico de cultura organizacional — arquitectura hexagonal.

- `domain`: entidades y reglas de negocio puras (sin dependencias externas).
- `application`: casos de uso y puertos (contratos hacia infraestructura).
- `infrastructure`: adaptadores concretos (Excel vía pandas/openpyxl, SQLite).
- `main`: punto de composición (inyección de dependencias) y CLI.
"""
