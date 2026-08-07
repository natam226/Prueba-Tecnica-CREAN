import pandas as pd

from src.panel_mensual import construir_panel_mensual, primer_mes_por_grupo


def test_forward_fill_no_interpola_linealmente():
    """SPEC_V2 §6.3.1: un saldo persiste hasta el siguiente movimiento.
    Entre enero (100) y abril (400) los meses intermedios valen 100, NO 200/300."""
    df = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-04-10"],
        "saldo": [100.0, 400.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    saldos = panel.sort_values("mes")["saldo_mes"].tolist()
    assert saldos == [100.0, 100.0, 100.0, 400.0]


def test_dentro_de_un_mes_gana_la_ultima_observacion():
    df = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-05", "2026-01-28"],
        "saldo": [100.0, 250.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    assert panel["saldo_mes"].tolist() == [250.0]


def test_cada_grupo_arranca_en_su_primer_mes_y_todos_terminan_en_mes_max():
    df = pd.DataFrame({
        "numero_id": [1, 2],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-03-10"],
        "saldo": [100.0, 50.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    assert (panel["numero_id"] == 1).sum() == 3   # ene, feb, mar
    assert (panel["numero_id"] == 2).sum() == 1   # solo mar
    assert panel["mes"].max() == pd.Timestamp("2026-03-01")


def test_mes_es_siempre_el_primer_dia_del_mes():
    df = pd.DataFrame({
        "numero_id": [1], "producto": ["cdt"],
        "fecha": ["2026-02-27"], "saldo": [10.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    assert panel["mes"].tolist() == [pd.Timestamp("2026-02-01")]


def test_mes_max_explicito_extiende_el_panel():
    df = pd.DataFrame({
        "numero_id": [1], "producto": ["cdt"],
        "fecha": ["2026-01-15"], "saldo": [100.0],
    })
    panel = construir_panel_mensual(
        df, group_cols=["numero_id", "producto"], mes_max=pd.Timestamp("2026-03-01")
    )
    assert panel["saldo_mes"].tolist() == [100.0, 100.0, 100.0]


def test_grupos_independientes_no_se_contaminan():
    df = pd.DataFrame({
        "numero_id": [1, 2, 2],
        "producto": ["cdt", "cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-01-15", "2026-03-01"],
        "saldo": [100.0, 999.0, 5.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    c1 = panel[panel["numero_id"] == 1].sort_values("mes")["saldo_mes"].tolist()
    assert c1 == [100.0, 100.0, 100.0]   # el 999 del cliente 2 no se filtra


def test_primer_mes_por_grupo():
    df = pd.DataFrame({
        "numero_id": [1, 1, 2],
        "fecha": ["2026-03-01", "2025-11-20", "2026-02-05"],
        "saldo": [1.0, 2.0, 3.0],
    })
    r = primer_mes_por_grupo(df, group_cols=["numero_id"]).set_index("numero_id")
    assert r.loc[1, "primer_mes"] == pd.Timestamp("2025-11-01")
    assert r.loc[2, "primer_mes"] == pd.Timestamp("2026-02-01")


def test_mes_max_anterior_al_primer_mes_del_grupo_omite_el_grupo_sin_filtrar_otros():
    """Contrato del límite de mes_max: si el primer dato real de un grupo cae
    DESPUES de mes_max, ese grupo no tiene ningún mes dentro de la ventana y
    se omite por completo (0 filas), sin afectar a otros grupos que sí caen
    dentro de la ventana."""
    df = pd.DataFrame({
        "numero_id": [1, 2],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-05-01"],
        "saldo": [100.0, 999.0],
    })
    panel = construir_panel_mensual(
        df, group_cols=["numero_id", "producto"], mes_max=pd.Timestamp("2026-03-01")
    )
    assert (panel["numero_id"] == 2).sum() == 0
    c1 = panel[panel["numero_id"] == 1].sort_values("mes")["saldo_mes"].tolist()
    assert c1 == [100.0, 100.0, 100.0]


def test_mes_max_igual_al_primer_mes_del_grupo_produce_una_fila():
    """Caso límite vecino del anterior: si el primer dato real cae EXACTAMENTE
    en mes_max, el grupo produce una única fila (no cero)."""
    df = pd.DataFrame({
        "numero_id": [1],
        "producto": ["cdt"],
        "fecha": ["2026-03-15"],
        "saldo": [100.0],
    })
    panel = construir_panel_mensual(
        df, group_cols=["numero_id", "producto"], mes_max=pd.Timestamp("2026-03-01")
    )
    assert len(panel) == 1
    assert panel["mes"].tolist() == [pd.Timestamp("2026-03-01")]
    assert panel["saldo_mes"].tolist() == [100.0]


def test_observado_distingue_mes_real_de_mes_arrastrado():
    """D9 (N5): `observado` marca los meses con fila real en `df`. Entre enero
    (real) y abril (real) los meses de por medio (feb, mar) son forward fill:
    observado=0, aunque `saldo_mes` tenga un valor no nulo."""
    df = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "fecha": ["2026-01-15", "2026-04-10"],
        "saldo": [100.0, 400.0],
    })
    panel = construir_panel_mensual(df, group_cols=["numero_id", "producto"])
    panel = panel.sort_values("mes")
    assert panel["observado"].tolist() == [1, 0, 0, 1]
    assert panel["saldo_mes"].tolist() == [100.0, 100.0, 100.0, 400.0]
