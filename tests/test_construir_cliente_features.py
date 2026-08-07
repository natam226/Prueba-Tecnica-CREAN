import pandas as pd

import config
from src.db_io import escribir_tabla_sqlite
from oro.construir_cliente_features import construir_cliente_features


def _tabla_producto(numero_id, producto, saldo_snapshot=100.0, saldo_prom_6m=100.0,
                     tendencia_6m=0.0, n_obs_ventana=1, tenencia=1, fecha_snapshot="2026-06-01"):
    """Fila mínima con el esquema que produce agregar_serie_saldo (post Fix 1)."""
    return {
        "numero_id": numero_id,
        "producto": producto,
        "saldo_snapshot": saldo_snapshot,
        "fecha_snapshot": fecha_snapshot,
        "saldo_prom_6m": saldo_prom_6m,
        "tendencia_6m": tendencia_6m,
        "n_obs_ventana": n_obs_ventana,
        "tenencia": tenencia,
    }


def test_construir_cliente_features_logica_de_negocio(tmp_path, monkeypatch):
    """
    Cubre las dos reglas de negocio más consecuentes: etiqueta_adopcion y las
    banderas de población de SPEC_V2 §2. Clientes sintéticos:
      - 201: saldo positivo en invesbot -> etiqueta_adopcion == 1
      - 202: saldo positivo solo en CDT -> etiqueta_adopcion == 0
      - 203: sin producto, sin estimador, sin financieros -> apto_entrenamiento == 0
      - 204: sin producto pero CON estimador -> apto_entrenamiento == 1
    """
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)
    monkeypatch.setattr(
        "oro.construir_cliente_features.calcular_fecha_corte",
        lambda: pd.Timestamp("2026-06-01"))

    clientes_plata = pd.DataFrame({
        "numero_id": [201, 202, 203, 204],
        "sin_dato_financiero_total": [False, False, True, True],
    })
    escribir_tabla_sqlite(clientes_plata, plata_db, "clientes_plata")

    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    escribir_tabla_sqlite(vacia, plata_db, "aho_cte_plata")
    escribir_tabla_sqlite(vacia, plata_db, "bolsillos_plata")
    escribir_tabla_sqlite(vacia, plata_db, "fiducuenta_plata")

    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(202, "cdt", saldo_snapshot=1000.0)]),
        plata_db, "cdt_inversion_virtual_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(201, "invesbot", saldo_snapshot=500.0)]),
        plata_db, "invesbot_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [204], "estimador_ingreso": [3_000_000.0],
                      "tiene_estimador_ingreso": [True]}),
        plata_db, "estimador_ingresos_plata",
    )

    resultado = construir_cliente_features().set_index("numero_id")

    assert resultado.loc[201, "etiqueta_adopcion"] == 1
    assert resultado.loc[202, "etiqueta_adopcion"] == 0
    assert resultado.loc[201, "cdt_tenencia"] == 0
    assert resultado.loc[202, "invesbot_tenencia"] == 0

    # SPEC_V2 §2: excluir_modelado desaparece
    assert "excluir_modelado" not in resultado.columns

    # tiene_historial_producto: separado de la aptitud para entrenar
    assert resultado.loc[201, "tiene_historial_producto"] == 1
    assert resultado.loc[202, "tiene_historial_producto"] == 1
    assert resultado.loc[203, "tiene_historial_producto"] == 0
    assert resultado.loc[204, "tiene_historial_producto"] == 0

    # única exclusión admitida: sin señal en NINGUNA fuente
    assert resultado.loc[203, "apto_entrenamiento"] == 0
    assert resultado.loc[203, "sin_ninguna_senal"] == 1
    # 204 no tiene producto pero sí estimador -> entra al entrenamiento como negativo legítimo
    assert resultado.loc[204, "apto_entrenamiento"] == 1
    assert resultado.loc[204, "sin_ninguna_senal"] == 0


def test_cliente_sin_producto_pero_con_datos_financieros_entra_al_entrenamiento(tmp_path, monkeypatch):
    """SPEC_V2 §2: los ~90.467 clientes con datos financieros completos y sin
    historial de producto son ejemplos negativos legítimos y necesarios.
    No pueden quedar fuera del entrenamiento ni del scoring."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)
    monkeypatch.setattr(
        "oro.construir_cliente_features.calcular_fecha_corte",
        lambda: pd.Timestamp("2026-06-01"))

    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [401], "sin_dato_financiero_total": [False]}),
        plata_db, "clientes_plata",
    )
    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    for t in ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata",
              "cdt_inversion_virtual_plata", "invesbot_plata"]:
        escribir_tabla_sqlite(vacia, plata_db, t)
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata",
    )

    r = construir_cliente_features().set_index("numero_id")
    assert r.loc[401, "tiene_historial_producto"] == 0
    assert r.loc[401, "apto_entrenamiento"] == 1   # tiene señal financiera
    assert r.loc[401, "sin_ninguna_senal"] == 0


def test_agregados_de_inversion_excluyen_los_productos_de_la_etiqueta(tmp_path, monkeypatch):
    """SPEC_V2 §1.1: n_productos_inversion_no_etiqueta y saldo_invertido_no_etiqueta
    se calculan SOLO con CDT y Fiducuenta. Un cliente con saldo enorme en Invesbot
    y cero en CDT/Fiducuenta debe quedar en 0 en ambas columnas."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)
    monkeypatch.setattr(
        "oro.construir_cliente_features.calcular_fecha_corte",
        lambda: pd.Timestamp("2026-06-01"))

    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [301, 302],
                      "sin_dato_financiero_total": [False, False]}),
        plata_db, "clientes_plata",
    )

    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    escribir_tabla_sqlite(vacia, plata_db, "aho_cte_plata")
    escribir_tabla_sqlite(vacia, plata_db, "bolsillos_plata")

    # 302: 700 en Fiducuenta -> cuenta
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(302, "fiducuenta", saldo_snapshot=700.0)]),
        plata_db, "fiducuenta_plata",
    )
    # 302: 300 en CDT -> cuenta. 301: nada.
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(302, "cdt", saldo_snapshot=300.0)]),
        plata_db, "cdt_inversion_virtual_plata",
    )
    # 301: 9.000.000 en Invesbot -> NO debe contar
    escribir_tabla_sqlite(
        pd.DataFrame([_tabla_producto(301, "invesbot", saldo_snapshot=9_000_000.0)]),
        plata_db, "invesbot_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata",
    )

    r = construir_cliente_features().set_index("numero_id")

    assert r.loc[301, "n_productos_inversion_no_etiqueta"] == 0
    assert r.loc[301, "saldo_invertido_no_etiqueta"] == 0.0
    assert r.loc[302, "n_productos_inversion_no_etiqueta"] == 2
    assert r.loc[302, "saldo_invertido_no_etiqueta"] == 1000.0


def test_recencia_de_dato_y_etiqueta_alternativa(tmp_path, monkeypatch):
    """D0: dias_desde_ultimo_dato es el máximo de fecha_snapshot entre las 5
    fuentes de saldo (N1); etiqueta_adopcion_reciente exige que el snapshot de
    Invesbot/Inversión Virtual esté dentro de la ventana de recencia (N4)."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)
    monkeypatch.setattr(
        "oro.construir_cliente_features.calcular_fecha_corte",
        lambda: pd.Timestamp("2026-06-01"))

    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [601, 602, 603],
                      "sin_dato_financiero_total": [False, False, False]}),
        plata_db, "clientes_plata")

    vacia = pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                                   "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"])
    for t in ["aho_cte_plata", "bolsillos_plata", "fiducuenta_plata", "cdt_inversion_virtual_plata"]:
        escribir_tabla_sqlite(vacia, plata_db, t)

    # 601: saldo positivo en invesbot, snapshot RECIENTE (dentro de 90 días del corte)
    # 602: saldo positivo en invesbot, snapshot ANTIGUO (fuera de la ventana)
    # 603: sin ninguna fila de producto -> sin dato en absoluto
    escribir_tabla_sqlite(pd.DataFrame([
        _tabla_producto(601, "invesbot", saldo_snapshot=500.0, fecha_snapshot="2026-05-15"),
        _tabla_producto(602, "invesbot", saldo_snapshot=500.0, fecha_snapshot="2025-01-01"),
    ]), plata_db, "invesbot_plata")

    escribir_tabla_sqlite(
        pd.DataFrame({"numero_id": [], "estimador_ingreso": [], "tiene_estimador_ingreso": []}),
        plata_db, "estimador_ingresos_plata")

    r = construir_cliente_features().set_index("numero_id")

    assert r.loc[601, "etiqueta_adopcion"] == 1        # etiqueta principal: sin exigir recencia
    assert r.loc[602, "etiqueta_adopcion"] == 1        # también positivo, aunque el dato sea viejo
    assert r.loc[601, "etiqueta_adopcion_reciente"] == 1
    assert r.loc[602, "etiqueta_adopcion_reciente"] == 0   # fuera de la ventana de 90 días
    assert r.loc[603, "etiqueta_adopcion_reciente"] == 0

    assert r.loc[601, "dias_desde_ultimo_dato"] == 17
    assert pd.isna(r.loc[603, "dias_desde_ultimo_dato"])
    assert r.loc[603, "sin_dato_reciente"] == 1
    assert r.loc[601, "sin_dato_reciente"] == 0
