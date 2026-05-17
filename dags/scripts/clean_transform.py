import logging
import pandas as pd


def clean_data(**context):
    ti = context['ti']

    # Traemos los datos desde la tarea anterior
    data = ti.xcom_pull(task_ids='extract_csv')
    logging.info("Iniciando limpieza de datos...")

    logging.info("Simulando la limpieza de nulos y casteo de datos")
    return data
