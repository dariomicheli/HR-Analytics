import logging
from airflow.providers.postgres.hooks.postgres import PostgresHook


def load_data_postgres(**context):
    ti = context['ti']

    clean_data = ti.xcom_pull(task_ids='clean_data')

    # Nos conectamos a la base de datos configurada en Airflow
    hook = PostgresHook(postgres_conn_id='postgres_dwh')
    conn = hook.get_conn()
    cur = conn.cursor()

    logging.info(
        f"Conectado a PostgreSQL. Insertando {len(clean_data)} registros...")

    # Confirmamos los cambios (Commit) y cerramos la conexión
    conn.commit()
    cur.close()
    conn.close()
    logging.info("Carga en el Data Warehouse finalizada con éxito.")
