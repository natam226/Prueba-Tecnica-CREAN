import pandas as pd

import config
from src.db_io import escribir_tabla_sqlite
from oro.construir_cliente_features import construir_cliente_features


def _tabla_producto(numero_id, producto, saldo_snapshot=100.0, saldo_prom_6m=100.0,
                     tendencia_6m=0.0, n_obs_ventana=1, tenencia=1):
    """Fila mínima con el esquema que produce agregar_serie_saldo (post Fix 1)."""
    return {
        "numero_id": numero_id,
        "producto": producto,
        "saldo_snapshot": saldo_snapshot,
        "fecha_snapshot": "2026-06-01",
        "saldo_prom_6m": saldo_prom_6m,
        "tendencia_6m": tendencia_6m,
        "n_obs_ventana": n_obs_ventana,
        "tenencia": tenencia,
    }


def test_construir_cliente_features_logica_de_negocio(tmp_path, monkeypatch):
    """
    Cubre las dos reglas de negocio más consecuentes de todo el pipeline:
    etiqueta_adopcion y excluir_modelado. Clientes sintéticos:
      - 201: saldo positivo en invesbot -> etiqueta_adopcion == 1
      - 202: saldo positivo solo en CDT (no invesbot/inversion_virtual)
             -> etiqueta_adopcion == 0 (CDT/Fiducuenta son señal, no parte de la etiqueta)
      - 203: sin tenencia en ningún producto y sin estimador_ingreso -> excluir_modelado == 1
      - 204: sin tenencia en ningún producto pero CON estimador_ingreso -> excluir_modelado == 0
    """
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    clientes_plata = pd.DataFrame({"numero_id": [201, 202, 203, 204]})
    escribir_tabla_sqlite(clientes_plata, plata_db, "clientes_plata")

    # aho_cte_plata: ninguno de nuestros clientes sintéticos tiene cuenta_ahorro/corriente
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                               "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"]),
        plata_db, "aho_cte_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                               "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"]),
        plata_db, "bolsillos_plata",
    )
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["numero_id", "producto", "saldo_snapshot", "fecha_snapshot",
                               "saldo_prom_6m", "tendencia_6m", "n_obs_ventana", "tenencia"]),
        plata_db, "fiducuenta_plata",
    )

    # cdt_inversion_virtual_plata: 202 tiene CDT positivo (no debe activar la etiqueta)
    cdt_inv = pd.DataFrame([_tabla_producto(202, "cdt", saldo_snapshot=1000.0)])
    escribir_tabla_sqlite(cdt_inv, plata_db, "cdt_inversion_virtual_plata")

    # invesbot_plata: 201 tiene saldo positivo (debe activar la etiqueta)
    invesbot = pd.DataFrame([_tabla_producto(201, "invesbot", saldo_snapshot=500.0)])
    escribir_tabla_sqlite(invesbot, plata_db, "invesbot_plata")

    # estimador_ingresos_plata: solo 204 tiene estimador de ingreso
    estimador = pd.DataFrame({
        "numero_id": [204],
        "estimador_ingreso": [3_000_000.0],
        "tiene_estimador_ingreso": [True],
    })
    escribir_tabla_sqlite(estimador, plata_db, "estimador_ingresos_plata")

    resultado = construir_cliente_features()
    resultado = resultado.set_index("numero_id")

    # (a) saldo positivo en invesbot -> adopción
    assert resultado.loc[201, "etiqueta_adopcion"] == 1
    # (b) saldo positivo solo en CDT -> NO adopción (CDT/Fiducuenta no son parte de la etiqueta)
    assert resultado.loc[202, "etiqueta_adopcion"] == 0
    assert resultado.loc[201, "cdt_tenencia"] == 0
    assert resultado.loc[202, "invesbot_tenencia"] == 0
    assert resultado.loc[202, "inversion_virtual_tenencia"] == 0

    # (c) sin tenencia en ningún producto y sin estimador_ingreso -> excluir del modelado
    assert resultado.loc[203, "excluir_modelado"] == 1
    assert resultado.loc[203, "etiqueta_adopcion"] == 0

    # (d) sin tenencia en ningún producto pero con estimador_ingreso -> NO excluir
    assert resultado.loc[204, "excluir_modelado"] == 0


def test_agregados_de_inversion_excluyen_los_productos_de_la_etiqueta(tmp_path, monkeypatch):
    """SPEC_V2 §1.1: n_productos_inversion_no_etiqueta y saldo_invertido_no_etiqueta
    se calculan SOLO con CDT y Fiducuenta. Un cliente con saldo enorme en Invesbot
    y cero en CDT/Fiducuenta debe quedar en 0 en ambas columnas."""
    plata_db = tmp_path / "plata.db"
    oro_db = tmp_path / "oro.db"
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    monkeypatch.setattr(config, "ORO_DB", oro_db)

    escribir_tabla_sqlite(pd.DataFrame({"numero_id": [301, 302]}), plata_db, "clientes_plata")

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
