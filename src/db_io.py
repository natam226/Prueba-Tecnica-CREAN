import sqlite3
import zipfile
from pathlib import Path

import pandas as pd


def extraer_zip_a_db(zip_path: Path, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        nombres_db = [n for n in z.namelist() if n.endswith(".db")]
        if len(nombres_db) != 1:
            raise ValueError(f"Se esperaba un único .db en {zip_path}, se encontraron {nombres_db}")
        z.extract(nombres_db[0], destino_dir)
    return destino_dir / nombres_db[0]


def leer_tabla_sqlite(db_path: Path, tabla: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql(f'SELECT * FROM "{tabla}"', con)


def escribir_tabla_sqlite(df: pd.DataFrame, db_path: Path, tabla: str, if_exists: str = "replace") -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        df.to_sql(tabla, con, if_exists=if_exists, index=False)
