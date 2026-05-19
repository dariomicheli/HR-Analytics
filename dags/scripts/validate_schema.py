import logging
import pandas as pd
from scripts.config import COLUMNAS_ESPERADAS

# dos columnas iguales
# encoding
# delimitador
# #que el archivo no esté vacío


def validate_schema(**context):
    ti = context['ti']

    # Traemos la ruta del archivo que descubrió la tarea anterior
    ruta_archivo = ti.xcom_pull(task_ids='discover_input_file')

    logging.info(f"Validando el esquema del archivo: {ruta_archivo}")

    # Leemos solo la primera fila para obtener las columnas (sin cargar todo el CSV)
    df_preview = pd.read_csv(ruta_archivo, nrows=0)

    # Validamos que estén todas las columnas que necesitamos
    columnas_faltantes = set(COLUMNAS_ESPERADAS) - set(df_preview.columns)

    if columnas_faltantes:
        mensaje_error = f"El archivo {ruta_archivo} no tiene las siguientes columnas esperadas: {columnas_faltantes}"
        logging.error(mensaje_error)
        raise ValueError(mensaje_error)

    logging.info("El esquema es válido. Listo para extracción y carga.")

    # Si todo está bien, volvemos a pasar la ruta hacia adelante
    return ruta_archivo
