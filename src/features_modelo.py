"""Selección de predictoras para los dos modelos de propensión (SPEC_V2 §6.1).

Modelo A (completo): capacidad financiera + comportamiento en productos que NO
definen la etiqueta + variables derivadas.
Modelo B (cold-start): SOLO capacidad financiera y derivadas de ella.

Toda salida pasa por `validar_sin_fuga` antes de devolverse: la selección y el
guard viven juntos para que sea imposible entrenar saltándose la comprobación.
"""
from typing import Iterable

import config
from src.fuga import PREFIJOS_FUGA, validar_sin_fuga

# Identificadores, etiquetas y banderas de población: nunca son predictoras.
COLUMNAS_NO_FEATURE = frozenset({
    "numero_id",
    "etiqueta_adopcion",
    "etiqueta_adopcion_reciente",  # D0.2/N4: etiqueta alternativa de sensibilidad, no predictora
    "apto_entrenamiento",
    "tiene_historial_producto",
    "sin_ninguna_senal",
    "score_propension",
    "nivel_prioridad",
    "modelo_usado",
    "monto_estimado_12m",
    "monto_conservador_12m",
    "monto_base_12m",
    "monto_optimista_12m",
})

# SPEC_V2 §6.4: de las tres demográficas, SOLO género queda fuera del modelo.
# grupo_edad y desc_tipo_de_vivienda entran (esta última sujeta a §6.5).
COLUMNAS_SENSIBLES_EXCLUIDAS = ("desc_genero",)

# Prefijos que el Modelo A no puede usar: los de fuga.
PREFIJOS_EXCLUIDOS_A = PREFIJOS_FUGA

# Modelo B: lista blanca. Nada de producto, ni siquiera indirectamente.
# Son las columnas financieras + sus derivadas de §5 que no tocan saldos de producto.
COLUMNAS_MODELO_B = tuple(config.COLS_FINANCIERAS) + (
    "capacidad_ahorro",
    "estimador_ingreso",
    "tiene_estimador_ingreso",
    "falta_estimador",
    "ratio_egreso_ingreso",
    "pct_ahorro_ingreso",
    "ratio_pasivo_activo",
    "patrimonio_por_ingreso",
    "dif_ingreso_declarado_estimado",   # D10 (antes gap_ingreso_estimado_declarado)
    "pct_dif_ingreso",                  # D10 (antes pct_gap_ingreso)
    "sin_dato_financiero",
    "grupo_edad",
    "desc_tipo_de_vivienda",
    "tiene_dato_vivienda",
    "perfil_incompleto",
    "desc_segmento",
)


def features_modelo_a(columnas: Iterable[str]) -> list[str]:
    """Predictoras del Modelo A: todo menos ids, etiquetas, fuga y género."""
    feats = [
        c for c in columnas
        if c not in COLUMNAS_NO_FEATURE
        and c not in COLUMNAS_SENSIBLES_EXCLUIDAS
        and not c.startswith(PREFIJOS_EXCLUIDOS_A)
    ]
    validar_sin_fuga(feats, contexto="Modelo A")
    return feats


def features_modelo_b(columnas: Iterable[str]) -> list[str]:
    """Predictoras del Modelo B: lista blanca de capacidad financiera."""
    presentes = set(columnas)
    feats = [c for c in COLUMNAS_MODELO_B if c in presentes]
    validar_sin_fuga(feats, contexto="Modelo B")
    return feats
