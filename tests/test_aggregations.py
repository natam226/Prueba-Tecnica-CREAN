import pandas as pd

from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual


def test_agregar_serie_saldo_snapshot_es_el_mas_reciente():
    df = pd.DataFrame({
        "numero_id": [1, 1, 1],
        "fecha": ["2026-01-01", "2026-03-01", "2026-06-01"],
        "saldo": [100.0, 200.0, 300.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"))
    fila = resultado.iloc[0]
    assert fila["saldo_snapshot"] == 300.0
    assert str(fila["fecha_snapshot"]) == "2026-06-01 00:00:00"
    assert fila["n_obs_ventana"] == 3  # las 3 filas caen dentro de la ventana de 6M


def test_agregar_serie_saldo_promedio_y_tendencia():
    # ventana de 6M hacia atrás desde 2026-06-01 => desde 2025-12-01
    df = pd.DataFrame({
        "numero_id": [1, 1, 1, 1],
        "fecha": ["2025-12-01", "2026-01-15", "2026-04-01", "2026-06-01"],
        "saldo": [100.0, 100.0, 300.0, 300.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"))
    fila = resultado.iloc[0]
    assert fila["saldo_prom_6m"] == 200.0  # promedio de las 4 filas
    assert fila["tendencia_6m"] == 200.0  # promedio 2a mitad (300) - promedio 1a mitad (100)
    assert fila["tenencia"] == 1
    assert fila["n_obs_ventana"] == 4  # las 4 filas caen dentro de la ventana


def test_agregar_serie_saldo_sin_datos_en_ventana():
    # Edge case: grupo con snapshot antiguo, nada en la ventana de 6M.
    # fecha_corte global = 2026-06-01, ventana = [2025-12-01, 2026-06-01].
    # grupo 1: datos en ventana (normal). grupo 2: solo datos antiguos (2020).
    # Esperado: grupo 2 tiene saldo_prom_6m y tendencia_6m ambos NaN reales (no medibles,
    # no confundir con "confirmado cero"), y n_obs_ventana == 0 (hecho, no suposición)
    df = pd.DataFrame({
        "numero_id": [1, 1, 2],
        "fecha": ["2026-01-01", "2026-06-01", "2020-01-01"],
        "saldo": [100.0, 300.0, 9999.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"), meses_ventana=6)
    # Grupo 2: snapshot preserved, but no data in window
    fila_grupo2 = resultado[resultado["numero_id"] == 2].iloc[0]
    assert fila_grupo2["saldo_snapshot"] == 9999.0
    assert pd.isna(fila_grupo2["saldo_prom_6m"])  # sin datos en ventana -> NaN real, no 0
    assert pd.isna(fila_grupo2["tendencia_6m"])   # sin datos en ventana -> NaN real, no 0
    assert fila_grupo2["tenencia"] == 1
    assert fila_grupo2["n_obs_ventana"] == 0  # ningún registro cae en la ventana


def test_agregar_serie_saldo_usa_fecha_corte_explicita_no_el_maximo_del_grupo():
    """D4: fecha_corte es un parámetro externo (global), NO se recalcula por
    grupo. Un cliente cuyo último dato es posterior al corte queda igual
    medido contra el corte, no contra su propio máximo."""
    df = pd.DataFrame({
        "numero_id": [1, 1, 1],
        "fecha": ["2026-01-01", "2026-03-01", "2026-08-01"],  # ago > corte
        "saldo": [100.0, 200.0, 999.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"))
    fila = resultado.iloc[0]
    assert fila["saldo_snapshot"] == 200.0          # último dato <= corte
    assert str(fila["fecha_snapshot"]) == "2026-03-01 00:00:00"


def test_agregar_serie_saldo_no_regresiona_nan_vs_cero_con_fecha_corte():
    """Guarda contra una regresión de esta MISMA tarea: al añadir fecha_corte,
    el caso 'sin datos en la ventana' debe seguir devolviendo NaN real, no 0.0
    (comportamiento ya corregido en el código actual, commit 9277016)."""
    df = pd.DataFrame({
        "numero_id": [1, 1, 2],
        "fecha": ["2026-01-01", "2026-06-01", "2020-01-01"],
        "saldo": [100.0, 300.0, 9999.0],
    })
    resultado = agregar_serie_saldo(
        df, group_cols=["numero_id"], fecha_corte=pd.Timestamp("2026-06-01"), meses_ventana=6)
    fila_grupo2 = resultado[resultado["numero_id"] == 2].iloc[0]
    assert fila_grupo2["saldo_snapshot"] == 9999.0
    assert pd.isna(fila_grupo2["saldo_prom_6m"])
    assert pd.isna(fila_grupo2["tendencia_6m"])
    assert fila_grupo2["n_obs_ventana"] == 0


def test_normalizar_producto_inv_virtual_corrige_casing_inconsistente():
    # Valor real en crean_inv_virtual_cdt.db: UTF-8 válido, pero con 'ó' minúscula
    # (U+00F3) en medio de un valor por lo demás en mayúsculas — no es corrupción
    # de bytes. El prefijo "INVERSI" (ASCII, siempre presente) es indiferente a esto.
    assert normalizar_producto_inv_virtual("INVERSIóN VIRTUAL") == "INVERSION_VIRTUAL"
    assert normalizar_producto_inv_virtual("CDT") == "CDT"
