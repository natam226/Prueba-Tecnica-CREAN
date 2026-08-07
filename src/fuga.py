"""Guardia contra fuga de información en el conjunto de entrenamiento.

SPEC_V2 §1: la etiqueta `adopcion` se define como saldo activo en Invesbot y/o
Inversión Virtual, así que ninguna variable derivada de esos dos productos puede
ser predictora. Este módulo es la implementación del "test automático que falle
si alguna variable con prefijo invesbot_ o inv_virtual_ entra al conjunto de
entrenamiento" (§1, acción 3).
"""
from typing import Iterable

# `inversion_virtual_` es la grafía que realmente generan plata/oro;
# `inv_virtual_` es la que usa SPEC_V2. Se cubren las dos.
PREFIJOS_FUGA = ("invesbot_", "inv_virtual_", "inversion_virtual_")

# Variables sin prefijo delator que igualmente contienen la etiqueta porque
# agregan los productos que la definen (SPEC_V2 §1).
COLUMNAS_FUGA_EXPLICITAS = frozenset({
    "etiqueta_adopcion",
    "tiene_invesbot",
    "tiene_inv_virtual",
    "tiene_inversion_virtual",
    "n_productos_inversion",
    "saldo_total_invertido",
    "pct_patrimonio_invertido",
    "n_productos_total",          # cuenta TODOS los productos, incluidos los de la etiqueta
    "tiene_historial_inversion",  # §6.3: incluye historial en Invesbot/IV
    "monto_estimado_12m",         # salida del modelo de monto, no entrada
})


class FugaDeInformacionError(AssertionError):
    """Se lanza cuando una variable prohibida entra al conjunto de entrenamiento."""


def columnas_con_fuga(columnas: Iterable[str]) -> list[str]:
    """Devuelve, ordenadas, las columnas que no pueden ser predictoras."""
    return sorted(
        c for c in columnas
        if c.startswith(PREFIJOS_FUGA) or c in COLUMNAS_FUGA_EXPLICITAS
    )


def validar_sin_fuga(columnas: Iterable[str], contexto: str = "entrenamiento") -> bool:
    """Lanza FugaDeInformacionError si alguna columna prohibida está presente."""
    encontradas = columnas_con_fuga(columnas)
    if encontradas:
        raise FugaDeInformacionError(
            f"Fuga de información en {contexto}: {encontradas}. "
            f"SPEC_V2 §1 prohíbe toda variable derivada de Invesbot o Inversión Virtual."
        )
    return True
