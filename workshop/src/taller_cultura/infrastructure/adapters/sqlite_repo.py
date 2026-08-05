"""Adaptador de salida: persistencia en SQLite.

Implementa el puerto `RepositorioTaller`. Las escrituras usan `sqlite3`
directamente (control fino sobre ids autoincrementales dentro de una
transacción); las lecturas usan `pandas.read_sql_query`, que es la forma
natural de traer datos tabulares de vuelta al dominio.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from taller_cultura.application.ports import RepositorioTaller
from taller_cultura.domain.model import (
    Aspecto,
    Calificacion,
    Calificador,
    CategoriaAspecto,
    Empresa,
    Momento,
    TipoCultura,
    Valoracion,
)

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS calificadores (
    codigo INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL,
    empresa_id INTEGER REFERENCES empresas(id)
);

CREATE TABLE IF NOT EXISTS aspectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_cultura TEXT NOT NULL,
    categoria TEXT NOT NULL,
    orden INTEGER NOT NULL,
    texto TEXT NOT NULL,
    UNIQUE (tipo_cultura, categoria, orden)
);

CREATE TABLE IF NOT EXISTS calificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aspecto_id INTEGER NOT NULL REFERENCES aspectos(id),
    calificador_codigo INTEGER NOT NULL REFERENCES calificadores(codigo),
    momento TEXT NOT NULL,
    valoracion TEXT NOT NULL,
    es_consenso INTEGER NOT NULL DEFAULT 0
);
"""


class RepositorioTallerSQLite(RepositorioTaller):
    """Repositorio de taller respaldado por un archivo SQLite."""

    def __init__(self, ruta_bd: str | Path) -> None:
        self._ruta = Path(ruta_bd)
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._conexion = sqlite3.connect(self._ruta)
        self._conexion.execute("PRAGMA foreign_keys = ON;")
        self._conexion.executescript(ESQUEMA_SQL)
        self._conexion.commit()

    def cerrar(self) -> None:
        self._conexion.close()

    def __enter__(self) -> "RepositorioTallerSQLite":
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    # -- escrituras ---------------------------------------------------

    def guardar_empresas(self, empresas: list[Empresa]) -> dict[str, int]:
        cursor = self._conexion.cursor()
        mapa_ids: dict[str, int] = {}
        for empresa in empresas:
            cursor.execute(
                "INSERT INTO empresas (nombre) VALUES (?) "
                "ON CONFLICT(nombre) DO UPDATE SET nombre = excluded.nombre",
                (empresa.nombre,),
            )
            fila = cursor.execute(
                "SELECT id FROM empresas WHERE nombre = ?", (empresa.nombre,)
            ).fetchone()
            mapa_ids[empresa.nombre] = fila[0]
        self._conexion.commit()
        return mapa_ids

    def guardar_calificadores(self, calificadores: list[Calificador]) -> None:
        cursor = self._conexion.cursor()
        cursor.executemany(
            "INSERT INTO calificadores (codigo, nombre, empresa_id) VALUES (?, ?, ?) "
            "ON CONFLICT(codigo) DO UPDATE SET nombre = excluded.nombre",
            [(c.codigo, c.nombre, c.empresa_id) for c in calificadores],
        )
        self._conexion.commit()

    def guardar_aspectos(self, aspectos: list[Aspecto]) -> dict[int, int]:
        cursor = self._conexion.cursor()
        mapa_ids: dict[int, int] = {}
        for indice, aspecto in enumerate(aspectos):
            cursor.execute(
                "INSERT INTO aspectos (tipo_cultura, categoria, orden, texto) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(tipo_cultura, categoria, orden) DO UPDATE SET texto = excluded.texto",
                (aspecto.tipo_cultura.value, aspecto.categoria.value, aspecto.orden, aspecto.texto),
            )
            fila = cursor.execute(
                "SELECT id FROM aspectos WHERE tipo_cultura = ? AND categoria = ? AND orden = ?",
                (aspecto.tipo_cultura.value, aspecto.categoria.value, aspecto.orden),
            ).fetchone()
            mapa_ids[indice] = fila[0]
        self._conexion.commit()
        return mapa_ids

    def guardar_calificaciones(self, calificaciones: list[Calificacion]) -> None:
        cursor = self._conexion.cursor()
        cursor.execute("DELETE FROM calificaciones")
        cursor.executemany(
            "INSERT INTO calificaciones "
            "(aspecto_id, calificador_codigo, momento, valoracion, es_consenso) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
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

    # -- lecturas (pandas) ---------------------------------------------

    def listar_aspectos(self) -> list[Aspecto]:
        df = pd.read_sql_query(
            "SELECT id, tipo_cultura, categoria, orden, texto FROM aspectos ORDER BY id", self._conexion
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

    def listar_calificaciones(self) -> list[Calificacion]:
        df = pd.read_sql_query(
            "SELECT aspecto_id, calificador_codigo, momento, valoracion, es_consenso "
            "FROM calificaciones ORDER BY id",
            self._conexion,
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

    def listar_calificadores(self) -> list[Calificador]:
        df = pd.read_sql_query(
            "SELECT codigo, nombre, empresa_id FROM calificadores ORDER BY codigo", self._conexion
        )
        return [
            Calificador(
                codigo=int(fila.codigo),
                nombre=fila.nombre,
                empresa_id=None if pd.isna(fila.empresa_id) else int(fila.empresa_id),
            )
            for fila in df.itertuples(index=False)
        ]

    def listar_empresas(self) -> list[Empresa]:
        df = pd.read_sql_query("SELECT id, nombre FROM empresas ORDER BY id", self._conexion)
        return [Empresa(id=int(fila.id), nombre=fila.nombre) for fila in df.itertuples(index=False)]
