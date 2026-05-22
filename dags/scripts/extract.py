import logging
from scripts.config import COLUMNAS_ESPERADAS, RUTA_TEMP
from pyarrow import csv as pv
import pyarrow.parquet as pq


def extract_csv(**context):
    ti = context["ti"]

    # Traemos la ruta del archivo que descubrió la tarea anterior
    ruta_archivo = ti.xcom_pull(task_ids='validate_schema')

    logging.info(f"Extrayendo datos del archivo CSV: {ruta_archivo}")

    # Le indicamos a Arrow qué columnas nos interesan
    convert_options = pv.ConvertOptions(include_columns=COLUMNAS_ESPERADAS)

    # Leemos el CSV directamente a una PyArrow Table (estructura C++ ultra ligera)
    tabla_arrow = pv.read_csv(
        ruta_archivo,
        convert_options=convert_options
    )

    ruta_destino = f"{RUTA_TEMP}/extract.parquet"

    # 3. Escribimos la tabla directamente a formato Parquet
    pq.write_table(tabla_arrow, ruta_destino)

    logging.info(
        f"Extracción completada y guardada en {ruta_destino}. Número de registros extraídos: {tabla_arrow.num_rows:,}")
    return ruta_destino
