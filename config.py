from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
BRONCE_DIR = ROOT / "bronce" / "data"
PLATA_DIR = ROOT / "plata" / "data"
ORO_DIR = ROOT / "oro" / "data"
OUTPUTS_DIR = ROOT / "outputs"

BRONCE_DB = BRONCE_DIR / "bronce.db"
PLATA_DB = PLATA_DIR / "plata.db"
ORO_DB = ORO_DIR / "oro.db"

# --- Parámetros PROVISIONALES sujetos a confirmación (ver "Preguntas Abiertas" del plan) ---
VENTANA_MESES_AGREGACION = 6  # Pregunta Abierta #1 y #2
RANDOM_STATE = 42
TEST_SIZE = 0.2
