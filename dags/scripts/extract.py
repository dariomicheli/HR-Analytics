import logging
from scripts.config import COLUMNAS_ESPERADAS, RUTA_TEMP
import pandas as pd


def extract_csv(**context):
    ti = context["ti"]

    # Traemos la ruta del archivo que descubrió la tarea anterior
    ruta_archivo = ti.xcom_pull(task_ids='validate_schema')

    logging.info(f"Extrayendo datos del archivo CSV: {ruta_archivo}")

    df = pd.read_csv(ruta_archivo, usecols=COLUMNAS_ESPERADAS,
                     encoding='utf-8')

    ruta_destino = f"{RUTA_TEMP}/extract.parquet"
    df.to_parquet(ruta_destino, engine='pyarrow', index=False)

    logging.info(
        f"Extracción completada y guardada en {ruta_destino}. Número de registros extraídos: {len(df)}")
    return ruta_destino
