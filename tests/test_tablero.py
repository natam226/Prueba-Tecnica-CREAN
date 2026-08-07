"""Prueba de humo del tablero: que cada vista renderice sin excepción.

A diferencia del resto de la suite, estas pruebas SÍ necesitan que el pipeline
haya corrido -- el tablero lee artefactos reales. Se saltan cuando no existen,
para que la suite siga corriendo en un checkout limpio.

Lo que cubren es la clase de fallo que los tests unitarios no ven: que el
tablero pida una columna que un notebook dejó de escribir. Esa rotura solo
aparece al renderizar.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

ARTEFACTOS = [
    "eda/resumen_ejecutivo.json",
    "eda/resumen_shape.json",
    "eda/tasas_adopcion_por_segmento.csv",
    "eda/faltantes_tasa_adopcion.csv",
    "eda/validacion_variables.csv",
    "models/metricas_propension.json",
    "models/curva_precision_recall.csv",
    "powerbi/dimensionamiento.csv",
    "powerbi/fact_cliente_score.csv",
    "powerbi/dim_cliente.csv",
    "powerbi/fact_importancia_variables.csv",
    "powerbi/fact_auditoria_sesgo.csv",
]

faltan = [a for a in ARTEFACTOS if not (config.OUTPUTS_DIR / a).exists()]
pytestmark = pytest.mark.skipif(
    bool(faltan), reason=f"el pipeline no ha corrido; faltan: {faltan[:3]}")

VISTAS = ["Resumen", "Caracterización", "Modelos", "Oportunidad",
          "Priorización", "Sesgo y supuestos"]

RUTA_APP = str(Path(__file__).resolve().parent.parent / "app" / "tablero.py")


def _errores(app) -> list[str]:
    """`app.exception` es una ElementList vacía cuando no hubo fallo, no None."""
    return [e.value for e in app.exception]


def _abrir(vista: str):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(RUTA_APP, default_timeout=400)
    app.run()
    assert not _errores(app), f"el tablero no arranca: {_errores(app)}"
    app.radio[0].set_value(vista).run()
    return app


@pytest.mark.parametrize("vista", VISTAS)
def test_vista_renderiza_sin_excepcion(vista):
    app = _abrir(vista)
    assert not _errores(app), _errores(app)


def test_simulador_de_captura_responde():
    """El slider recalcula la oportunidad; no es decorativo."""
    app = _abrir("Oportunidad")
    app.slider[0].set_value(40).run()
    assert not _errores(app), _errores(app)
    assert any("40%" in m.label for m in app.metric), \
        "la tarjeta de oportunidad no refleja la tasa elegida"


def test_lista_de_contacto_es_descargable():
    app = _abrir("Priorización")
    assert not _errores(app), _errores(app)
    assert len(app.get("download_button")) == 1


def test_pipeline_a_medias_avisa_en_vez_de_reventar(tmp_path, monkeypatch):
    """Un paso saltado no debe tumbar el tablero con un traceback de Python.

    Antes de este guard, ejecutar el dimensionamiento sin la EDA ni la
    auditoría de sesgo dejaba tres vistas mostrando un traceback crudo. La
    vista afectada debe decir qué le falta; las demás deben seguir sirviendo.
    """
    from streamlit.testing.v1 import AppTest

    from app import datos as dat

    # Solo lo que necesitan Resumen, Oportunidad y Priorización.
    minimo = [("eda", "resumen_ejecutivo.json"),
              ("models", "metricas_propension.json"),
              ("powerbi", "dimensionamiento.csv"),
              ("powerbi", "fact_cliente_score.csv"),
              ("powerbi", "dim_cliente.csv")]
    for sub, archivo in minimo:
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        (tmp_path / sub / archivo).write_bytes(
            (config.OUTPUTS_DIR / sub / archivo).read_bytes())

    monkeypatch.setattr(config, "OUTPUTS_DIR", tmp_path)
    for f in (dat.csv, dat.jsonf, dat.base_clientes):
        f.clear()
    try:
        completas = {"Resumen", "Oportunidad", "Priorización"}
        for vista in VISTAS:
            app = AppTest.from_file(RUTA_APP, default_timeout=400)
            app.run()
            app.radio[0].set_value(vista).run()
            assert not _errores(app), f"{vista} reventó: {_errores(app)}"
            if vista in completas:
                assert not app.warning, f"{vista} avisa sin motivo"
            else:
                assert app.warning, f"{vista} no avisa de su artefacto faltante"
                # El aviso tiene que decir qué ejecutar, no solo qué falta.
                assert "produce" in app.warning[0].value
    finally:
        for f in (dat.csv, dat.jsonf, dat.base_clientes):
            f.clear()


def test_numero_id_se_expone_como_texto():
    """Es un entero de 19 dígitos: como número perdería los últimos dígitos.

    Se comprueba que sea texto, no un dtype concreto: pandas lo representa como
    `object` o como `StringDtype` según la versión, y ambos sirven.
    """
    import pandas as pd

    from app import datos as dat

    dat.base_clientes.clear()
    base = dat.base_clientes()
    assert pd.api.types.is_string_dtype(base["numero_id"])
    assert base["numero_id"].str.fullmatch(r"-?\d+").all()
    # El valor extremo real de la base excede el entero exacto de float64: si
    # alguna capa lo convirtiera a número, este dígito final se perdería.
    assert base["numero_id"].map(len).max() >= 19
