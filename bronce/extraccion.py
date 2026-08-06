# bronce/extraccion.py
import os
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.db_io import extraer_zip_a_db, leer_tabla_sqlite, escribir_tabla_sqlite


def _limpiar_solo_lectura(func, path, exc_info):
    # onerror de shutil.rmtree: en Windows (y en particular en carpetas sincronizadas
    # por OneDrive) los directorios recién creados pueden quedar con el atributo
    # de solo-lectura, lo que hace fallar rmdir/unlink con PermissionError incluso
    # tras haber borrado todo el contenido. Se limpia el atributo y se reintenta.
    os.chmod(path, stat.S_IWRITE)
    func(path)


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

    if sys.version_info >= (3, 12):
        shutil.rmtree(staging, onexc=_limpiar_solo_lectura)
    else:
        shutil.rmtree(staging, onerror=_limpiar_solo_lectura)


if __name__ == "__main__":
    main()
