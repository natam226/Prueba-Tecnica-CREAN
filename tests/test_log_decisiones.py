import pandas as pd

from src.log_decisiones import leer_log, registrar_decision


def test_registrar_crea_el_archivo_con_cabecera(tmp_path):
    ruta = tmp_path / "log.csv"
    registrar_decision("imputacion_estimador", "no_imputar",
                       "AUC=0.55 -> ausencia aleatoria y el modelo maneja nulos",
                       evidencia={"auc": 0.55}, ruta=ruta)
    df = leer_log(ruta)
    assert list(df.columns) == ["timestamp", "clave", "decision", "motivo", "evidencia"]
    assert df.loc[0, "clave"] == "imputacion_estimador"
    assert df.loc[0, "decision"] == "no_imputar"


def test_registrar_hace_append_y_conserva_el_historial(tmp_path):
    ruta = tmp_path / "log.csv"
    registrar_decision("vivienda", "conservar_categorica", "IV=0.031", ruta=ruta)
    registrar_decision("vivienda", "descartar", "IV recalculado=0.008", ruta=ruta)
    df = leer_log(ruta)
    assert len(df) == 2
    assert df.loc[1, "decision"] == "descartar"


def test_evidencia_se_serializa_como_json(tmp_path):
    import json
    ruta = tmp_path / "log.csv"
    registrar_decision("k", "d", "m", evidencia={"auc": 0.7, "n": 3}, ruta=ruta)
    df = leer_log(ruta)
    assert json.loads(df.loc[0, "evidencia"]) == {"auc": 0.7, "n": 3}


def test_evidencia_vacia_no_rompe(tmp_path):
    ruta = tmp_path / "log.csv"
    registrar_decision("k", "d", "m", ruta=ruta)
    df = leer_log(ruta)
    assert df.loc[0, "evidencia"] == "{}"


def test_leer_log_inexistente_devuelve_dataframe_vacio(tmp_path):
    df = leer_log(tmp_path / "no_existe.csv")
    assert df.empty
    assert list(df.columns) == ["timestamp", "clave", "decision", "motivo", "evidencia"]
