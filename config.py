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

# --- Catálogos compartidos ---
COLS_FINANCIERAS = [
    "ingresos_mensuales",
    "total_egresos_mensuales",
    "total_activos",
    "total_pasivos",
    "total_patrimonio",
]

PRODUCTOS = [
    "cuenta_ahorro", "cuenta_corriente", "bolsillos",
    "fiducuenta", "cdt", "inversion_virtual", "invesbot",
]

# Productos que DEFINEN la etiqueta de adopción (nunca predictores)
PRODUCTOS_ETIQUETA = ["invesbot", "inversion_virtual"]

# Productos de inversión que NO definen la etiqueta (sí son predictores)
PRODUCTOS_INVERSION_NO_ETIQUETA = ["cdt", "fiducuenta"]

# Productos que componen el saldo líquido (SPEC_V2 §5)
PRODUCTOS_LIQUIDOS = ["cuenta_ahorro", "cuenta_corriente", "bolsillos"]

# --- Umbrales de decisión (SPEC_V2 + DECISIONES.md) ---
UMBRAL_IV_MINIMO = 0.02              # §4.1 y §6.5
UMBRAL_AUC_FUGA = 0.95               # §1: por encima => sospechar fuga residual
UMBRAL_AUC_PATRON_DEBIL = 0.60       # §3.2
UMBRAL_AUC_PATRON_INFORMATIVO = 0.70 # §3.2

# D6: bandas de interpretación para el proxy de género, no un umbral único.
# < MODERADO -> proxy mínimo. [MODERADO, SUSTANCIAL] -> proxy moderado.
# > SUSTANCIAL -> proxy sustancial (investigar mitigación).
UMBRAL_AUC_PROXY_MODERADO = 0.60     # §6.6.1 (D6)
UMBRAL_AUC_PROXY_SUSTANCIAL = 0.70   # §6.6.1 (D6)

# D7: el Jaccard es inaplicable (conjuntos desbalanceados: máximo alcanzable
# ~0.196, ver DECISIONES.md). Se reemplaza por lift condicional.
UMBRAL_LIFT_PERFIL_INCOMPLETO = 1.5  # §5/§6.5.2 (D7)

UMBRAL_VIF = 10.0                    # §4.5
UMBRAL_IMPACTO_DISPAR = 0.80         # §6.6.2
MESES_VALIDACION_BACKTEST = 3        # §6.3.4

# D9: ventana fija de volatilidad (reutiliza VENTANA_MESES_AGREGACION, ver abajo)
# + mínimo de meses con observación REAL (no arrastrada por forward fill).
MESES_MINIMOS_CV_LIQUIDO = 3         # §5 (D9)

# D0.2: ventana de la etiqueta alternativa del análisis de sensibilidad.
VENTANA_DIAS_ETIQUETA_RECIENTE = 90  # (D0, N4)

# VENTANA_MESES_AGREGACION = 6 confirmada por D9 para snapshot/prom_6m/tendencia_6m
# Y para la ventana de cv_saldo_liquido (misma ventana, mismo FECHA_CORTE global).
VENTANA_MESES_AGREGACION = 6
RANDOM_STATE = 42
TEST_SIZE = 0.2
