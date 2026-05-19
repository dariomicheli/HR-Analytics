import logging
from scripts.config import NOMBRE_ARCHIVO, RUTA_INPUT
import pandas as pd


def extract_csv(**context):
    ti = context["ti"]

    # Traemos la ruta del archivo que descubrió la tarea anterior
    ruta_archivo = ti.xcom_pull(task_ids='validate_schema')

    logging.info(f"Extrayendo datos del archivo CSV: {ruta_archivo}")

    df = pd.read_csv(ruta_archivo)

    logging.info(
        f"Extracción completada. Número de registros extraídos: {len(df)}")
    return df
