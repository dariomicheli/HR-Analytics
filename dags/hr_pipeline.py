from scripts.build_aggregations import refresh_materialized_views
from scripts.archive import archive_file
from scripts.config import RUTA_INPUT
from scripts.discover import discover_input_file
from scripts.validate_schema import validate_schema
from scripts.load import load_data_postgres
from scripts.clean_transform_polars import clean_data
from scripts.extract import extract_csv
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.operators.python import PythonOperator
from airflow import DAG
from datetime import datetime, timedelta
from airflow.sensors.filesystem import FileSensor


# Configuración básica del DAG
default_args = {
    "owner": "equipo_datos",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10)
}

with DAG(
    dag_id="hr_analytics_pipeline",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # None significa que se ejecuta manual dándole al botón "Play"
    catchup=False,
    max_active_runs=1,
    tags=["etl", "csv"],
) as dag:

    # Vigila la carpeta input para detectar la llegada de un nuevo archivo CSV
    tarea_esperar = FileSensor(
        task_id="esperar_archivo_csv",
        # Espera a que cualquier archivo CSV aparezca en la carpeta
        filepath=f"{RUTA_INPUT}*.csv",
        poke_interval=60,  # Revisa cada 60 segundos
        mode="reschedule"
    )

    # Descubre la ruta del archivo CSV recién llegado
    tarea_descubrir = PythonOperator(
        task_id="discover_input_file",
        python_callable=discover_input_file,
    )

    # Valida que el CSV tenga el esquema correcto antes de procesarlo
    tarea_validar = PythonOperator(
        task_id="validate_schema",
        python_callable=validate_schema,
    )

    # Extraer los datos del CSV
    tarea_extraer = PythonOperator(
        task_id="extract_csv",
        python_callable=extract_csv,
    )

    # Limpiar y transformar
    tarea_transformar = PythonOperator(
        task_id="clean_data",
        python_callable=clean_data,
    )

    # Cargar en Staging
    tarea_cargar = PythonOperator(
        task_id="load_data_postgres",
        python_callable=load_data_postgres,
    )

    tarea_actualizar_vm = PythonOperator(
        task_id="refresh_materialized_views",
        python_callable=refresh_materialized_views,
    )

    tarea_archivar = PythonOperator(
        task_id="archive_file",
        python_callable=archive_file,
    )

    # Definimos el orden estricto de ejecución (El Pipeline)
    tarea_esperar >> tarea_descubrir >> tarea_validar >> tarea_extraer >> tarea_transformar >> tarea_cargar >> tarea_actualizar_vm >> tarea_archivar
