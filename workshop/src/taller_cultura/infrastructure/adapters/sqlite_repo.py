"""Adaptador de salida: persistencia en SQLite.

Implementa el puerto `RepositorioTaller`. Guarda **varias sesiones** del
taller (una por empresa y fecha), que es lo que permite comparar una
aplicación del taller con la siguiente.

Las escrituras usan `sqlite3` directamente (control fino sobre los ids
autoincrementales dentro de una transacción); las lecturas usan
`pandas.read_sql_query`, la forma natural de traer datos tabulares.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from taller_cultura.application.ports import RepositorioTaller
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    Calificador,
    CategoriaAspecto,
    Momento,
    SesionTaller,
    TipoCultura,
    Valoracion,
)

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa TEXT NOT NULL,
    fecha_taller TEXT NOT NULL,
    numero_version INTEGER NOT NULL,
    archivo_origen TEXT NOT NULL DEFAULT '',
    creada_en TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (empresa, numero_version)
);

CREATE TABLE IF NOT EXISTS calificadores (
    sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    codigo INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    PRIMARY KEY (sesion_id, codigo)
);

CREATE TABLE IF NOT EXISTS aspectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    tipo_cultura TEXT NOT NULL,
    categoria TEXT NOT NULL,
    orden INTEGER NOT NULL,
    texto TEXT NOT NULL,
    UNIQUE (sesion_id, tipo_cultura, categoria, orden)
);

CREATE TABLE IF NOT EXISTS calificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sesion_id INTEGER NOT NULL REFERENCES sesiones(id) ON DELETE CASCADE,
    aspecto_id INTEGER NOT NULL REFERENCES aspectos(id) ON DELETE CASCADE,
    calificador_codigo INTEGER NOT NULL,
    momento TEXT NOT NULL,
    valoracion TEXT NOT NULL,
    es_consenso INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_aspectos_sesion ON aspectos(sesion_id);
CREATE INDEX IF NOT EXISTS idx_calificaciones_sesion ON calificaciones(sesion_id);
"""

TABLAS_DEL_ESQUEMA = ("sesiones", "calificadores", "aspectos", "calificaciones")


class RepositorioTallerSQLite(RepositorioTaller):
    """Repositorio de sesiones del taller respaldado por un archivo SQLite."""

    def __init__(self, ruta_bd: str | Path) -> None:
        self._ruta = Path(ruta_bd)
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._conexion = sqlite3.connect(self._ruta)
        self._conexion.execute("PRAGMA foreign_keys = ON;")
        self._migrar_si_hace_falta()
        self._conexion.executescript(ESQUEMA_SQL)
        self._conexion.commit()

    def _migrar_si_hace_falta(self) -> None:
        """Descarta un esquema anterior incompatible (sin `sesiones`).

        La base es un artefacto derivado: todo su contenido se reconstruye
        importando el Excel de nuevo, así que recrearla no pierde nada que
        no se pueda regenerar.
        """
        cursor = self._conexion.cursor()
        tablas = {
            fila[0]
            for fila in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if not tablas or "sesiones" in tablas:
            return
        for tabla in ("calificaciones", "aspectos", "calificadores", "empresas"):
            if tabla in tablas:
                cursor.execute(f"DROP TABLE {tabla}")
        self._conexion.commit()

    def cerrar(self) -> None:
        self._conexion.close()

    def __enter__(self) -> "RepositorioTallerSQLite":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    # -- sesiones ---------------------------------------------------------

    def crear_sesion(self, sesion: SesionTaller) -> SesionTaller:
        cursor = self._conexion.cursor()
        cursor.execute(
            "INSERT INTO sesiones (empresa, fecha_taller, numero_version, archivo_origen) "
            "VALUES (?, ?, ?, ?)",
            (
                sesion.empresa,
                sesion.fecha_taller.isoformat(),
                sesion.numero_version,
                sesion.archivo_origen,
            ),
        )
        self._conexion.commit()
        return SesionTaller(
            id=cursor.lastrowid,
            empresa=sesion.empresa,
            fecha_taller=sesion.fecha_taller,
            numero_version=sesion.numero_version,
            archivo_origen=sesion.archivo_origen,
        )

    def listar_sesiones(self, empresa: str | None = None) -> list[SesionTaller]:
        consulta = (
            "SELECT id, empresa, fecha_taller, numero_version, archivo_origen FROM sesiones"
        )
        parametros: tuple = ()
        if empresa:
            consulta += " WHERE empresa = ?"
            parametros = (empresa,)
        consulta += " ORDER BY empresa, numero_version"

        df = pd.read_sql_query(consulta, self._conexion, params=parametros)
        return [self._a_sesion(fila) for fila in df.itertuples(index=False)]

    def obtener_sesion(self, sesion_id: int) -> SesionTaller | None:
        df = pd.read_sql_query(
            "SELECT id, empresa, fecha_taller, numero_version, archivo_origen "
            "FROM sesiones WHERE id = ?",
            self._conexion,
            params=(sesion_id,),
        )
        if df.empty:
            return None
        return self._a_sesion(next(df.itertuples(index=False)))

    def siguiente_version(self, empresa: str) -> int:
        fila = self._conexion.execute(
            "SELECT COALESCE(MAX(numero_version), 0) FROM sesiones WHERE empresa = ?",
            (empresa,),
        ).fetchone()
        return int(fila[0]) + 1

    def eliminar_sesion(self, sesion_id: int) -> None:
        self._conexion.execute("DELETE FROM sesiones WHERE id = ?", (sesion_id,))
        self._conexion.commit()

    @staticmethod
    def _a_sesion(fila) -> SesionTaller:
        return SesionTaller(
            id=int(fila.id),
            empresa=fila.empresa,
            fecha_taller=date.fromisoformat(fila.fecha_taller),
            numero_version=int(fila.numero_version),
            archivo_origen=fila.archivo_origen or "",
        )

    # -- escrituras del contenido -------------------------------------------

    def guardar_calificadores(self, sesion_id: int, calificadores: list[Calificador]) -> None:
        self._conexion.executemany(
            "INSERT INTO calificadores (sesion_id, codigo, nombre) VALUES (?, ?, ?) "
            "ON CONFLICT(sesion_id, codigo) DO UPDATE SET nombre = excluded.nombre",
            [(sesion_id, c.codigo, c.nombre) for c in calificadores],
        )
        self._conexion.commit()

    def guardar_aspectos(self, sesion_id: int, aspectos: list[Aspecto]) -> dict[int, int]:
        cursor = self._conexion.cursor()
        mapa_ids: dict[int, int] = {}
        for indice, aspecto in enumerate(aspectos):
            cursor.execute(
                "INSERT INTO aspectos (sesion_id, tipo_cultura, categoria, orden, texto) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(sesion_id, tipo_cultura, categoria, orden) "
                "DO UPDATE SET texto = excluded.texto",
                (
                    sesion_id,
                    aspecto.tipo_cultura.value,
                    aspecto.categoria.value,
                    aspecto.orden,
                    aspecto.texto,
                ),
            )
            fila = cursor.execute(
                "SELECT id FROM aspectos WHERE sesion_id = ? AND tipo_cultura = ? "
                "AND categoria = ? AND orden = ?",
                (sesion_id, aspecto.tipo_cultura.value, aspecto.categoria.value, aspecto.orden),
            ).fetchone()
            mapa_ids[indice] = fila[0]
        self._conexion.commit()
        return mapa_ids

    def guardar_calificaciones(self, sesion_id: int, calificaciones: list[Calificacion]) -> None:
        cursor = self._conexion.cursor()
        cursor.execute("DELETE FROM calificaciones WHERE sesion_id = ?", (sesion_id,))
        cursor.executemany(
            "INSERT INTO calificaciones "
            "(sesion_id, aspecto_id, calificador_codigo, momento, valoracion, es_consenso) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    sesion_id,
                    c.aspecto_id,
                    c.calificador_codigo,
                    c.momento.value,
                    c.valoracion.value,
                    int(c.es_consenso),
                )
                for c in calificaciones
            ],
        )
        self._conexion.commit()

    # -- lecturas (pandas) ---------------------------------------------------

    def listar_aspectos(self, sesion_id: int) -> list[Aspecto]:
        df = pd.read_sql_query(
            "SELECT id, tipo_cultura, categoria, orden, texto FROM aspectos "
            "WHERE sesion_id = ? ORDER BY id",
            self._conexion,
            params=(sesion_id,),
        )
        return [
            Aspecto(
                id=int(fila.id),
                tipo_cultura=TipoCultura.desde_texto(fila.tipo_cultura),
                categoria=CategoriaAspecto.desde_texto(fila.categoria),
                orden=int(fila.orden),
                texto=fila.texto,
            )
            for fila in df.itertuples(index=False)
        ]

    def listar_calificaciones(self, sesion_id: int) -> list[Calificacion]:
        df = pd.read_sql_query(
            "SELECT aspecto_id, calificador_codigo, momento, valoracion, es_consenso "
            "FROM calificaciones WHERE sesion_id = ? ORDER BY id",
            self._conexion,
            params=(sesion_id,),
        )
        return [
            Calificacion(
                aspecto_id=int(fila.aspecto_id),
                calificador_codigo=int(fila.calificador_codigo),
                momento=Momento.desde_texto(fila.momento),
                valoracion=Valoracion.desde_texto(fila.valoracion),
                es_consenso=bool(fila.es_consenso),
            )
            for fila in df.itertuples(index=False)
        ]

    def listar_calificadores(self, sesion_id: int) -> list[Calificador]:
        df = pd.read_sql_query(
            "SELECT codigo, nombre FROM calificadores WHERE sesion_id = ? ORDER BY codigo",
            self._conexion,
            params=(sesion_id,),
        )
        return [
            Calificador(codigo=int(fila.codigo), nombre=fila.nombre)
            for fila in df.itertuples(index=False)
        ]
