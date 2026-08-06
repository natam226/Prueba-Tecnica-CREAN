import sqlite3
import zipfile

import pandas as pd

from src.db_io import extraer_zip_a_db, leer_tabla_sqlite, escribir_tabla_sqlite


def test_extraer_zip_a_db(tmp_path):
    db_path = tmp_path / "origen.db"
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")

    zip_path = tmp_path / "origen.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.write(db_path, arcname="origen.db")

    destino = tmp_path / "extraido"
    resultado = extraer_zip_a_db(zip_path, destino)

    assert resultado == destino / "origen.db"
    assert resultado.exists()


def test_leer_y_escribir_tabla_sqlite(tmp_path):
    df = pd.DataFrame({"numero_id": [1, 2], "saldo": [10.0, 20.0]})
    db_path = tmp_path / "salida.db"

    escribir_tabla_sqlite(df, db_path, "mi_tabla")
    resultado = leer_tabla_sqlite(db_path, "mi_tabla")

    pd.testing.assert_frame_equal(resultado, df)
