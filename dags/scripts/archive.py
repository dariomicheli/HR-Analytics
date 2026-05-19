import logging
import os
import shutil
from datetime import datetime
from scripts.config import RUTA_ARCHIVE


def archive_file(**context):
    ti = context['ti']

    # Traemos la ruta del archivo procesado
    ruta_archivo = ti.xcom_pull(task_ids='discover_input_file')

    # 1. Obtenemos el nombre base del archivo original
    nombre_original = os.path.basename(ruta_archivo)

    # 2. Separamos el nombre de la extensión
    nombre_sin_ext, extension = os.path.splitext(nombre_original)

    # 3. Generamos el texto con el día y la hora (Formato: AñoMesDia_HoraMinutoSegundo)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 4. Armamos el nuevo nombre fusionando todo
    nuevo_nombre = f"{nombre_sin_ext}_{timestamp}{extension}"

    # 5. Definimos la ruta final
    ruta_destino = f'{RUTA_ARCHIVE}{nuevo_nombre}'

    # Movemos el archivo original a la carpeta de archive con el nuevo nombre
    shutil.move(ruta_archivo, ruta_destino)
    logging.info(
        f"Éxito. Archivo original movido y renombrado a: {ruta_destino}")
