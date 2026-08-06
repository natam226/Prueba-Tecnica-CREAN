import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.db_io import leer_tabla_sqlite

TABLAS = ["cliente_features", "dim_cliente", "dim_producto", "dim_tiempo", "fact_saldos"]


def main():
    destino = config.OUTPUTS_DIR / "powerbi"
    destino.mkdir(parents=True, exist_ok=True)
    for tabla in TABLAS:
        df = leer_tabla_sqlite(config.ORO_DB, tabla)
        ruta = destino / f"{tabla}.csv"
        df.to_csv(ruta, index=False)
        print(f"{tabla}: {len(df)} filas -> {ruta}")


if __name__ == "__main__":
    main()
