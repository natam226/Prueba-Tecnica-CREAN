# bronce/extraccion.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.db_io import extraer_zip_a_db, leer_tabla_sqlite, escribir_tabla_sqlite

FUENTES = [
    ("clientes.zip", "clientes.db", "clientes"),
    ("crean_aho_cte.zip", "crean_aho_cte.db", "crean_aho_cte"),
    ("crean_bolsillos.zip", "crean_bolsillos.db", "crean_bolsillos"),
    ("crean_fiducuenta.zip", "crean_fiducuenta.db", "crean_fiducuenta"),
    ("crean_inv_virtual_cdt.zip", "crean_inv_virtual_cdt.db", "crean_inv_virtual_cdt"),
    ("invesbot.zip", "invesbot.db", "invesbot"),
    ("estimador_ing.zip", "estimador_ing.db", "estimador_ing"),
]


def main():
    staging = config.BRONCE_DIR / "_staging"
    for zip_name, db_filename, tabla in FUENTES:
        zip_path = config.DATA_DIR / zip_name
        db_path = extraer_zip_a_db(zip_path, staging)
        assert db_path.name == db_filename, f"esperaba {db_filename}, extraído {db_path.name}"
        df = leer_tabla_sqlite(db_path, tabla)
        escribir_tabla_sqlite(df, config.BRONCE_DB, tabla)
        print(f"{tabla}: {len(df)} filas -> bronce.db")


if __name__ == "__main__":
    main()
