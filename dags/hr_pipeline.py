from scripts.quality_checks import quality_checks
from scripts.build_aggregations import refresh_materialized_views
from scripts.cleanup_and_close import finalizar_pipeline
from scripts.config import RUTA_INPUT
from scripts.discover import discover_input_file
from scripts.validate_schema import validate_schema
from scripts.load import load_data_postgres
from scripts.clean_transform import clean_data
from scripts.extract import extract_csv
from airflow.operators.python import PythonOperator
from airflow import DAG
from datetime import datetime, timedelta
from scripts.gdrive_sensor import GDriveCSVSensor
from scripts.config import GDRIVE_CONN_ID, GDRIVE_FOLDER_ID
# ---------------------------------------------------------------------------
# Configuración del DAG
# ---------------------------------------------------------------------------
default_args = {
    "owner": "equipo_datos",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="hr_analytics_pipeline",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    # schedule_interval="*/5 * * * *", # Cada 5 min
    schedule_interval=None,   # Trigger manual o via API externa
    catchup=False,
    max_active_runs=1,
    tags=["etl", "csv", "gdrive"],
) as dag:
    """
    # ── 1. SENSOR ─────────────────────────────────────────────────────────
    # Vigila la carpeta de Drive hasta que aparezca al menos un CSV válido.
    tarea_esperar = GDriveCSVSensor(
        task_id="esperar_csv_en_drive",
        gdrive_conn_id=GDRIVE_CONN_ID,
        folder_id=GDRIVE_FOLDER_ID,
        poke_interval=300,    # revisar cada 5 min
        mode="reschedule",
    )
    """
    # ── 2. DISCOVER ───────────────────────────────────────────────────────
    # Lista los CSVs en Drive, valida cantidad/tamaño, descarga el más nuevo
    # a RUTA_TEMP y publica la ruta local via XCom.
    tarea_descubrir = PythonOperator(
        task_id="discover_input_file",
        python_callable=discover_input_file,
    )

    # ── 3. VALIDATE SCHEMA ────────────────────────────────────────────────
    # Verifica encoding UTF-8, delimitador, presencia de todas las columnas
    # esperadas. Falla el pipeline antes de gastar recursos si el CSV es inválido.
    tarea_validar = PythonOperator(
        task_id="validate_schema",
        python_callable=validate_schema,
    )

    # ── 4. EXTRACT ────────────────────────────────────────────────────────
    # Lee el CSV con PyArrow → escribe Parquet en RUTA_TEMP (extract.parquet)
    tarea_extraer = PythonOperator(
        task_id="extract_csv",
        python_callable=extract_csv,
    )

    # ── 5. CLEAN & TRANSFORM ─────────────────────────────────────────────
    # 11 etapas de limpieza con Polars → clean.parquet
    tarea_transformar = PythonOperator(
        task_id="clean_data",
        python_callable=clean_data,
    )

    # ── 6. LOAD ───────────────────────────────────────────────────────────
    # TRUNCATE + COPY masivo a stg_hr en PostgreSQL
    tarea_cargar = PythonOperator(
        task_id="load_data_postgres",
        python_callable=load_data_postgres,
    )

    # Quality Checks post-carga
    tarea_controles_calidad = PythonOperator(
        task_id="quality_checks",
        python_callable=quality_checks,
    )

    # ── 7. REFRESH MATERIALIZED VIEWS ─────────────────────────────────────
    # Actualiza las vistas gold para Metabase
    tarea_actualizar_vm = PythonOperator(
        task_id="refresh_materialized_views",
        python_callable=refresh_materialized_views,
    )

    # ── 8. ARCHIVE ────────────────────────────────────────────────────────
    # Registra la firma del archivo procesado y limpia los archivos temporales.
    tarea_cerrar_limpiar = PythonOperator(
        task_id="finalizar_pipeline",
        python_callable=finalizar_pipeline,
    )

    # ── Orden de ejecución ────────────────────────────────────────────────
    (
        tarea_descubrir
        >> tarea_validar
        >> tarea_extraer
        >> tarea_transformar
        >> tarea_cargar
        >> tarea_controles_calidad
        >> tarea_actualizar_vm
        >> tarea_cerrar_limpiar
    )
