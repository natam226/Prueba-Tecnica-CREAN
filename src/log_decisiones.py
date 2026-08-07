"""Log de decisiones del pipeline (SPEC_V2 §10).

"Toda decisión de imputación debe quedar registrada en un log de decisiones."
Se registra en CSV append-only: cada fila es una decisión tomada, con la
evidencia numérica que la justificó. Si una decisión se revisa, se añade una
fila nueva en vez de sobrescribir — el historial es parte del entregable.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config

COLUMNAS = ["timestamp", "clave", "decision", "motivo", "evidencia"]


def _ruta_por_defecto() -> Path:
    return config.OUTPUTS_DIR / "decisiones" / "log_decisiones.csv"


def registrar_decision(clave: str, decision: str, motivo: str,
                       evidencia: dict | None = None, ruta: Path | None = None) -> Path:
    ruta = Path(ruta) if ruta is not None else _ruta_por_defecto()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fila = pd.DataFrame([{
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "clave": clave,
        "decision": decision,
        "motivo": motivo,
        "evidencia": json.dumps(evidencia or {}, ensure_ascii=False, default=str),
    }], columns=COLUMNAS)
    fila.to_csv(ruta, mode="a", header=not ruta.exists(), index=False, encoding="utf-8")
    return ruta


def leer_log(ruta: Path | None = None) -> pd.DataFrame:
    ruta = Path(ruta) if ruta is not None else _ruta_por_defecto()
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS)
    return pd.read_csv(ruta, encoding="utf-8")
