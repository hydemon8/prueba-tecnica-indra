"""Catálogo de tools del asistente. Importar el paquete registra todas las tools."""

from . import read, write  # noqa: F401  (el registro ocurre al importar)
from .base import REGISTRY, Principal, ToolContext, ToolError, ToolSpec

__all__ = ["REGISTRY", "Principal", "ToolContext", "ToolError", "ToolSpec"]
