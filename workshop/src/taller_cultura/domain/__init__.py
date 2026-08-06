"""Núcleo del dominio (hexágono interno).

Este paquete no importa NADA de infraestructura, pandas, sqlite ni de los
adaptadores. Solo contiene reglas de negocio puras: entidades, objetos de
valor, excepciones y servicios de dominio.
"""

from .model import (
    Aspecto,
    CategoriaAspecto,
    Calificacion,
    Calificador,
    Empresa,
    Momento,
    TipoCultura,
    Valoracion,
)
from .services import (
    CalculadoraResumen,
    DiagnosticoTaller,
    ResumenCategoria,
    ResumenCultura,
    ResumenTaller,
)

__all__ = [
    "Aspecto",
    "CategoriaAspecto",
    "Calificacion",
    "Calificador",
    "Empresa",
    "Momento",
    "TipoCultura",
    "Valoracion",
    "CalculadoraResumen",
    "DiagnosticoTaller",
    "ResumenCategoria",
    "ResumenCultura",
    "ResumenTaller",
]
