"""Excepciones propias del dominio.

Se separan de cualquier error técnico (de la base de datos o del lector de
Excel) para que la capa de aplicación pueda distinguir "el usuario/los datos
están mal" de "falló la infraestructura".
"""


class DomainError(Exception):
    """Error base de todo el dominio."""


class ValoracionInvalida(DomainError):
    """El símbolo/valor de la calificación no pertenece al semáforo A/R/V."""


class MomentoInvalido(DomainError):
    """El momento no es PASADO ni ACTUAL."""


class CategoriaInvalida(DomainError):
    """La categoría del aspecto no está en el catálogo conocido."""


class TipoCulturaDesconocido(DomainError):
    """El nombre del tipo de cultura no coincide con ninguno del catálogo."""
