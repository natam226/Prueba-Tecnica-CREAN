"""Selección de predictoras para los dos modelos de propensión (SPEC_V2 §6.1).

Modelo A (completo): capacidad financiera + comportamiento en productos que NO
definen la etiqueta + variables derivadas.
Modelo B (cold-start): SOLO capacidad financiera y derivadas de ella.

Toda salida pasa por `validar_sin_fuga` antes de devolverse: la selección y el
guard viven juntos para que sea imposible entrenar saltándose la comprobación.
"""
from typing import Iterable

import config
from src.fuga import COLUMNAS_FUGA_EXPLICITAS, PREFIJOS_FUGA, validar_sin_fuga

# Identificadores, etiquetas y banderas de población: nunca son predictoras.
# NOTA: las columnas de fuga (invesbot/inv_virtual y sus agregados explícitos,
# p.ej. n_productos_total, etiqueta_adopcion_reciente) NO se listan aquí. Se
# excluyen más abajo referenciando directamente `fuga.COLUMNAS_FUGA_EXPLICITAS`
# y `fuga.PREFIJOS_FUGA` -- ver el comentario sobre esa decisión junto al filtro.
COLUMNAS_NO_FEATURE = frozenset({
    "numero_id",
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
    # Nombres REALES de las columnas de fact_cliente_score (Task 18). El plan
    # las había anticipado como `score_propension` / `nivel_prioridad`, pero la
    # tabla se escribió con `score` / `nivel`, así que los nombres de arriba no
    # las atrapaban. Cualquier notebook que haga merge de fact_cliente_score
    # sobre cliente_features (p.ej. 07_auditoria_sesgo) las arrastraría al set
    # de predictoras: `nivel`/`poblacion` rompen el fit por ser strings, y
    # `score` -- que es la SALIDA del modelo de propensión -- se colaría en
    # silencio como entrada, inflando cualquier AUC medido sobre ella.
    "score",
    "nivel",
    "poblacion",
    "valor_referencia",
    "tipo_valor_referencia",
    "valor_esperado_12m",
    "capacidad_ahorro_anualizada",
})

# SPEC_V2 §6.4: de las tres demográficas, SOLO género queda fuera del modelo.
# grupo_edad y desc_tipo_de_vivienda entran (esta última sujeta a §6.5).
COLUMNAS_SENSIBLES_EXCLUIDAS = ("desc_genero",)

# Prefijos que el Modelo A no puede usar: los de fuga.
PREFIJOS_EXCLUIDOS_A = PREFIJOS_FUGA

# Sufijos que el Modelo A no puede usar: artefactos intermedios, no predictoras.
# `{producto}_fecha_snapshot` es un datetime-string que Task 2B dejó de eliminar
# en `_pivotear_producto` porque `agregar_recencia_dato` lo necesita para derivar
# `dias_desde_ultimo_dato` (la forma numérica, esa sí predictora, ya está en
# COLUMNAS_MODELO_B/A). Regla por sufijo -- no por lista de nombres -- para que
# un producto nuevo no reintroduzca el bug en silencio.
SUFIJOS_EXCLUIDOS_A = ("_fecha_snapshot",)

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
    """Predictoras del Modelo A: todo menos ids, etiquetas, fuga y género.

    La exclusión de fuga se hace referenciando `fuga.COLUMNAS_FUGA_EXPLICITAS`
    y `fuga.PREFIJOS_FUGA` directamente en vez de mantener una copia propia:
    tres bugs seguidos (etiqueta_adopcion_reciente, n_productos_total) fueron
    causados por una tarea posterior agregando una columna real que ya estaba
    en la lista de fuga.py pero que esta lista nunca se enteró de duplicar.
    Referenciar el mismo objeto elimina esa clase de bug de raíz: una sola
    fuente de verdad para "qué es fuga". `validar_sin_fuga` sigue corriendo
    después como backstop -- no depende de que este filtro esté completo, así
    que sigue pudiendo fallar si algo más (un descuido en COLUMNAS_NO_FEATURE,
    COLUMNAS_SENSIBLES_EXCLUIDAS o SUFIJOS_EXCLUIDOS_A) deja pasar una columna
    de fuga por otra vía.
    """
    feats = [
        c for c in columnas
        if c not in COLUMNAS_NO_FEATURE
        and c not in COLUMNAS_SENSIBLES_EXCLUIDAS
        and c not in COLUMNAS_FUGA_EXPLICITAS
        and not c.startswith(PREFIJOS_EXCLUIDOS_A)
        and not c.endswith(SUFIJOS_EXCLUIDOS_A)
    ]
    validar_sin_fuga(feats, contexto="Modelo A")
    return feats


def features_modelo_b(columnas: Iterable[str]) -> list[str]:
    """Predictoras del Modelo B: lista blanca de capacidad financiera."""
    presentes = set(columnas)
    feats = [c for c in COLUMNAS_MODELO_B if c in presentes]
    validar_sin_fuga(feats, contexto="Modelo B")
    return feats
