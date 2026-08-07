"""Evidencia por cliente: en qué bin de WoE cae cada una de sus variables.

QUÉ ES Y QUÉ NO ES ESTO
-----------------------
El WoE mide la asociación **univariada** de cada variable con la adopción:
cuánto se sobre-representa un tramo entre quienes adoptaron frente a quienes
no. Es la evidencia observada en los datos.

NO es la atribución interna del modelo. El modelo de propensión es un
`HistGradientBoostingClassifier`, no una tarjeta de puntaje logística sobre
WoE: captura interacciones y no linealidades que esta descomposición no ve.
La lectura correcta es «qué tiene este cliente que se asocia con adoptar», no
«por esto el modelo dio 0.87». Para atribución fiel al modelo haría falta algo
como SHAP.

CONVENCIÓN DE SIGNO (verificada contra el artefacto)
----------------------------------------------------
    woe = ln(% de no adoptantes en el bin / % de adoptantes en el bin)

Por lo tanto **WoE positivo = evidencia EN CONTRA de adoptar**, que es el
inverso de la convención más difundida. Leerlo al revés invierte todas las
conclusiones, así que la interpretación se traduce a texto explícito en
`clasificar_direccion` y nunca se muestra el número solo.
"""
import re

import pandas as pd

# `(-0.001, 4.0]` o `[0, 1)`: tramos continuos, con corchete o paréntesis.
INTERVALO = re.compile(
    r"^([\(\[])\s*(-?[\d.eE+-]+)\s*,\s*(-?[\d.eE+-]+)\s*([\)\]])$")
# `= 0` o `= 0.0`: igualdad explícita, como la escribe el binning discreto.
IGUALDAD = re.compile(r"^=\s*(.+)$")

SIN_DATO = "Sin dato"


def _coincide_intervalo(valor: float, etiqueta: str) -> bool:
    m = INTERVALO.match(etiqueta)
    if not m:
        return False
    abre, bajo, alto, cierra = m.groups()
    try:
        v, lo, hi = float(valor), float(bajo), float(alto)
    except (TypeError, ValueError):
        return False
    por_abajo = v > lo if abre == "(" else v >= lo
    por_arriba = v <= hi if cierra == "]" else v < hi
    return por_abajo and por_arriba


def _coincide_literal(valor, etiqueta: str) -> bool:
    m = IGUALDAD.match(etiqueta)
    objetivo = m.group(1).strip() if m else etiqueta
    try:
        return float(objetivo) == float(valor)
    except (TypeError, ValueError):
        return str(objetivo).strip() == str(valor).strip()


def ubicar_bin(valor, etiquetas) -> str | None:
    """Bin al que pertenece `valor`, o None si ninguno lo cubre.

    Devolver None es deliberado: significa que el binning se hizo sobre una
    distribución que ya no cubre este valor -- síntoma de deriva. Es preferible
    a forzarlo al tramo más cercano y presentar evidencia inventada.
    """
    etiquetas = list(etiquetas)
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return SIN_DATO if SIN_DATO in etiquetas else None
    for etiqueta in etiquetas:
        if etiqueta == SIN_DATO:
            continue
        if INTERVALO.match(etiqueta):
            if _coincide_intervalo(valor, etiqueta):
                return etiqueta
        elif _coincide_literal(valor, etiqueta):
            return etiqueta
    return None


def clasificar_direccion(woe: float, umbral: float = 0.10) -> str:
    """Traduce el signo del WoE a algo que no se pueda leer al revés."""
    if pd.isna(woe) or abs(woe) < umbral:
        return "neutro"
    return "en contra" if woe > 0 else "a favor"


def evidencia_del_cliente(features: pd.Series, woe: pd.DataFrame) -> pd.DataFrame:
    """Tabla de evidencia univariada ordenada por fuerza.

    `features` es la fila de `cliente_features` del cliente; `woe` es
    `outputs/eda/woe_por_bin.csv`. Se devuelven solo las variables cuyo bin se
    pudo resolver: una variable sin bin identificable no aporta evidencia y
    mostrarla vacía solo añade ruido.
    """
    filas = []
    for variable, tramos in woe.groupby("variable"):
        if variable not in features.index:
            continue
        valor = features[variable]
        etiqueta = ubicar_bin(valor, tramos["bin"].tolist())
        if etiqueta is None:
            continue
        fila = tramos[tramos["bin"] == etiqueta].iloc[0]
        filas.append({
            "variable": variable,
            "valor_cliente": valor,
            "bin": etiqueta,
            "woe": float(fila["woe"]),
            "fuerza": abs(float(fila["woe"])),
            "direccion": clasificar_direccion(float(fila["woe"])),
            "n_en_bin": int(fila["n"]),
        })
    if not filas:
        return pd.DataFrame(columns=["variable", "valor_cliente", "bin", "woe",
                                     "fuerza", "direccion", "n_en_bin"])
    return (pd.DataFrame(filas)
            .sort_values("fuerza", ascending=False)
            .reset_index(drop=True))
