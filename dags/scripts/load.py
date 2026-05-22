import logging
import os
from airflow.providers.postgres.hooks.postgres import PostgresHook
from scripts.config import COLUMNAS_STG, POSTGRES_DWH_CONN_ID, RUTA_TEMP
import pandas as pd


def load_data_postgres(**context):
    ti = context['ti']
    clean_filepath = ti.xcom_pull(task_ids='clean_data')

    if not clean_filepath:
        raise ValueError(
            "ERROR: No se recibió la ruta de los datos desde la etapa de limpieza.")

    logging.info("Iniciando la carga de datos en PostgreSQL...")

    # Definimos ruta para el csv temporal
    csv_temporal = f"{RUTA_TEMP}stg_load_temp.csv"

    # Leemos el archivo limpio
    df = pd.read_parquet(clean_filepath, engine='pyarrow')  # type: ignore

    logging.info(f"Guardando {len(df):,} registros en disco temporalmente...")

    # Guardamos el DataFrame a disco
    df.to_csv(csv_temporal, index=False, header=False, sep='\t')

    logging.info(
        f"Archivo temporal guardado en {csv_temporal}. Preparando carga masiva...")

    # Liberamos la memoria RAM eliminando el DataFrame
    del df

    # Nos conectamos a la base de datos configurada en Airflow
    hook = PostgresHook(postgres_conn_id=POSTGRES_DWH_CONN_ID)
    conn = None
    cursor = None

    try:
        conn = hook.get_conn()
        cursor = conn.cursor()

        logging.info(
            "Ejecutando TRUNCATE en la tabla stg_hr para vaciar registros anteriores...")
        cursor.execute("TRUNCATE TABLE stg_hr;")

        # Ejecución del comando COPY
        # Le pasamos explícitamente el nombre de las columnas al motor de Postgres
        columnas_str = ", ".join(COLUMNAS_STG)
        sql_copy = f"COPY stg_hr ({columnas_str}) FROM STDIN WITH CSV DELIMITER '\t'"

        logging.info("Ejecutando COPY...")

        # El stream de datos se hace directo desde el disco a PostgreSQL
        with open(csv_temporal, 'r') as file_obj:
            cursor.copy_expert(sql_copy, file_obj)

        # Confirmamos la transacción (TRUNCATE + COPY)
        conn.commit()
        logging.info("¡Carga masiva a la tabla de Staging completada!")

    except Exception as error_general:
        if conn:
            conn.rollback()
        mensaje = f"❌ ERROR INESPERADO durante la carga de datos: {str(error_general)}"
        logging.error(mensaje)
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

        # Limpieza del archivo temporal para no llenar el disco del contenedor
        if os.path.exists(csv_temporal):
            os.remove(csv_temporal)
            logging.debug(
                f"Archivo temporal {csv_temporal} eliminado del disco.")
