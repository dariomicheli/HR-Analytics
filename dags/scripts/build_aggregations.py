import logging
from scripts.config import POSTGRES_DWH_CONN_ID
from sqlalchemy.exc import SQLAlchemyError
from airflow.providers.postgres.hooks.postgres import PostgresHook


def refresh_materialized_views(**context):
    logging.info("Actualizando vistas materializadas...")

    # Nos conectamos usando las credenciales de Airflow
    hook = PostgresHook(postgres_conn_id=POSTGRES_DWH_CONN_ID)

    # Lista de las vistas que armamos para Metabase
    vistas_a_actualizar = [
        'gold_hr_active_summary',
        'gold_hr_hiring_evolution'
    ]

    try:
        # Iteramos sobre la lista y refrescamos una por una
        for vista in vistas_a_actualizar:
            logging.info(f"Ejecutando REFRESH en la vista: {vista}")

            # El comando nativo de PostgreSQL para recalcular la vista
            query_refresh = f"REFRESH MATERIALIZED VIEW {vista};"

            # hook.run() ejecuta, comitea y libera el cursor al instante
            hook.run(query_refresh)

            logging.info(f"✅ Vista {vista} actualizada correctamente.")

    except SQLAlchemyError as error_db:
        mensaje = f"❌ ERROR DE BASE DE DATOS al refrescar las vistas: {str(error_db)}"
        logging.error(mensaje)
        raise

    except Exception as error_general:
        mensaje = f"❌ ERROR INESPERADO: {str(error_general)}"
        logging.error(mensaje)
        raise
