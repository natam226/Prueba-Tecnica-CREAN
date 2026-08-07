# tests/test_transformacion_mensual.py
import pandas as pd

import config
from src.db_io import escribir_tabla_sqlite, leer_tabla_sqlite
from plata.transformacion import (
    construir_saldos_mensual, construir_primer_registro, reportar_recorte_por_fuente,
)


def _bronce_minimo(bronce_db):
    escribir_tabla_sqlite(
        pd.DataFrame({
            "fecha": ["2026-01-10", "2026-03-05"],
            "numero_id": [1, 1],
            "producto": ["CUENTA DE AHORRO", "CUENTA DE AHORRO"],
            "saldo": [100.0, 300.0],
        }),
        bronce_db, "crean_aho_cte",
    )
    for tabla, producto in [("crean_bolsillos", "BOLSILLOS"),
                            ("crean_fiducuenta", "FIDUCUENTA"),
                            ("invesbot", "INVESBOT")]:
        escribir_tabla_sqlite(
            pd.DataFrame({"fecha": ["2026-02-01"], "numero_id": [2],
                          "producto": [producto], "saldo": [50.0]}),
            bronce_db, tabla,
        )
    escribir_tabla_sqlite(
        pd.DataFrame({"fecha": ["2026-03-01"], "numero_id": [1],
                      "producto": ["CDT"], "saldo": [7.0]}),
        bronce_db, "crean_inv_virtual_cdt",
    )


def test_saldos_mensual_aplica_forward_fill_por_cliente_producto(tmp_path, monkeypatch):
    bronce_db = tmp_path / "bronce.db"
    plata_db = tmp_path / "plata.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    _bronce_minimo(bronce_db)

    construir_saldos_mensual()
    r = leer_tabla_sqlite(plata_db, "saldos_mensual_plata")
    r["mes"] = pd.to_datetime(r["mes"])

    # D4: FECHA_CORTE = min(max_fecha por fuente) = 2026-02-01 en este fixture
    # (bolsillos/fiducuenta/invesbot solo tienen dato hasta esa fecha). El dato
    # de aho_cte del 2026-03-05 queda POR ENCIMA del corte y no debe usarse:
    # ninguna fuente se regulariza más allá de lo que ven las demás.
    ahorro = r[(r["numero_id"] == 1) & (r["producto"] == "cuenta_ahorro")].sort_values("mes")
    assert ahorro["mes"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")]
    assert ahorro["saldo_mes"].tolist() == [100.0, 100.0]   # ene (real), feb (ffill)
    assert ahorro["observado"].tolist() == [1, 0]
    # `cdt` (fuente crean_inv_virtual_cdt) solo tiene una fila, en 2026-03-01,
    # que queda POR ENCIMA del corte global (2026-02-01). Por el contrato de
    # frontera de `construir_panel_mensual` (Task 6, ver src/panel_mensual.py):
    # un grupo cuyo primer mes real es POSTERIOR a mes_max se omite del panel
    # por completo (cero filas) — no se inventa una fila con un saldo que
    # nunca existió antes del corte. Por eso `cdt` NO aparece en este fixture.
    assert set(r["producto"]) == {"cuenta_ahorro", "bolsillos", "fiducuenta", "invesbot"}
    assert r[r["producto"] == "cdt"].empty
    assert not r.duplicated(subset=["numero_id", "producto", "mes"]).any()
    assert r["mes"].max() == pd.Timestamp("2026-02-01")   # ninguna fuente pasa del corte global


def test_primer_registro_toma_el_minimo_entre_las_fuentes_no_etiqueta(tmp_path, monkeypatch):
    """`_bronce_minimo` no coloca a Invesbot como el mínimo real para ningún
    cliente, así que este caso no distingue "todas las fuentes" de "solo las
    no-etiqueta" -- ver test_primer_registro_excluye_productos_de_etiqueta
    para el caso que sí lo hace."""
    bronce_db = tmp_path / "bronce.db"
    plata_db = tmp_path / "plata.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    _bronce_minimo(bronce_db)

    construir_primer_registro()
    r = leer_tabla_sqlite(plata_db, "primer_registro_plata").set_index("numero_id")
    assert pd.Timestamp(r.loc[1, "primer_mes"]) == pd.Timestamp("2026-01-01")
    assert pd.Timestamp(r.loc[2, "primer_mes"]) == pd.Timestamp("2026-02-01")


def test_primer_registro_excluye_productos_de_etiqueta(tmp_path, monkeypatch):
    """D8 amendment (ver leakage-investigation.md, 2026-08-06): 'primer
    registro del cliente en CUALQUIER fuente' se redefine a 'cualquier fuente
    NO-etiqueta' (config.PRODUCTOS_ETIQUETA). Antes de este fix, el registro
    más antiguo de un cliente en Invesbot/Inversión Virtual determinaba
    `primer_mes` para ~32% de los adoptantes, convirtiendo
    `antiguedad_relacion_meses` en un proxy directo de `etiqueta_adopcion`."""
    bronce_db = tmp_path / "bronce.db"
    plata_db = tmp_path / "plata.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)
    monkeypatch.setattr(config, "PLATA_DB", plata_db)

    # numero_id=1: Invesbot (etiqueta) es la fuente GLOBALMENTE más antigua
    # (2026-01-01) pero debe ser ignorada; cuenta_ahorro (no-etiqueta) empieza
    # después (2026-03-01) y debe ser la que determine primer_mes.
    escribir_tabla_sqlite(
        pd.DataFrame({"fecha": ["2026-01-01"], "numero_id": [1],
                      "producto": ["INVESBOT"], "saldo": [500.0]}),
        bronce_db, "invesbot")
    escribir_tabla_sqlite(
        pd.DataFrame({"fecha": ["2026-03-01"], "numero_id": [1],
                      "producto": ["CUENTA DE AHORRO"], "saldo": [100.0]}),
        bronce_db, "crean_aho_cte")
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["fecha", "numero_id", "producto", "saldo"]),
        bronce_db, "crean_bolsillos")
    escribir_tabla_sqlite(
        pd.DataFrame(columns=["fecha", "numero_id", "producto", "saldo"]),
        bronce_db, "crean_fiducuenta")
    # numero_id=2: SOLO tiene dato en Inversión Virtual (etiqueta). Sin
    # ninguna fuente no-etiqueta, el cliente no debe aparecer en absoluto en
    # el resultado -- no hay señal de antigüedad no-etiqueta para él (mismo
    # edge case que `sin_dato_reciente` en la capa oro).
    escribir_tabla_sqlite(
        pd.DataFrame({"fecha": ["2026-02-01"], "numero_id": [2],
                      "producto": ["INVERSION_VIRTUAL"], "saldo": [300.0]}),
        bronce_db, "crean_inv_virtual_cdt")

    construir_primer_registro()
    r = leer_tabla_sqlite(plata_db, "primer_registro_plata").set_index("numero_id")

    assert pd.Timestamp(r.loc[1, "primer_mes"]) == pd.Timestamp("2026-03-01")
    assert 2 not in r.index


def _bronce_con_fila_intrames_posterior_al_corte(bronce_db):
    """4 de las 5 fuentes terminan exactamente el 2026-02-01; `crean_aho_cte`
    tiene una fila extra el 2026-02-15 — MISMO mes de corte, DÍA posterior.
    FECHA_CORTE = min(max_fecha por fuente) = 2026-02-01 de todas formas
    (aho_cte no es la fuente que fija el mínimo). Pin de la regresión D4:
    sin truncar por día antes de bucketear a mes, `construir_panel_mensual`
    tomaría la fila del 02-15 (saldo=999.0) como "el" valor de febrero para
    aho_cte, aunque ninguna otra fuente ve nada después del día 1."""
    escribir_tabla_sqlite(
        pd.DataFrame({
            "fecha": ["2026-01-10", "2026-02-01", "2026-02-15"],
            "numero_id": [1, 1, 1],
            "producto": ["CUENTA DE AHORRO"] * 3,
            "saldo": [100.0, 200.0, 999.0],
        }),
        bronce_db, "crean_aho_cte",
    )
    for tabla, producto in [("crean_bolsillos", "BOLSILLOS"),
                            ("crean_fiducuenta", "FIDUCUENTA"),
                            ("invesbot", "INVESBOT")]:
        escribir_tabla_sqlite(
            pd.DataFrame({"fecha": ["2026-02-01"], "numero_id": [2],
                          "producto": [producto], "saldo": [50.0]}),
            bronce_db, tabla,
        )
    escribir_tabla_sqlite(
        pd.DataFrame({"fecha": ["2026-02-01"], "numero_id": [1],
                      "producto": ["CDT"], "saldo": [7.0]}),
        bronce_db, "crean_inv_virtual_cdt",
    )


def test_saldos_mensual_trunca_por_dia_no_solo_por_mes(tmp_path, monkeypatch):
    bronce_db = tmp_path / "bronce.db"
    plata_db = tmp_path / "plata.db"
    monkeypatch.setattr(config, "BRONCE_DB", bronce_db)
    monkeypatch.setattr(config, "PLATA_DB", plata_db)
    _bronce_con_fila_intrames_posterior_al_corte(bronce_db)

    construir_saldos_mensual()
    r = leer_tabla_sqlite(plata_db, "saldos_mensual_plata")
    r["mes"] = pd.to_datetime(r["mes"])

    # La fila del 2026-02-15 (saldo=999.0) queda por ENCIMA del corte
    # (2026-02-01), aunque caiga en el mismo mes calendario. No debe influir
    # en `saldo_mes` de febrero: ese mes debe quedar en 200.0 (la fila del
    # día 01, la única <= FECHA_CORTE), no en 999.0.
    ahorro = r[(r["numero_id"] == 1) & (r["producto"] == "cuenta_ahorro")].sort_values("mes")
    assert ahorro["mes"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")]
    assert ahorro["saldo_mes"].tolist() == [100.0, 200.0]
    assert 999.0 not in ahorro["saldo_mes"].tolist()
    assert ahorro["observado"].tolist() == [1, 1]   # ambos meses tienen fila real <= corte

    # D4: el reporte por fuente debe reflejar la fila descartada a nivel de día.
    stats = reportar_recorte_por_fuente()
    assert stats["crean_aho_cte"]["filas_totales"] == 3
    assert stats["crean_aho_cte"]["filas_posteriores_al_corte"] == 1
    assert stats["crean_aho_cte"]["grupos_omitidos_por_corte"] == 0
    assert stats["crean_aho_cte"]["fecha_max_fuente"] == pd.Timestamp("2026-02-15")
