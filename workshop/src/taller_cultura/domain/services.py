"""Servicios de dominio: lógica de negocio pura, sin I/O.

Reciben colecciones de entidades ya cargadas (por la capa de aplicación) y
producen resultados de negocio. No conocen sqlite, pandas ni Excel.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .model import (
    Aspecto,
    Calificacion,
    CategoriaAspecto,
    Momento,
    TipoCultura,
    Valoracion,
)


@dataclass(frozen=True, slots=True)
class ResumenCultura:
    """Consolidado de un tipo de cultura en un momento (PASADO/ACTUAL)."""

    tipo_cultura: TipoCultura
    momento: Momento
    conteo_por_valoracion: dict[Valoracion, int]

    @property
    def total(self) -> int:
        return sum(self.conteo_por_valoracion.values())

    @property
    def promedio_ponderado(self) -> float:
        if self.total == 0:
            return 0.0
        suma = sum(v.peso * n for v, n in self.conteo_por_valoracion.items())
        return round(suma / self.total, 2)

    @property
    def porcentaje_valor_alto(self) -> float:
        """Porcentaje de respuestas con el símbolo de mayor peso (V)."""
        if self.total == 0:
            return 0.0
        alto = self.conteo_por_valoracion.get(Valoracion.ALTO, 0)
        return round(100 * alto / self.total, 1)


@dataclass(frozen=True, slots=True)
class ResumenCategoria:
    """Consolidado de un tipo de cultura, DESGLOSADO por categoría (Tipo de
    cultura / Comportamientos / Símbolos / Sistemas), en un momento dado.
    Misma forma que `ResumenCultura`, con la categoría como dimensión extra.
    """

    tipo_cultura: TipoCultura
    categoria: CategoriaAspecto
    momento: Momento
    conteo_por_valoracion: dict[Valoracion, int]

    @property
    def total(self) -> int:
        return sum(self.conteo_por_valoracion.values())

    @property
    def promedio_ponderado(self) -> float:
        if self.total == 0:
            return 0.0
        suma = sum(v.peso * n for v, n in self.conteo_por_valoracion.items())
        return round(suma / self.total, 2)


@dataclass(frozen=True, slots=True)
class ResumenTaller:
    """Resultado completo del taller: un ResumenCultura por cultura y momento."""

    resumenes: tuple[ResumenCultura, ...]

    def para(self, tipo_cultura: TipoCultura, momento: Momento) -> ResumenCultura | None:
        for r in self.resumenes:
            if r.tipo_cultura is tipo_cultura and r.momento is momento:
                return r
        return None

    @property
    def momentos_con_datos(self) -> tuple[Momento, ...]:
        """Qué momentos tienen realmente respuestas, en orden temporal."""
        presentes = {r.momento for r in self.resumenes if r.total > 0}
        return tuple(m for m in (Momento.PASADO, Momento.ACTUAL) if m in presentes)

    @property
    def distingue_momentos(self) -> bool:
        """¿Tiene sentido hablar de PASADO y ACTUAL en este taller?

        Solo cuando ambos momentos están llenos. Si el taller registró una
        única medición —el caso de un taller que se hace por primera vez—
        nombrar el momento no aporta nada: hay un solo valor por cultura y
        llamarlo "PASADO" solo confunde. Quien consume el resumen usa esta
        propiedad para decidir si menciona los momentos o los omite.
        """
        return len(self.momentos_con_datos) > 1

    @property
    def momento_unico(self) -> Momento | None:
        """El único momento con datos, si es que hay uno solo."""
        momentos = self.momentos_con_datos
        return momentos[0] if len(momentos) == 1 else None

    def promedio(self, tipo_cultura: TipoCultura, momento: Momento | None = None) -> float | None:
        """Promedio de una cultura. Sin `momento`, el del único que haya."""
        if momento is None:
            momento = self.momento_unico
            if momento is None:
                return None
        resumen = self.para(tipo_cultura, momento)
        if resumen is None or resumen.total == 0:
            return None
        return resumen.promedio_ponderado

    def brecha(self, tipo_cultura: TipoCultura) -> float:
        """Diferencia entre el promedio ACTUAL y el PASADO (evolución deseada)."""
        actual = self.para(tipo_cultura, Momento.ACTUAL)
        pasado = self.para(tipo_cultura, Momento.PASADO)
        if actual is None or pasado is None:
            return 0.0
        return round(actual.promedio_ponderado - pasado.promedio_ponderado, 2)

    def ranking_por_promedio(self, momento: Momento) -> list[ResumenCultura]:
        return sorted(
            (r for r in self.resumenes if r.momento is momento),
            key=lambda r: r.promedio_ponderado,
            reverse=True,
        )


@dataclass(frozen=True, slots=True)
class ComparacionCultura:
    """Cómo se movió un tipo de cultura entre dos sesiones del taller."""

    tipo_cultura: TipoCultura
    promedio_antes: float | None
    promedio_ahora: float | None

    @property
    def es_comparable(self) -> bool:
        return self.promedio_antes is not None and self.promedio_ahora is not None

    @property
    def variacion(self) -> float | None:
        if not self.es_comparable:
            return None
        return round(self.promedio_ahora - self.promedio_antes, 2)

    @property
    def variacion_porcentual(self) -> float | None:
        """Cambio relativo. `None` si no hay base contra la cual comparar."""
        if not self.es_comparable or self.promedio_antes == 0:
            return None
        return round(100 * (self.promedio_ahora - self.promedio_antes) / self.promedio_antes, 1)

    @property
    def mejoro(self) -> bool:
        return self.variacion is not None and self.variacion > 0

    @property
    def empeoro(self) -> bool:
        return self.variacion is not None and self.variacion < 0


@dataclass(frozen=True, slots=True)
class ComparacionTaller:
    """Resultado de contrastar dos sesiones del taller de la misma empresa."""

    comparaciones: tuple[ComparacionCultura, ...]

    def para(self, tipo_cultura: TipoCultura) -> ComparacionCultura | None:
        for c in self.comparaciones:
            if c.tipo_cultura is tipo_cultura:
                return c
        return None

    @property
    def comparables(self) -> tuple[ComparacionCultura, ...]:
        return tuple(c for c in self.comparaciones if c.es_comparable)

    @property
    def mayor_avance(self) -> ComparacionCultura | None:
        candidatas = [c for c in self.comparables if c.mejoro]
        return max(candidatas, key=lambda c: c.variacion, default=None)

    @property
    def mayor_retroceso(self) -> ComparacionCultura | None:
        candidatas = [c for c in self.comparables if c.empeoro]
        return min(candidatas, key=lambda c: c.variacion, default=None)


class ComparadorSesiones:
    """Servicio de dominio: contrasta el resumen de dos sesiones.

    Compara siempre el mismo momento en ambas sesiones (por defecto
    PASADO, que es el que el taller llena primero); comparar el PASADO de
    una contra el ACTUAL de otra mezclaría dos preguntas distintas.
    """

    def comparar(
        self,
        resumen_antes: "ResumenTaller",
        resumen_ahora: "ResumenTaller",
        momento: Momento = Momento.PASADO,
    ) -> ComparacionTaller:
        comparaciones = []
        for tipo_cultura in TipoCultura:
            antes = resumen_antes.para(tipo_cultura, momento)
            ahora = resumen_ahora.para(tipo_cultura, momento)
            comparaciones.append(
                ComparacionCultura(
                    tipo_cultura=tipo_cultura,
                    promedio_antes=antes.promedio_ponderado if antes and antes.total else None,
                    promedio_ahora=ahora.promedio_ponderado if ahora and ahora.total else None,
                )
            )
        return ComparacionTaller(comparaciones=tuple(comparaciones))


@dataclass(frozen=True, slots=True)
class DiagnosticoTaller:
    """Cobertura de los datos: cuánto del taller está realmente calificado.

    Sirve para leer el resumen con criterio: un promedio calculado sobre 3
    respuestas no vale lo mismo que uno calculado sobre 30.
    """

    total_aspectos: int
    aspectos_calificados: int
    respuestas_consenso: int
    respuestas_individuales: int

    @property
    def aspectos_sin_calificar(self) -> int:
        return self.total_aspectos - self.aspectos_calificados

    @property
    def porcentaje_cobertura(self) -> float:
        if self.total_aspectos == 0:
            return 0.0
        return round(100 * self.aspectos_calificados / self.total_aspectos, 1)


class CalculadoraResumen:
    """Servicio de dominio que agrega calificaciones en resúmenes por cultura."""

    def diagnosticar(
        self,
        aspectos: list[Aspecto],
        calificaciones: list[Calificacion],
    ) -> DiagnosticoTaller:
        ids_validos = {a.id for a in aspectos if a.id is not None}
        calificados = {c.aspecto_id for c in calificaciones if c.aspecto_id in ids_validos}
        return DiagnosticoTaller(
            total_aspectos=len(aspectos),
            aspectos_calificados=len(calificados),
            respuestas_consenso=sum(1 for c in calificaciones if c.es_consenso),
            respuestas_individuales=sum(1 for c in calificaciones if not c.es_consenso),
        )

    def calcular(
        self,
        aspectos: list[Aspecto],
        calificaciones: list[Calificacion],
        *,
        solo_consenso: bool = False,
    ) -> ResumenTaller:
        aspecto_por_id = {a.id: a for a in aspectos if a.id is not None}

        contadores: dict[tuple[TipoCultura, Momento], Counter[Valoracion]] = {}
        for calificacion in calificaciones:
            if solo_consenso and not calificacion.es_consenso:
                continue
            aspecto = aspecto_por_id.get(calificacion.aspecto_id)
            if aspecto is None:
                continue
            clave = (aspecto.tipo_cultura, calificacion.momento)
            contadores.setdefault(clave, Counter())[calificacion.valoracion] += 1

        resumenes = tuple(
            ResumenCultura(
                tipo_cultura=tipo_cultura,
                momento=momento,
                conteo_por_valoracion=dict(contador),
            )
            for (tipo_cultura, momento), contador in sorted(
                contadores.items(), key=lambda kv: (kv[0][0].value, kv[0][1].value)
            )
        )
        return ResumenTaller(resumenes=resumenes)

    def calcular_por_categoria(
        self,
        aspectos: list[Aspecto],
        calificaciones: list[Calificacion],
    ) -> dict[tuple[TipoCultura, CategoriaAspecto, Momento], Counter[Valoracion]]:
        aspecto_por_id = {a.id: a for a in aspectos if a.id is not None}
        resultado: dict[tuple[TipoCultura, CategoriaAspecto, Momento], Counter[Valoracion]] = {}
        for calificacion in calificaciones:
            aspecto = aspecto_por_id.get(calificacion.aspecto_id)
            if aspecto is None:
                continue
            clave = (aspecto.tipo_cultura, aspecto.categoria, calificacion.momento)
            resultado.setdefault(clave, Counter())[calificacion.valoracion] += 1
        return resultado

    def calcular_detalle_por_categoria(
        self,
        aspectos: list[Aspecto],
        calificaciones: list[Calificacion],
    ) -> tuple[ResumenCategoria, ...]:
        """Igual que `calcular_por_categoria`, pero envuelto en `ResumenCategoria`
        (con `promedio_ponderado` ya calculado) en vez de `Counter`s crudos.
        """
        contadores = self.calcular_por_categoria(aspectos, calificaciones)
        return tuple(
            ResumenCategoria(
                tipo_cultura=tipo_cultura,
                categoria=categoria,
                momento=momento,
                conteo_por_valoracion=dict(contador),
            )
            for (tipo_cultura, categoria, momento), contador in sorted(
                contadores.items(), key=lambda kv: (kv[0][0].value, kv[0][1].value, kv[0][2].value)
            )
        )
