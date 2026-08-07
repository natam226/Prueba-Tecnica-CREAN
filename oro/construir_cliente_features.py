# oro/construir_cliente_features.py
import json

import pandas as pd

import config
from src.db_io import leer_tabla_sqlite, escribir_tabla_sqlite
from src.decisiones import decidir_perfil_incompleto
from src.derivadas import (
    agregar_agregados_producto,
    agregar_banderas_faltantes,
    agregar_ratios_financieros,
    agregar_tendencia_relativa,
    agregar_vivienda_como_categoria,
    resumen_cv_saldo_liquido,
)
from src.fecha_corte import calcular_fecha_corte

PRODUCTOS = config.PRODUCTOS
BLOQUES_PERFIL = ["falta_estimador", "falta_vivienda", "falta_financiero"]

# Leak-fix (ver .superpowers/sdd/2026-08-06-pipeline-crean-v2/leakage-investigation.md):
# fuentes admitidas para `dias_desde_ultimo_dato`/`sin_dato_reciente` (D0) y,
# vía plata/transformacion.py::construir_primer_registro, para
# `antiguedad_relacion_meses` (D8). Invesbot / Inversión Virtual quedan
# excluidos de ambas agregaciones: incluirlos convertía cada variable en una
# función directa de `etiqueta_adopcion` para ~31-32% de los adoptantes.
PRODUCTOS_NO_ETIQUETA = [p for p in PRODUCTOS if p not in config.PRODUCTOS_ETIQUETA]

TABLAS_PRODUCTO = {
    "cuenta_ahorro": "aho_cte_plata",
    "cuenta_corriente": "aho_cte_plata",
    "bolsillos": "bolsillos_plata",
    "fiducuenta": "fiducuenta_plata",
    "cdt": "cdt_inversion_virtual_plata",
    "inversion_virtual": "cdt_inversion_virtual_plata",
    "invesbot": "invesbot_plata",
}


def _pivotear_producto(clientes_ids, producto):
    tabla = TABLAS_PRODUCTO[producto]
    df = leer_tabla_sqlite(config.PLATA_DB, tabla)
    df["fecha_snapshot"] = pd.to_datetime(df["fecha_snapshot"])
    df = df[df["producto"] == producto].drop(columns=["producto"])
    df = df.rename(columns={
        "saldo_snapshot": f"{producto}_saldo_snapshot",
        "saldo_prom_6m": f"{producto}_saldo_prom_6m",
        "tendencia_6m": f"{producto}_tendencia_6m",
        "tenencia": f"{producto}_tenencia",
        "n_obs_ventana": f"{producto}_n_obs_ventana",
        "fecha_snapshot": f"{producto}_fecha_snapshot",   # D0: ya no se descarta
    })
    return df


def agregar_recencia_dato(base: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    """D0, requisito 1: control de calidad de dato por cliente (N1).

    `dias_desde_ultimo_dato` = FECHA_CORTE - máxima fecha_snapshot entre las 5
    fuentes de saldo NO-etiqueta (`PRODUCTOS_NO_ETIQUETA`: excluye Invesbot e
    Inversión Virtual). Confirmed leak fix: incluir esas dos fuentes en el MAX
    hacía que, para ~31% de los adoptantes, "hace cuánto vimos a este
    cliente" fuera en realidad "hace cuánto se registró su snapshot de
    Invesbot/Inversión Virtual" -- una función directa de `etiqueta_adopcion`
    (ver .superpowers/sdd/2026-08-06-pipeline-crean-v2/leakage-investigation.md
    §3). Un cliente sin NINGUNA fila de producto no-etiqueta queda en NULO +
    bandera `sin_dato_reciente`, nunca en 0 ni en un valor grande arbitrario;
    esto incluye, deliberadamente, al cliente cuyo ÚNICO dato está en
    Invesbot/Inversión Virtual -- no hay señal de recencia no-etiqueta para
    él bajo esta definición, con independencia de qué tan reciente sea su
    dato de etiqueta.
    """
    out = base.copy()
    fecha_cols = [f"{p}_fecha_snapshot" for p in PRODUCTOS_NO_ETIQUETA]
    presentes = [c for c in fecha_cols if c in out.columns]
    ultimo_dato = out[presentes].max(axis=1)
    out["dias_desde_ultimo_dato"] = (fecha_corte - ultimo_dato).dt.days.astype("Int64")
    out["sin_dato_reciente"] = ultimo_dato.isna().astype(int)
    return out


def agregar_etiqueta_adopcion_reciente(base: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    """D0, análisis de sensibilidad: etiqueta alternativa que SÍ exige recencia
    (N4: ventana de `config.VENTANA_DIAS_ETIQUETA_RECIENTE` días desde
    FECHA_CORTE). Solo se usa para comparar contra la etiqueta principal en la
    Task 18B - la etiqueta principal (`etiqueta_adopcion`) no cambia."""
    out = base.copy()
    ventana = config.VENTANA_DIAS_ETIQUETA_RECIENTE
    reciente_invesbot = (
        (out["invesbot_saldo_snapshot"] > 0)
        & ((fecha_corte - out["invesbot_fecha_snapshot"]).dt.days <= ventana)
    ).fillna(False)
    reciente_iv = (
        (out["inversion_virtual_saldo_snapshot"] > 0)
        & ((fecha_corte - out["inversion_virtual_fecha_snapshot"]).dt.days <= ventana)
    ).fillna(False)
    out["etiqueta_adopcion_reciente"] = (reciente_invesbot | reciente_iv).astype(int)
    return out


def _lift_medido_desde_eda():
    """Lee el lift condicional (D7) medido por notebooks/03_eda_faltantes.ipynb.
    Si el notebook aún no se ha ejecutado, devuelve None: la bandera no se crea
    y las banderas por bloque siguen siendo la señal disponible."""
    ruta = config.OUTPUTS_DIR / "eda" / "faltantes_solapamiento.json"
    if not ruta.exists():
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f).get("lift_estimador_vivienda")


def agregar_perfil_incompleto(df, lift_medido=None):
    """SPEC_V2 §5: bandera única, SOLO si §6.5.2 confirma causa común (D7: lift
    condicional >= config.UMBRAL_LIFT_PERFIL_INCOMPLETO)."""
    if lift_medido is None:
        lift_medido = _lift_medido_desde_eda()
    if lift_medido is None:
        return df
    if not decidir_perfil_incompleto(lift_medido)["crear_bandera_unica"]:
        return df

    out = df.copy()
    presentes = [c for c in BLOQUES_PERFIL if c in out.columns]
    out["perfil_incompleto"] = (out[presentes].sum(axis=1) > 0).astype(int)
    return out


def construir_cliente_features():
    base = leer_tabla_sqlite(config.PLATA_DB, "clientes_plata")

    for producto in PRODUCTOS:
        df_producto = _pivotear_producto(base["numero_id"], producto)
        base = base.merge(df_producto, on="numero_id", how="left")

        # sin_producto = cliente sin NINGÚN registro para este producto (ausencia real).
        # Debe capturarse ANTES de rellenar tenencia: agregar_serie_saldo siempre pone
        # tenencia=1 cuando el grupo plata existe, aunque su ventana de 6M esté vacía,
        # así que tenencia NaN post-merge es la señal inequívoca de ausencia total.
        sin_producto = base[f"{producto}_tenencia"].isna()

        base[f"{producto}_tenencia"] = base[f"{producto}_tenencia"].fillna(0).astype(int)
        # saldo_snapshot solo es NaN por ausencia real del producto -> fillna(0.0) incondicional
        base[f"{producto}_saldo_snapshot"] = base[f"{producto}_saldo_snapshot"].fillna(0.0)

        # saldo_prom_6m / tendencia_6m: rellenar con 0.0 SOLO para ausencia real del producto.
        # Si el cliente tiene el producto pero su ventana de 6M no tuvo observaciones, el NaN
        # (heredado de agregar_serie_saldo) debe permanecer: "sin dato" != "confirmado cero".
        base.loc[sin_producto, f"{producto}_saldo_prom_6m"] = (
            base.loc[sin_producto, f"{producto}_saldo_prom_6m"].fillna(0.0)
        )
        base.loc[sin_producto, f"{producto}_tendencia_6m"] = (
            base.loc[sin_producto, f"{producto}_tendencia_6m"].fillna(0.0)
        )
        # n_obs_ventana: un conteo de 0 es un hecho, siempre seguro de rellenar
        base[f"{producto}_n_obs_ventana"] = base[f"{producto}_n_obs_ventana"].fillna(0).astype(int)

    estimador = leer_tabla_sqlite(config.PLATA_DB, "estimador_ingresos_plata")
    base = base.merge(estimador, on="numero_id", how="left")
    base["tiene_estimador_ingreso"] = base["tiene_estimador_ingreso"].fillna(False).astype(bool)

    base["etiqueta_adopcion"] = (
        (base["invesbot_saldo_snapshot"] > 0) | (base["inversion_virtual_saldo_snapshot"] > 0)
    ).astype(int)

    fecha_corte = calcular_fecha_corte()
    base = agregar_recencia_dato(base, fecha_corte)
    base = agregar_etiqueta_adopcion_reciente(base, fecha_corte)

    # --- SPEC_V2 §1.1: agregados de inversión que NO tocan la etiqueta ---
    # Solo CDT y Fiducuenta. Nunca Invesbot ni Inversión Virtual: sumarlos
    # reintroduciría la etiqueta dentro de las predictoras.
    cols_saldo_no_etiqueta = [
        f"{p}_saldo_snapshot" for p in config.PRODUCTOS_INVERSION_NO_ETIQUETA
    ]
    base["saldo_invertido_no_etiqueta"] = base[cols_saldo_no_etiqueta].fillna(0.0).sum(axis=1)
    base["n_productos_inversion_no_etiqueta"] = (
        (base[cols_saldo_no_etiqueta].fillna(0.0) > 0).sum(axis=1).astype(int)
    )

    # --- SPEC_V2 §2: población de entrenamiento vs. población de scoring ---
    # Se scorea a TODA la base. La única exclusión admitida es "sin ninguna señal
    # en ninguna fuente": ni producto, ni estimador de ingreso, ni datos financieros.
    tenencia_cols = [f"{p}_tenencia" for p in PRODUCTOS]
    base["tiene_historial_producto"] = (base[tenencia_cols].sum(axis=1) > 0).astype(int)

    base["sin_ninguna_senal"] = (
        (base["tiene_historial_producto"] == 0)
        & (~base["tiene_estimador_ingreso"])
        & base["sin_dato_financiero_total"].fillna(False).astype(bool)
    ).astype(int)

    base["apto_entrenamiento"] = (1 - base["sin_ninguna_senal"]).astype(int)

    # --- SPEC_V2 §5: variables derivadas ---
    base = agregar_ratios_financieros(base)
    base = agregar_agregados_producto(base)
    base = agregar_tendencia_relativa(base)   # D3: {producto}_tendencia_relativa_6m
    base = agregar_vivienda_como_categoria(base)
    base = agregar_banderas_faltantes(base, {
        "financiero": config.COLS_FINANCIERAS,
        "estimador": ["estimador_ingreso"],
    })
    # `falta_vivienda` NO sale de agregar_banderas_faltantes: `agregar_vivienda_como_categoria`
    # ya sustituyó los nulos por "Sin dato", así que la columna no tiene nulos que contar.
    # Es el complemento exacto de la bandera que esa función dejó.
    base["falta_vivienda"] = (1 - base["tiene_dato_vivienda"]).astype(int)

    # D9: coeficiente de variación del saldo líquido, ventana fija de 6M desde
    # FECHA_CORTE (misma `fecha_corte` global ya calculada arriba), mínimo de
    # meses observados (Task 7 ya regulariza todas las fuentes contra ese
    # mismo mes_max).
    panel = leer_tabla_sqlite(config.PLATA_DB, "saldos_mensual_plata")
    panel["mes"] = pd.to_datetime(panel["mes"])
    base = base.merge(
        resumen_cv_saldo_liquido(panel, config.PRODUCTOS_LIQUIDOS, fecha_corte=fecha_corte),
        on="numero_id", how="left",
    )
    base["cv_saldo_liquido_insuficiente"] = (
        base["cv_saldo_liquido_insuficiente"].fillna(1).astype(int))

    # D8 (AMENDADA por el leak-fix de
    # .superpowers/sdd/2026-08-06-pipeline-crean-v2/leakage-investigation.md):
    # antigüedad de la relación = meses entre FECHA_CORTE global y el primer
    # registro del cliente en cualquier fuente NO-etiqueta (contra
    # FECHA_CORTE explícitamente, no contra "el mes máximo del panel"). La
    # redacción original de D8 decía "cualquier fuente" sin más; se comprobó
    # que ese MIN incluía a Invesbot/Inversión Virtual y por tanto era una
    # función directa de la etiqueta para ~32% de los adoptantes. La
    # exclusión ya vive en `primer_registro_plata`
    # (plata/transformacion.py::construir_primer_registro), esta capa solo
    # consume su resultado.
    primer = leer_tabla_sqlite(config.PLATA_DB, "primer_registro_plata")
    primer["primer_mes"] = pd.to_datetime(primer["primer_mes"])
    primer["antiguedad_relacion_meses"] = (
        (fecha_corte.year - primer["primer_mes"].dt.year) * 12
        + (fecha_corte.month - primer["primer_mes"].dt.month)
    ).astype("Int64")
    base = base.merge(
        primer[["numero_id", "antiguedad_relacion_meses"]], on="numero_id", how="left")

    # SPEC_V2 §5/§6.5.2 (D7): bandera única `perfil_incompleto`, solo si el
    # lift condicional medido por notebooks/03_eda_faltantes.ipynb supera el
    # umbral. No-op (columna ausente) si el notebook no se ha corrido o si el
    # lift medido no confirma causa común -- las banderas por bloque siguen
    # siendo la señal disponible en ese caso.
    base = agregar_perfil_incompleto(base)

    escribir_tabla_sqlite(base, config.ORO_DB, "cliente_features")
    return base


if __name__ == "__main__":
    df = construir_cliente_features()
    print(f"cliente_features: {len(df)} filas, {df.shape[1]} columnas")
    print(f"tasa adopción: {df['etiqueta_adopcion'].mean():.4f}")
    print(f"con historial de producto: {df['tiene_historial_producto'].sum()}")
    print(f"sin ninguna señal (única exclusión): {df['sin_ninguna_senal'].sum()}")
    print(f"aptos para entrenamiento: {df['apto_entrenamiento'].sum()}")
