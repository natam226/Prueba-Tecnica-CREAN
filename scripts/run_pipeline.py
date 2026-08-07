"""Orquestador del pipeline bronce -> plata -> oro (SPEC_V2).

Uso:
    python scripts/run_pipeline.py

Los notebooks NO se ejecutan aquí (son interactivos), pero a diferencia de la v1
ahora tienen dependencias reales entre sí. Orden obligatorio:

    1. python scripts/run_pipeline.py          (bronce, plata, oro, esquema estrella)
    2. notebooks/01_eda.ipynb
    3. notebooks/03_eda_faltantes.ipynb        -> decide el tratamiento de falta_estimador
    4. python -m oro.construir_cliente_features (aplica la decisión de perfil_incompleto)
    5. notebooks/04_validacion_variables.ipynb -> IV/WoE, decisión de vivienda
    6. notebooks/02_modelado.ipynb             -> modelos A y B, fact_cliente_score
    7. notebooks/06_monto_12m.ipynb            -> monto a 12m, actualiza fact_cliente_score
    8. notebooks/07_auditoria_sesgo.ipynb      -> fact_auditoria_sesgo.csv
    9. notebooks/05_dimensionamiento.ipynb     -> dimensionamiento.csv
   10. python scripts/export_powerbi.py        (falla si falta algún insumo)

Por qué el orden 3 -> 4 es obligatorio y no solo recomendado: paso 4 vuelve a
ejecutar `oro/construir_cliente_features.py`, que lee
`outputs/eda/faltantes_solapamiento.json` para decidir si crea la bandera
`perfil_incompleto` (lift condicional, D7). Ese JSON lo produce el paso 3. Si
se ejecuta el paso 4 sin haber corrido antes el paso 3, `cliente_features` no
refleja la decisión medida y los pasos 5-9 quedan corriendo sobre datos
potencialmente desactualizados.

Los pasos 7-9 se auto-referencian sobre `fact_cliente_score`: 6 la crea, 7 la
actualiza con las columnas de monto y recalcula `nivel`, y 8/9 la leen ya
actualizada. Ejecutar 8 o 9 antes de 7 no falla con una excepción clara: los
CSV resultantes simplemente no tendrán las columnas de monto o usarán niveles
sin recalcular, así que el orden importa aunque no esté forzado en código.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import bronce.extraccion as extraccion
import bronce.diagnostico_calidad as diagnostico_calidad
import plata.transformacion as transformacion
import oro.construir_cliente_features as construir_cliente_features
import oro.construir_esquema_estrella as construir_esquema_estrella


def paso(nombre, fn):
    print(f"--- {nombre} ---")
    fn()
    print(f"OK: {nombre}\n")


def _run_plata_transformacion():
    transformacion.limpiar_clientes()
    transformacion.transformar_aho_cte()
    for tabla_bronce, tabla_plata_destino in transformacion.FUENTES_PRODUCTO_UNICO:
        transformacion.transformar_producto_unico(tabla_bronce, tabla_plata_destino)
    transformacion.transformar_cdt_inversion_virtual()
    transformacion.transformar_estimador_ingresos()
    # SPEC_V2 §6.3.1 y §8: panel mensual con forward fill + primer registro
    transformacion.construir_saldos_mensual()
    transformacion.construir_primer_registro()


def main():
    paso("bronce: extracción", extraccion.main)
    paso("bronce: diagnóstico de calidad", diagnostico_calidad.main)
    paso("plata: transformaciones", _run_plata_transformacion)
    paso("oro: cliente_features", construir_cliente_features.construir_cliente_features)
    paso("oro: esquema estrella", construir_esquema_estrella.construir_esquema_estrella)
    print(__doc__.split("Orden obligatorio:")[1])
    print("Pipeline de datos completo. Ejecutar los notebooks en el orden de arriba "
          "y después `python scripts/export_powerbi.py`.")


if __name__ == "__main__":
    main()
