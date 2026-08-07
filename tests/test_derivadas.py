import numpy as np
import pandas as pd
import pytest

from src.derivadas import (
    agregar_agregados_producto,
    agregar_banderas_faltantes,
    agregar_ratios_financieros,
    agregar_tendencia_relativa,
    agregar_vivienda_como_categoria,
    division_segura,
    resumen_cv_saldo_liquido,
)


def test_division_por_cero_devuelve_nulo_no_infinito():
    """SPEC_V2 §5: todas las divisiones manejan denominador cero devolviendo
    nulo, no infinito."""
    r = division_segura(pd.Series([10.0, 10.0, 0.0]), pd.Series([2.0, 0.0, 0.0]))
    assert r.iloc[0] == 5.0
    assert pd.isna(r.iloc[1])
    assert pd.isna(r.iloc[2])
    assert not np.isinf(r.to_numpy(dtype="float64", na_value=0.0)).any()


def test_division_por_nulo_devuelve_nulo():
    r = division_segura(pd.Series([10.0]), pd.Series([np.nan]))
    assert pd.isna(r.iloc[0])


def test_division_numerador_nulo_devuelve_nulo():
    r = division_segura(pd.Series([np.nan]), pd.Series([2.0]))
    assert pd.isna(r.iloc[0])


def test_division_segura_preserva_el_indice():
    num = pd.Series([10.0, 20.0], index=[7, 9])
    den = pd.Series([2.0, 0.0], index=[7, 9])
    r = division_segura(num, den)
    assert r.index.tolist() == [7, 9]


def test_division_segura_denominador_positivo_excluye_negativos():
    """D3/N2: tendencia_relativa_6m usa denominador_positivo=True. Con un
    saldo_prom_6m negativo (sobregiro) el signo del ratio se invierte y deja
    de significar "dirección del cambio", así que se descarta a nulo."""
    r = division_segura(pd.Series([10.0, 10.0]), pd.Series([2.0, -5.0]),
                        denominador_positivo=True)
    assert r.iloc[0] == 5.0
    assert pd.isna(r.iloc[1])


def _df_financiero():
    return pd.DataFrame({
        "ingresos_mensuales": [1000.0, 0.0, 2000.0],
        "total_egresos_mensuales": [400.0, 100.0, 500.0],
        "total_activos": [5000.0, 0.0, 8000.0],
        "total_pasivos": [1000.0, 50.0, 0.0],
        "total_patrimonio": [4000.0, 0.0, 8000.0],
        "capacidad_ahorro": [600.0, -100.0, 1500.0],
        "estimador_ingreso": [900.0, np.nan, 2500.0],
    })


def test_ratios_financieros_valores_y_ceros():
    r = agregar_ratios_financieros(_df_financiero())
    assert r.loc[0, "ratio_egreso_ingreso"] == 0.4
    assert r.loc[0, "pct_ahorro_ingreso"] == 0.6
    assert r.loc[0, "ratio_pasivo_activo"] == 0.2
    assert r.loc[0, "patrimonio_por_ingreso"] == 4000.0 / 12000.0
    # D10: la variable se llama dif_ingreso_declarado_estimado y su fórmula es
    # ingresos_mensuales - estimador_ingreso (el nombre ya no contradice la fórmula)
    assert r.loc[0, "dif_ingreso_declarado_estimado"] == 100.0
    assert r.loc[0, "pct_dif_ingreso"] == 0.1
    # cliente 1: ingresos 0 y activos 0 -> todos los ratios nulos, ninguno inf
    for col in ["ratio_egreso_ingreso", "pct_ahorro_ingreso",
                "ratio_pasivo_activo", "patrimonio_por_ingreso", "pct_dif_ingreso"]:
        assert pd.isna(r.loc[1, col]), col
    # cliente 2: activos 8000 y pasivos 0 -> 0.0, que es un valor legítimo
    assert r.loc[2, "ratio_pasivo_activo"] == 0.0
    # estimador nulo -> dif nulo, no 0
    assert pd.isna(r.loc[1, "dif_ingreso_declarado_estimado"])


def _df_productos():
    cols = {}
    for p in ["cuenta_ahorro", "cuenta_corriente", "bolsillos",
              "fiducuenta", "cdt", "inversion_virtual", "invesbot"]:
        cols[f"{p}_saldo_snapshot"] = [0.0, 0.0]
    df = pd.DataFrame(cols)
    df.loc[0, "cuenta_ahorro_saldo_snapshot"] = 100.0
    df.loc[0, "bolsillos_saldo_snapshot"] = 50.0
    df.loc[0, "cdt_saldo_snapshot"] = 700.0
    df.loc[0, "invesbot_saldo_snapshot"] = 9000.0
    df["total_patrimonio"] = [1000.0, 0.0]
    return df


def test_agregados_producto_distinguen_total_de_no_etiqueta():
    r = agregar_agregados_producto(_df_productos())
    assert r.loc[0, "saldo_liquido_total"] == 150.0     # ahorro + corriente + bolsillos
    assert r.loc[0, "n_productos_total"] == 4           # ahorro, bolsillos, cdt, invesbot
    assert r.loc[0, "n_productos_no_etiqueta"] == 3     # sin invesbot ni inv. virtual
    assert r.loc[0, "ratio_liquidez_patrimonio"] == 0.15
    assert pd.isna(r.loc[1, "ratio_liquidez_patrimonio"])   # patrimonio 0 -> nulo


def test_tendencia_relativa_por_producto():
    """D3: tendencia_relativa_6m = tendencia_6m / saldo_prom_6m, por producto.

    Fixture simplificada respecto al borrador del brief (que construía el
    DataFrame con un reindex seguido de reasignación de columnas para llegar
    al mismo resultado): se construye directo con las tres filas que importan
    -- denominador positivo, cero y negativo -- para cdt, y una fila extra
    para fiducuenta que confirma que el cálculo es independiente por producto.
    """
    df = pd.DataFrame({
        "cdt_tendencia_6m": [200.0, 50.0, 10.0],
        "cdt_saldo_prom_6m": [1000.0, 0.0, -20.0],
        "fiducuenta_tendencia_6m": [30.0, 0.0, 0.0],
        "fiducuenta_saldo_prom_6m": [300.0, 0.0, 0.0],
    })
    r = agregar_tendencia_relativa(df)
    assert r.loc[0, "cdt_tendencia_relativa_6m"] == pytest.approx(0.2)
    assert pd.isna(r.loc[1, "cdt_tendencia_relativa_6m"])   # denominador 0
    assert pd.isna(r.loc[2, "cdt_tendencia_relativa_6m"])   # denominador negativo (N2)
    assert r.loc[0, "fiducuenta_tendencia_relativa_6m"] == pytest.approx(0.1)


def test_banderas_faltantes_por_bloque():
    df = pd.DataFrame({
        "ingresos_mensuales": [1.0, np.nan],
        "total_activos": [1.0, np.nan],
        "estimador_ingreso": [np.nan, 5.0],
    })
    r = agregar_banderas_faltantes(df, {
        "financiero": ["ingresos_mensuales", "total_activos"],
        "estimador": ["estimador_ingreso"],
    })
    assert r["falta_financiero"].tolist() == [0, 1]
    assert r["falta_estimador"].tolist() == [1, 0]


def test_vivienda_nulo_se_convierte_en_nivel_sin_dato():
    """SPEC_V2 §6.5: missing as a category, no imputación."""
    df = pd.DataFrame({"desc_tipo_de_vivienda": ["PROPIA", None, "ARRENDADA", np.nan]})
    r = agregar_vivienda_como_categoria(df)
    assert r["desc_tipo_de_vivienda"].tolist() == ["PROPIA", "Sin dato", "ARRENDADA", "Sin dato"]
    assert r["tiene_dato_vivienda"].tolist() == [1, 0, 1, 0]
    assert r["desc_tipo_de_vivienda"].isna().sum() == 0


FECHA_CORTE_TEST = pd.Timestamp("2026-06-01")
PRODUCTOS_LIQUIDOS_TEST = ["cuenta_ahorro", "cuenta_corriente", "bolsillos"]


def test_cv_saldo_liquido_coeficiente_de_variacion_sobre_ventana_fija():
    """D9: ventana fija de 6M desde fecha_corte, coeficiente de variación
    (std poblacional / media), no desviación absoluta.

    La ventana con fecha_corte=2026-06-01 y meses_ventana=6 es
    [2026-01-01, 2026-06-01] (Ene-Jun, ambos extremos inclusive = 6 cubos
    mensuales), así que las 6 filas del fixture están todas dentro."""
    panel = pd.DataFrame({
        "numero_id": [1] * 6,
        "producto": ["cuenta_ahorro"] * 6,
        "mes": pd.date_range("2026-01-01", periods=6, freq="MS"),
        "saldo_mes": [100.0, 100.0, 200.0, 200.0, 300.0, 300.0],
        "observado": [1, 0, 1, 0, 1, 0],   # 3 meses observados, cumple el mínimo
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    # media=(100+100+200+200+300+300)/6=200
    # std poblacional=sqrt(((-100)^2*2+0^2*2+100^2*2)/6)=sqrt(40000/6)=81.649658
    # cv=81.649658/200=0.408248 (verificado independientemente por cálculo,
    # no leyendo el resultado de la implementación)
    assert r.loc[1, "cv_saldo_liquido"] == pytest.approx(0.408248, rel=1e-4)
    assert r.loc[1, "cv_saldo_liquido_insuficiente"] == 0


def test_cv_saldo_liquido_nulo_si_menos_del_minimo_de_meses_observados():
    """D9: por debajo de 3 meses CON DATO (no arrastrado), nulo con bandera —
    nunca un valor calculado sobre muy pocos puntos."""
    panel = pd.DataFrame({
        "numero_id": [2] * 6,
        "producto": ["cuenta_ahorro"] * 6,
        "mes": pd.date_range("2026-01-01", periods=6, freq="MS"),  # Ene-Jun, dentro de la ventana
        "saldo_mes": [50.0] * 4 + [80.0, 80.0],
        "observado": [1, 0, 0, 0, 1, 0],   # solo 2 meses observados
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    assert pd.isna(r.loc[2, "cv_saldo_liquido"])
    assert r.loc[2, "cv_saldo_liquido_insuficiente"] == 1


def test_cv_saldo_liquido_nulo_si_media_no_es_positiva():
    """D9: manejar media cero (o negativa, sobregiro) devolviendo nulo."""
    panel = pd.DataFrame({
        "numero_id": [3] * 3,
        "producto": ["cuenta_corriente"] * 3,
        "mes": pd.date_range("2026-04-01", periods=3, freq="MS"),
        "saldo_mes": [-50.0, -50.0, -50.0],
        "observado": [1, 1, 1],
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    assert pd.isna(r.loc[3, "cv_saldo_liquido"])
    assert r.loc[3, "cv_saldo_liquido_insuficiente"] == 0   # sí hubo suficiente dato; el problema es la media


def test_cv_saldo_liquido_ignora_meses_fuera_de_la_ventana_de_6m():
    """La ventana es FIJA de 6 meses [fecha_corte - 5 meses, fecha_corte]
    (Ene-Jun 2026 para fecha_corte=2026-06-01): un mes anterior a la ventana
    no debe influir en la media/std aunque esté en el panel. Si el valor de
    hace 17 meses (999999) se colara, la media/std ya no serían 0."""
    panel = pd.DataFrame({
        "numero_id": [4] * 7,
        "producto": ["bolsillos"] * 7,
        "mes": pd.to_datetime([
            "2025-01-01",  # fuera de la ventana (17 meses antes de fecha_corte)
            "2026-01-01", "2026-02-01", "2026-03-01",
            "2026-04-01", "2026-05-01", "2026-06-01",
        ]),
        "saldo_mes": [999999.0] + [100.0] * 6,
        "observado": [1] * 7,
    })
    r = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST).set_index("numero_id")
    # dentro de la ventana los 6 meses valen 100 parejo -> media=100, std=0
    assert r.loc[4, "cv_saldo_liquido"] == pytest.approx(0.0)   # saldo plano DENTRO de la ventana


def test_cv_saldo_liquido_ignora_productos_no_liquidos():
    panel = pd.DataFrame({
        "numero_id": [1, 1],
        "producto": ["cdt", "cdt"],
        "mes": pd.to_datetime(["2026-04-01", "2026-05-01"]),
        "saldo_mes": [0.0, 100000.0],
        "observado": [1, 1],
    })
    r = resumen_cv_saldo_liquido(panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST)
    assert len(r) == 0


def test_cv_saldo_liquido_ventana_contiene_exactamente_seis_meses():
    """Ancla el tamaño de la ventana en 6 meses exactos (ni 5 ni 7): un
    fixture con dato real en 8 meses consecutivos (Nov 2025-Jun 2026), donde
    solo Ene-Jun 2026 deberían caer dentro de [fecha_corte - 5m, fecha_corte].

    Se prueba el límite exacto pasando `meses_minimos` explícito a ambos
    lados del conteo real de meses en ventana (6):
      - meses_minimos=6 -> los 6 meses en ventana SÍ alcanzan -> suficiente.
      - meses_minimos=7 -> los mismos 6 meses YA NO alcanzan -> insuficiente.
    Si la ventana tuviera 7 cubos (el bug original) el segundo caso pasaría
    a "suficiente" y el test fallaría, delatando el drift de +-1 mes.

    Los saldos son una progresión aritmética (10..80, paso 10) para que,
    además, el promedio de la ventana ancle CUÁLES 6 meses quedaron
    incluidos: Ene-Jun da media 55; Dic-May (un mes corrido) daría media 45;
    Nov-Jun con 7 meses (el bug) daría media 50 -- ninguno de esos otros
    valores pasaría la comparación con pytest.approx de abajo.
    """
    panel = pd.DataFrame({
        "numero_id": [5] * 8,
        "producto": ["cuenta_ahorro"] * 8,
        "mes": pd.date_range("2025-11-01", periods=8, freq="MS"),
        "saldo_mes": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
        "observado": [1] * 8,
    })
    r6 = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST,
        meses_minimos=6).set_index("numero_id")
    assert r6.loc[5, "cv_saldo_liquido_insuficiente"] == 0
    # ventana = [30, 40, 50, 60, 70, 80] (Ene-Jun): media=55,
    # std poblacional=sqrt(1750/6)=17.078251 -> cv=17.078251/55=0.310514
    # (verificado independientemente por cálculo)
    assert r6.loc[5, "cv_saldo_liquido"] == pytest.approx(0.310514, rel=1e-4)

    r7 = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=FECHA_CORTE_TEST,
        meses_minimos=7).set_index("numero_id")
    assert r7.loc[5, "cv_saldo_liquido_insuficiente"] == 1
    assert pd.isna(r7.loc[5, "cv_saldo_liquido"])


def test_cv_saldo_liquido_ventana_no_depende_del_dia_de_fecha_corte():
    """`fecha_corte` en producción (src/fecha_corte.calcular_fecha_corte)
    es un min(max_fecha) de datos reales -- NO tiene por qué caer en día 1.
    `panel_mensual["mes"]` sí es siempre día 1 (src/panel_mensual.py). Con
    un fecha_corte de mitad de mes (17), la ventana debe seguir cubriendo
    exactamente los mismos 6 cubos mensuales que con un fecha_corte de
    día 1 en el mismo mes -- restar DateOffset directamente sobre un
    fecha_corte con día > 1 dejaría fuera el cubo más antiguo, igual que el
    bug original dejaba fuera un cubo por el otro extremo."""
    panel = pd.DataFrame({
        "numero_id": [5] * 8,
        "producto": ["cuenta_ahorro"] * 8,
        "mes": pd.date_range("2025-11-01", periods=8, freq="MS"),
        "saldo_mes": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
        "observado": [1] * 8,
    })
    fecha_corte_mitad_de_mes = pd.Timestamp("2026-06-17")
    r6 = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=fecha_corte_mitad_de_mes,
        meses_minimos=6).set_index("numero_id")
    assert r6.loc[5, "cv_saldo_liquido_insuficiente"] == 0
    # mismos 6 cubos que con fecha_corte=2026-06-01 (Ene-Jun) -> mismo cv
    assert r6.loc[5, "cv_saldo_liquido"] == pytest.approx(0.310514, rel=1e-4)

    r7 = resumen_cv_saldo_liquido(
        panel, PRODUCTOS_LIQUIDOS_TEST, fecha_corte=fecha_corte_mitad_de_mes,
        meses_minimos=7).set_index("numero_id")
    assert r7.loc[5, "cv_saldo_liquido_insuficiente"] == 1
