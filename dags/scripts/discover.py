import os
import glob
import logging
from scripts.config import RUTA_INPUT


def discover_input_file(**context):
    patron_busqueda = os.path.join(f"{RUTA_INPUT}", "*.csv")

    # Buscamos todos los CSV en la carpeta
    archivos_encontrados = glob.glob(patron_busqueda)

    if not archivos_encontrados:
        logging.info(f"No se encontraron archivos CSV en {RUTA_INPUT}")
        raise FileNotFoundError(
            f"No se encontraron archivos CSV en {RUTA_INPUT}")

    # Si hay varios, nos quedamos con el modificado más recientemente
    archivo_mas_nuevo = max(archivos_encontrados, key=os.path.getmtime)

    logging.info(f"Archivo detectado para procesar: {archivo_mas_nuevo}")

    # Devolvemos la ruta para que la atrape el validador
    return archivo_mas_nuevo
