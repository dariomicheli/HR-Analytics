import logging
from scripts.config import RUTA_INPUT
import pandas as pd


def extract_csv(**context):
    df = pd.read_csv(RUTA_INPUT)
    logging.info(
        "Simulando la lectura del archivo CSV desde /opt/airflow/data/input")
    return df
