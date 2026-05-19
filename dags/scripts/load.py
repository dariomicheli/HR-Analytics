import io
import logging
from airflow.providers.postgres.hooks.postgres import PostgresHook
from scripts.config import COLUMNAS_STG, POSTGRES_DWH_CONN_ID
import pandas as pd


def load_data_postgres(**context):
    ti = context['ti']
    clean_filepath = ti.xcom_pull(task_ids='clean_data')

    if not clean_filepath:
        raise ValueError(
            "ERROR: No se recibió la ruta de los datos desde la etapa de limpieza.")

    logging.info("Iniciando la carga de datos en PostgreSQL...")

    # Leemos el archivo limpio
    df = pd.read_parquet(clean_filepath, engine='pyarrow')  # type: ignore

    # Nos conectamos a la base de datos configurada en Airflow
    hook = PostgresHook(postgres_conn_id=POSTGRES_DWH_CONN_ID)
    conn = None
    cursor = None

    logging.info("Conexión a PostgreSQL establecida.")

    try:
        conn = hook.get_conn()
        cursor = conn.cursor()

        logging.info(
            "Ejecutando TRUNCATE en la tabla stg_hr para vaciar registros anteriores...")
        cursor.execute("TRUNCATE TABLE stg_hr;")

        # Preparación del buffer en memoria RAM para el COPY masivo
        logging.info(
            f"Preparando {len(df)} registros para inyección directa...")
        buffer_memoria = io.StringIO()

        # Volcamos el DataFrame a ese archivo virtual en formato CSV (separado por tabulaciones)
        df.to_csv(buffer_memoria, index=False, header=False, sep='\t')

        # Rebobinamos el buffer al inicio
        buffer_memoria.seek(0)

        # Ejecución del comando COPY
        # Le pasamos explícitamente el nombre de las columnas al motor de Postgres
        columnas_str = ", ".join(COLUMNAS_STG)
        sql_copy = f"COPY stg_hr ({columnas_str}) FROM STDIN WITH CSV DELIMITER '\t'"

        logging.info("Ejecutando COPY...")
        cursor.copy_expert(sql_copy, buffer_memoria)

        # 8. Confirmamos la transacción (TRUNCATE + COPY)
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
