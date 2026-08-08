"""Genera el diccionario de datos de la capa oro.

    python scripts/diccionario_datos.py

Escribe `docs/diccionario_datos.md` con las 90 columnas de `cliente_features`
y el esquema estrella: qué es cada una, de dónde sale, cuántos nulos tiene y
qué papel juega en los modelos.

SE GENERA, NO SE ESCRIBE A MANO. Un diccionario escrito a mano se desincroniza
en la primera variable que alguien añada, y entonces miente — que es peor que
no existir. Aquí los nombres, tipos y conteos de nulos salen de la tabla real;
lo único escrito a mano son las descripciones, y las columnas sin descripción
se listan aparte para que se note el hueco.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from oro import esquema
from src.features_modelo import (
    COLUMNAS_MODELO_B, COLUMNAS_NO_FEATURE, COLUMNAS_SENSIBLES_EXCLUIDAS,
)
from src.fuga import COLUMNAS_FUGA_EXPLICITAS, PREFIJOS_FUGA

SALIDA = Path(__file__).resolve().parents[1] / "docs" / "diccionario_datos.md"

# Descripciones de las variables construidas. Las de producto se resuelven por
# patrón más abajo, porque son siete productos por cinco métricas.
DESCRIPCIONES = {
    "numero_id": "Identificador del cliente. Entero de hasta 19 dígitos: excede el entero exacto de coma flotante, así que fuera de SQLite viaja como texto.",
    "etiqueta_adopcion": "1 si el cliente tiene saldo activo en Invesbot o Inversión Virtual. Es la variable objetivo.",
    "etiqueta_adopcion_reciente": "Etiqueta alternativa que además exige actividad en los últimos 90 días. Solo se usa en el análisis de sensibilidad.",
    "apto_entrenamiento": "1 si el cliente tiene alguna señal en alguna fuente. Excluye a quien no aparece en ninguna.",
    "tiene_historial_producto": "1 si el cliente tiene al menos un producto. Define qué modelo se le aplica.",
    "sin_ninguna_senal": "1 si el cliente no aparece en ninguna fuente de producto ni financiera.",
    # --- capacidad financiera ---
    "ingresos_mensuales": "Ingreso mensual declarado. Viene de la fuente de clientes.",
    "total_egresos_mensuales": "Egreso mensual declarado.",
    "total_activos": "Activos declarados.",
    "total_pasivos": "Pasivos declarados.",
    "total_patrimonio": "Patrimonio declarado.",
    "estimador_ingreso": "Ingreso estimado a partir de patrones transaccionales. Su ausencia es informativa: señala una relación transaccional delgada con el banco.",
    "capacidad_ahorro": "ingresos_mensuales − total_egresos_mensuales. Excedente mensual disponible para invertir.",
    "ratio_egreso_ingreso": "egresos / ingresos. Presión de gasto, normalizada por nivel de ingreso.",
    "pct_ahorro_ingreso": "capacidad_ahorro / ingresos. Tasa de ahorro, comparable entre escalas.",
    "ratio_pasivo_activo": "pasivos / activos. Apalancamiento.",
    "patrimonio_por_ingreso": "patrimonio / ingresos. Riqueza acumulada relativa al flujo.",
    "dif_ingreso_declarado_estimado": "Diferencia entre el ingreso declarado y el estimado.",
    "pct_dif_ingreso": "Esa diferencia normalizada por el ingreso declarado.",
    # --- liquidez y volatilidad ---
    "saldo_liquido_total": "Suma de ahorro, corriente y bolsillos.",
    "ratio_liquidez_patrimonio": "saldo_liquido_total / patrimonio.",
    "cv_saldo_liquido": "Coeficiente de variación del saldo líquido en la ventana de 6 meses. Se usa el coeficiente y no la desviación para que sea comparable entre escalas.",
    "cv_saldo_liquido_insuficiente": "1 si hay menos de 3 meses realmente observados para calcular el coeficiente. Un saldo arrastrado por relleno tiene volatilidad artificial cero.",
    # --- relación con el banco ---
    "n_productos_total": "Número de productos del cliente, incluidos los que definen la etiqueta. NO es predictora.",
    "n_productos_no_etiqueta": "Número de productos excluyendo Invesbot e Inversión Virtual.",
    "n_productos_inversion_no_etiqueta": "Número de productos de inversión que no definen la etiqueta: CDT y Fiducuenta.",
    "saldo_invertido_no_etiqueta": "Saldo en CDT y Fiducuenta.",
    "antiguedad_relacion_meses": "Meses entre la fecha de corte y el primer registro del cliente en alguna fuente que NO define la etiqueta.",
    "dias_desde_ultimo_dato": "Días desde el último registro en alguna fuente que NO define la etiqueta.",
    "sin_dato_reciente": "1 si no hay ningún registro reciente en fuentes que no definen la etiqueta.",
    # --- banderas de dato faltante ---
    "falta_estimador": "1 si el cliente no tiene estimador de ingresos. Es el predictor negativo más fuerte de la base.",
    "tiene_estimador_ingreso": "Complemento de falta_estimador.",
    "sin_dato_financiero": "1 si faltan las cinco columnas financieras.",
    "sin_dato_financiero_total": "Variante que exige que falten todas.",
    "falta_financiero": "1 si falta alguna de las columnas financieras.",
    "falta_vivienda": "1 si no hay dato de tipo de vivienda. Afecta al 69% de la base.",
    "tiene_dato_vivienda": "Complemento de falta_vivienda.",
    "perfil_incompleto": "Bandera única de perfil incompleto. Solo se crea si los bloques de datos faltantes se solapan lo suficiente.",
    # --- demográficas ---
    "grupo_edad": "Rango etario. Entra al modelo.",
    "desc_genero": "Género. Se conserva SOLO para auditoría de sesgo; nunca entra al modelo.",
    "desc_segmento": "Segmento comercial. Es la variable con más poder predictivo de la base.",
    "desc_tipo_de_vivienda": "Tipo de vivienda. Mide, en parte, profundidad de la relación con el banco.",
}

# {producto}_{metrica}: siete productos por cinco métricas.
METRICAS = {
    "saldo_snapshot": "Último saldo observado en {p}.",
    "saldo_prom_6m": "Saldo promedio de {p} en la ventana de 6 meses.",
    "tendencia_6m": "Pendiente del saldo de {p} en 6 meses (crecimiento absoluto).",
    "tendencia_relativa_6m": "Tendencia de {p} dividida por su saldo promedio, para que sea comparable entre clientes de distinta escala.",
    "n_obs_ventana": "Meses con dato observado de {p} dentro de la ventana.",
    "tenencia": "1 si el cliente tiene {p}.",
    "fecha_snapshot": "Fecha del último registro de {p}. Artefacto intermedio, no predictora.",
}
PRODUCTOS_LEGIBLES = {
    "cuenta_ahorro": "cuenta de ahorro", "cuenta_corriente": "cuenta corriente",
    "bolsillos": "bolsillos", "fiducuenta": "Fiducuenta", "cdt": "CDT",
    "inversion_virtual": "Inversión Virtual", "invesbot": "Invesbot",
}


def describir(col: str) -> str:
    if col in DESCRIPCIONES:
        return DESCRIPCIONES[col]
    for producto, legible in PRODUCTOS_LEGIBLES.items():
        if col.startswith(producto + "_"):
            metrica = col[len(producto) + 1:]
            if metrica in METRICAS:
                return METRICAS[metrica].format(p=legible)
    return ""


def papel(col: str) -> str:
    """Qué hace esta columna en los modelos."""
    if col in COLUMNAS_FUGA_EXPLICITAS or col.startswith(PREFIJOS_FUGA):
        return "FUGA · nunca predictora"
    if col in COLUMNAS_SENSIBLES_EXCLUIDAS:
        return "excluida por idoneidad"
    if col in COLUMNAS_NO_FEATURE:
        return "identificador o bandera"
    if col in COLUMNAS_MODELO_B:
        return "predictora · modelos A y B"
    if col.endswith("_fecha_snapshot"):
        return "artefacto intermedio"
    return "predictora · modelo A"


def main():
    con = sqlite3.connect(config.ORO_DB)
    try:
        cf = pd.read_sql("SELECT * FROM cliente_features", con)
        tablas = {t: pd.read_sql(f'SELECT * FROM "{t}" LIMIT 1', con)
                  for t in ["dim_cliente", "dim_producto", "dim_tiempo",
                            "fact_saldos_mensual", "fact_cliente_score"]}
        conteos = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                   for t in tablas}
    finally:
        con.close()

    try:
        validacion = pd.read_csv(
            config.OUTPUTS_DIR / "eda" / "validacion_variables.csv"
        ).set_index("variable")
    except FileNotFoundError:
        validacion = pd.DataFrame()

    filas = []
    for col in cf.columns:
        nulos = int(cf[col].isna().sum())
        fila = {
            "columna": col,
            "tipo": str(cf[col].dtype),
            "nulos": f"{nulos:,} ({nulos / len(cf):.1%})" if nulos else "0",
            "papel": papel(col),
            "iv": "",
            "decision": "",
            "descripcion": describir(col),
        }
        if col in validacion.index:
            fila["iv"] = f"{validacion.loc[col, 'iv']:.3f}"
            fila["decision"] = str(validacion.loc[col, "decision_inclusion"])
        filas.append(fila)
    dicc = pd.DataFrame(filas)

    sin_descripcion = dicc[dicc["descripcion"] == ""]["columna"].tolist()

    lineas = [
        "# Diccionario de datos — capa oro",
        "",
        "**Generado por `scripts/diccionario_datos.py` desde la base real.** No",
        "editar a mano: se regenera y se pierde. Para cambiar una descripción,",
        "editar el diccionario `DESCRIPCIONES` de ese script.",
        "",
        f"`cliente_features`: **{len(cf):,} filas × {len(cf.columns)} columnas**, "
        "una fila por cliente.",
        "",
        "## Esquema estrella",
        "",
        "| Tabla | Filas | Llave primaria | Restricciones |",
        "|---|---|---|---|",
    ]
    for t, datos in tablas.items():
        r = esquema.RESTRICCIONES.get(t, {})
        pk = r.get("pk", "—")
        pk = ", ".join(pk) if isinstance(pk, (list, tuple)) else pk
        extras = []
        if r.get("fks"):
            extras.append(f"{len(r['fks'])} llaves foráneas")
        if esquema.INDICES.get(t):
            n = len(esquema.INDICES[t]); extras.append(f"{n} índice" + ("s" if n > 1 else ""))
        if r.get("unicas"):
            extras.append("UNIQUE")
        lineas.append(f"| `{t}` | {conteos[t]:,} | `{pk}` | "
                      f"{', '.join(extras) if extras else '—'} |")

    lineas += [
        "",
        "Las restricciones se declaran en `oro/esquema.py` y las aplica",
        "`escribir_tabla_sqlite`. Las foráneas se verifican con",
        "`PRAGMA foreign_keys = ON` al escribir el estrella.",
        "",
        "## Columnas de `cliente_features`",
        "",
        "La columna **papel** dice qué hace cada variable en los modelos. "
        "«FUGA» marca las que derivan de los productos que definen la etiqueta: "
        "un guard automático falla si alguna llega al entrenamiento.",
        "",
        "| Columna | Tipo | Nulos | Papel | IV | Decisión | Descripción |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in dicc.itertuples(index=False):
        lineas.append(
            f"| `{f.columna}` | {f.tipo} | {f.nulos} | {f.papel} | {f.iv} | "
            f"{f.decision} | {f.descripcion} |")

    if sin_descripcion:
        lineas += [
            "",
            "## Columnas sin descripción",
            "",
            "Se listan a propósito: un diccionario que finge estar completo es "
            "peor que uno que declara sus huecos.",
            "",
            *(f"- `{c}`" for c in sin_descripcion),
        ]

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{SALIDA}")
    print(f"  {len(dicc)} columnas documentadas")
    print(f"  {len(sin_descripcion)} sin descripción: {sin_descripcion or 'ninguna'}")


if __name__ == "__main__":
    main()
