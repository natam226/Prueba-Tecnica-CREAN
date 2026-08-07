"""Tablas de decisión de SPEC_V2, implementadas como código testeable.

La acción NO se elige de antemano: se deriva del estadístico medido (AUC del
clasificador auxiliar en §3.2, IV en §6.5). Tener la tabla en código y no en el
notebook evita que la decisión se "razone" a posteriori para justificar lo que
ya se hizo.

Bordes: SPEC_V2 §3.2 define las bandas como "< 0.60", "0.60 – 0.70" y "> 0.70".
Los valores exactos 0.60 y 0.70 caen por tanto en la banda intermedia.
"""
import config


def decidir_tratamiento_faltante_estimador(auc: float,
                                           modelo_maneja_nulos: bool = True) -> dict:
    """SPEC_V2 §3.2 — tabla de decisión sobre `falta_estimador`."""
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"AUC fuera de rango: {auc}")

    if auc < config.UMBRAL_AUC_PATRON_DEBIL:
        conclusion = "ausencia aproximadamente aleatoria"
        documentar = False
        bandera_predictora = False
    elif auc <= config.UMBRAL_AUC_PATRON_INFORMATIVO:
        conclusion = "patrón débil"
        documentar = True
        bandera_predictora = False
    else:
        conclusion = "ausencia informativa"
        documentar = True
        bandera_predictora = True

    if bandera_predictora:
        # §3.2, fila >0.70: NO imputar con medida central global. La bandera pasa
        # a ser predictora de pleno derecho; el valor queda nulo (o se imputa por
        # mediana condicional al grupo, decisión que toma el notebook con el grupo
        # identificado por las variables más importantes).
        accion = "bandera_predictora_sin_imputacion_global"
        imputar = False
    elif modelo_maneja_nulos:
        accion = "conservar_bandera_sin_imputar"
        imputar = False
    else:
        accion = "conservar_bandera_e_imputar_mediana_segmento"
        imputar = True

    return {
        "auc": float(auc),
        "conclusion": conclusion,
        "accion": accion,
        "imputar": imputar,
        "bandera_como_predictora": bandera_predictora,
        "documentar_variables_asociadas": documentar,
    }


def decidir_tratamiento_vivienda(iv_categorica: float, iv_bandera: float,
                                 umbral: float | None = None) -> dict:
    """SPEC_V2 §6.5 — regla de decisión de `desc_tipo_de_vivienda`."""
    umbral = config.UMBRAL_IV_MINIMO if umbral is None else umbral

    if iv_categorica >= umbral:
        accion, cat, band = "conservar_categorica_con_sin_dato", True, False
    elif iv_bandera >= umbral:
        accion, cat, band = "descartar_categorica_conservar_bandera", False, True
    else:
        accion, cat, band = "descartar_por_completo", False, False

    return {
        "accion": accion,
        "conservar_categorica": cat,
        "conservar_bandera": band,
        "iv_categorica": float(iv_categorica),
        "iv_bandera": float(iv_bandera),
        "umbral": float(umbral),
    }


def lift_condicional(sin_a, sin_b, universo) -> float:
    """D7 — reemplaza al índice de Jaccard, inaplicable aquí.

    Con conjuntos tan desbalanceados como "sin estimador_ingreso" (~114.431) y
    "sin desc_tipo_de_vivienda" (~585.000, 68% de la base), el Jaccard máximo
    alcanzable por construcción es ~0.196 (contención perfecta del menor en el
    mayor); un umbral de 0.50 nunca se activaría. El lift condicional no
    depende de los tamaños relativos:

        lift = P(sin_b | sin_a) / P(sin_b | con_a)

    lift > 1 -> faltar el bloque A predice faltar el bloque B (causa común de
    incompletitud). lift ~= 1 -> las ausencias son independientes.
    """
    a, b, u = set(sin_a), set(sin_b), set(universo)
    con_a = u - a
    if not a or not con_a:
        return float("nan")   # no se puede condicionar sobre un grupo vacío

    p_sin_a = len(a & b) / len(a)
    p_con_a = len(con_a & b) / len(con_a)
    if p_con_a == 0:
        return 0.0 if p_sin_a == 0 else float("inf")
    return p_sin_a / p_con_a


def decidir_perfil_incompleto(lift: float, umbral: float | None = None) -> dict:
    """SPEC_V2 §5 y §6.5.2 — una sola bandera `perfil_incompleto` en vez de
    banderas separadas, si los bloques de datos faltantes tienen causa común
    (D7: medida con lift condicional, umbral 1.5)."""
    umbral = config.UMBRAL_LIFT_PERFIL_INCOMPLETO if umbral is None else umbral
    return {
        "crear_bandera_unica": bool(lift >= umbral),
        "lift": float(lift),
        "umbral": float(umbral),
    }


def decidir_interpretacion_proxy_genero(auc: float) -> dict:
    """SPEC_V2 §6.6.1 — bandas de interpretación del AUC del clasificador de
    proxy de género (D6, reemplaza al umbral único de la propuesta provisional:
    un umbral binario oculta el caso intermedio, que es el resultado más
    probable y el que más requiere documentación explícita)."""
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"AUC fuera de rango: {auc}")

    if auc < config.UMBRAL_AUC_PROXY_MODERADO:
        interpretacion, accion = "proxy mínimo", "documentar_y_continuar"
    elif auc <= config.UMBRAL_AUC_PROXY_SUSTANCIAL:
        interpretacion, accion = "proxy moderado", "documentar_variables_asociadas"
    else:
        interpretacion, accion = "proxy sustancial", "investigar_mitigacion"

    return {"auc": float(auc), "interpretacion": interpretacion, "accion": accion}
