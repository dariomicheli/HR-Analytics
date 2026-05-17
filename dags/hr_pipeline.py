from scripts.load import load_data_postgres
from scripts.clean_transform import clean_data
from scripts.extract import extract_csv
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.python import PythonOperator
from airflow import DAG
from datetime import datetime, timedelta


# Configuración básica del DAG
default_args = {
    "owner": "equipo_datos",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id="hr_analytics_pipeline",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # None significa que se ejecuta manual dándole al botón "Play"
    catchup=False,
    tags=["etl", "csv"],
) as dag:

    # 2. Extraer los datos del CSV
    tarea_extraer = PythonOperator(
        task_id="extraer_csv",
        python_callable=extract_csv,
    )

    # 3. Limpiar y transformar
    tarea_transformar = PythonOperator(
        task_id="transformar_datos",
        python_callable=clean_data,
    )

    # 4. Cargar en Staging
    tarea_cargar = PythonOperator(
        task_id="cargar_a_postgres",
        python_callable=load_data_postgres,
    )

    # Definimos el orden estricto de ejecución (El Pipeline)
    tarea_extraer >> tarea_transformar >> tarea_cargar
