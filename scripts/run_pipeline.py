"""Orquestador end-to-end del pipeline bronce -> plata -> oro -> Power BI.

Ejecuta cada paso importando y llamando directamente su función de entrada
(en vez de usar subprocess), para evitar reintroducir el problema de sys.path
con una convención de invocación distinta. Uso:

    python scripts/run_pipeline.py

Los notebooks de EDA (01_eda.ipynb) y modelado (02_modelado.ipynb) NO se
ejecutan aquí: son exploratorios/interactivos por naturaleza y se corren
manualmente en Jupyter. Desde el Fix 2 de la revisión final, 02_modelado.ipynb
ya no depende del CSV que produce 01_eda.ipynb, así que pueden ejecutarse en
cualquier orden entre sí (aunque correr primero la EDA sigue siendo lo
recomendado, ya que documenta los datos antes de modelar).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import bronce.extraccion as extraccion
import bronce.diagnostico_calidad as diagnostico_calidad
import plata.transformacion as transformacion
import oro.construir_cliente_features as construir_cliente_features
import oro.construir_esquema_estrella as construir_esquema_estrella
import scripts.export_powerbi as export_powerbi


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


def main():
    paso("bronce: extracción", extraccion.main)
    paso("bronce: diagnóstico de calidad", diagnostico_calidad.main)
    paso("plata: transformaciones", _run_plata_transformacion)
    paso("oro: cliente_features", construir_cliente_features.construir_cliente_features)
    paso("oro: esquema estrella", construir_esquema_estrella.construir_esquema_estrella)
    print(
        "NOTA: los notebooks 01_eda.ipynb y 02_modelado.ipynb NO se ejecutan "
        "automáticamente (son exploratorios/interactivos) — correrlos manualmente "
        "en Jupyter antes o después de este paso, según se necesite.\n"
    )
    paso("Power BI: export", export_powerbi.main)
    print("Pipeline completo (excepto notebooks).")


if __name__ == "__main__":
    main()
