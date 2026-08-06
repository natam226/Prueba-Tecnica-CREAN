import pandas as pd

from src.aggregations import agregar_serie_saldo, normalizar_producto_inv_virtual


def test_agregar_serie_saldo_snapshot_es_el_mas_reciente():
    df = pd.DataFrame({
        "numero_id": [1, 1, 1],
        "fecha": ["2026-01-01", "2026-03-01", "2026-06-01"],
        "saldo": [100.0, 200.0, 300.0],
    })
    resultado = agregar_serie_saldo(df, group_cols=["numero_id"])
    fila = resultado.iloc[0]
    assert fila["saldo_snapshot"] == 300.0
    assert str(fila["fecha_snapshot"]) == "2026-06-01 00:00:00"


def test_agregar_serie_saldo_promedio_y_tendencia():
    # ventana de 6M hacia atrás desde 2026-06-01 => desde 2025-12-01
    df = pd.DataFrame({
        "numero_id": [1, 1, 1, 1],
        "fecha": ["2025-12-01", "2026-01-15", "2026-04-01", "2026-06-01"],
        "saldo": [100.0, 100.0, 300.0, 300.0],
    })
    resultado = agregar_serie_saldo(df, group_cols=["numero_id"])
    fila = resultado.iloc[0]
    assert fila["saldo_prom_6m"] == 200.0  # promedio de las 4 filas
    assert fila["tendencia_6m"] == 200.0  # promedio 2a mitad (300) - promedio 1a mitad (100)
    assert fila["tenencia"] == 1


def test_normalizar_producto_inv_virtual_corrige_casing_inconsistente():
    # Valor real en crean_inv_virtual_cdt.db: UTF-8 válido, pero con 'ó' minúscula
    # (U+00F3) en medio de un valor por lo demás en mayúsculas — no es corrupción
    # de bytes. El prefijo "INVERSI" (ASCII, siempre presente) es indiferente a esto.
    assert normalizar_producto_inv_virtual("INVERSIóN VIRTUAL") == "INVERSION_VIRTUAL"
    assert normalizar_producto_inv_virtual("CDT") == "CDT"
