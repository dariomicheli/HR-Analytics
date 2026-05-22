import logging
import pandas as pd
from scripts.config import COLUMNAS_ESPERADAS


def validate_schema(**context):
    ti = context['ti']
    ruta_archivo = ti.xcom_pull(task_ids='discover_input_file')
    DELIMITADOR_ESPERADO = ','

    logging.info(
        f"Iniciando validación del esquema del archivo: {ruta_archivo}")

    try:
        # Abrimos el archivo forzando la lectura en UTF-8
        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            primera_linea = f.readline()
            segunda_linea = f.readline()

    except UnicodeDecodeError:
        mensaje_error = f"ERROR DE ENCODING: El archivo {ruta_archivo} no es UTF-8. Por favor, conviértelo a UTF-8 antes de procesarlo."
        logging.error(mensaje_error)
        raise ValueError(mensaje_error)

    if DELIMITADOR_ESPERADO not in primera_linea:
        mensaje_error = f"ERROR DE DELIMITADOR: No se detectó '{DELIMITADOR_ESPERADO}' en la cabecera."
        logging.error(mensaje_error)
        raise ValueError(mensaje_error)

    # Si la segunda línea no existe o está en blanco, el archivo solo tiene cabeceras
    if not segunda_linea or not segunda_linea.strip():
        mensaje_error = "ERROR DE DATOS: El archivo tiene encabezados pero está vacío. No hay registros para procesar."
        logging.error(mensaje_error)
        raise ValueError(mensaje_error)

    logging.info(
        "Validaciones físicas superadas. Verificando contrato de datos...")

    # Leemos solo la primera fila para obtener las columnas (sin cargar todo el CSV)
    df_preview = pd.read_csv(ruta_archivo, nrows=0,
                             sep=DELIMITADOR_ESPERADO, encoding='utf-8')
    columnas_csv = [col.strip() for col in df_preview.columns]

    # Validamos que estén todas las columnas que necesitamos
    columnas_faltantes = set(COLUMNAS_ESPERADAS) - set(df_preview.columns)
    if columnas_faltantes:
        mensaje_error = f"El archivo {ruta_archivo} no tiene las siguientes columnas esperadas: {columnas_faltantes}"
        logging.error(mensaje_error)
        raise ValueError(mensaje_error)

    # Columnas sobrantes
    columnas_sobrantes = set(columnas_csv) - set(COLUMNAS_ESPERADAS)
    if columnas_sobrantes:
        logging.warning(
            f"El archivo {ruta_archivo} tiene columnas adicionales que no se usarán: {columnas_sobrantes}")

    logging.info("El esquema es válido. Listo para extracción y carga.")

    return ruta_archivo
