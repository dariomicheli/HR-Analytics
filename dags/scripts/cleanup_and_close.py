import logging
import os
from airflow.models import Variable


def finalizar_pipeline(**context):
    """
    Registra la firma del archivo procesado para evitar duplicados 
    y elimina los archivos temporales descargados.
    """
    ti = context['ti']

    # REGISTRAR EL ESTADO EXITOSO (Idempotencia)
    firma_str = ti.xcom_pull(task_ids="discover_input_file", key="firma_drive")
    if firma_str:
        Variable.set("hr_ultima_firma_procesada", firma_str)
        logging.info(
            f"✅ Pipeline completado. Firma actualizada en Airflow: {firma_str}")

    # LIMPIAR EL ARCHIVO RAW DESCARGADO
    ruta_archivo_csv = ti.xcom_pull(task_ids='discover_input_file')
    if ruta_archivo_csv and os.path.exists(ruta_archivo_csv):
        os.remove(ruta_archivo_csv)
        logging.info(
            f"🧹 Limpieza: Archivo temporal CSV eliminado ({ruta_archivo_csv})")

    # LIMPIAR LOS PARQUETS TEMPORALES
    ruta_extract = ti.xcom_pull(task_ids='extract_csv')
    if ruta_extract and os.path.exists(ruta_extract):
        os.remove(ruta_extract)
        logging.info(
            f"🧹 Limpieza: Parquet de extracción eliminado ({ruta_extract})")

    ruta_clean = ti.xcom_pull(task_ids='clean_data')
    if ruta_clean and os.path.exists(ruta_clean):
        os.remove(ruta_clean)
        logging.info(
            f"🧹 Limpieza: Parquet de limpieza eliminado ({ruta_clean})")
