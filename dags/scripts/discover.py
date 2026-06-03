"""
discover.py — Descubrimiento y descarga de archivos CSV desde Google Drive
==========================================================================

Responsabilidades:
  1. Listar todos los archivos CSV en la carpeta de Drive configurada.
  2. Aplicar validaciones de negocio (cantidad, MIME, tamaño).
  3. Descargar el archivo elegido (el más reciente si hay varios) a RUTA_TEMP.
  4. Publicar la ruta local via XCom para que la consuma validate_schema.

Dependencias:
  pip install apache-airflow-providers-google google-api-python-client
"""

import logging
import os
import io
from datetime import timezone

from airflow.providers.google.common.hooks.base_google import GoogleBaseHook
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from scripts.config import (
    GDRIVE_CONN_ID,
    GDRIVE_FOLDER_ID,
    GDRIVE_MIME_TYPES_PERMITIDOS,
    GDRIVE_MAX_ARCHIVOS_ESPERADOS,
    RUTA_TEMP,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tamaño máximo aceptado para un CSV de HR: 200 MB
# (ajustá según tu volumen real de datos)
# ---------------------------------------------------------------------------
MAX_BYTES: int = 200 * 1024 * 1024


def _get_drive_service():
    """Construye el cliente de Drive usando la conexión de Airflow."""
    hook = GoogleBaseHook(gcp_conn_id=GDRIVE_CONN_ID)
    credentials = hook.get_credentials()
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _listar_csvs(service) -> list[dict]:
    """
    Devuelve la lista de archivos CSV en la carpeta de Drive,
    ordenados por fecha de modificación descendente (más nuevo primero).
    """
    mime_filter = " or ".join(
        f"mimeType='{m}'" for m in GDRIVE_MIME_TYPES_PERMITIDOS
    )
    query = (
        f"'{GDRIVE_FOLDER_ID}' in parents"
        f" and ({mime_filter})"
        f" and trashed=false"
    )

    archivos: list[dict] = []
    page_token = None

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc",
                pageToken=page_token,
            )
            .execute()
        )
        archivos.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return archivos


def _validar_lista(archivos: list[dict]) -> dict:
    """
    Aplica todas las validaciones sobre la lista de archivos encontrados.
    Devuelve el archivo elegido (el más nuevo) o lanza excepción.
    """
    # ── 1. Carpeta vacía ──────────────────────────────────────────────────
    if not archivos:
        raise FileNotFoundError(
            f"No se encontraron archivos CSV en la carpeta de Drive "
            f"(folder_id={GDRIVE_FOLDER_ID}). "
            "Verificá que el archivo fue subido y que tiene el MIME correcto."
        )

    # ── 2. Más archivos de los esperados ──────────────────────────────────
    if GDRIVE_MAX_ARCHIVOS_ESPERADOS > 0 and len(archivos) > GDRIVE_MAX_ARCHIVOS_ESPERADOS:
        nombres = [a["name"] for a in archivos]
        logger.warning(
            f"⚠️  Se encontraron {len(archivos)} archivos CSV en Drive "
            f"(se esperaban {GDRIVE_MAX_ARCHIVOS_ESPERADOS}). "
            f"Archivos encontrados: {nombres}. "
            "Se procesará el más reciente y se ignorarán el resto. "
            "Revisá la carpeta de Drive para limpiar archivos viejos."
        )

    # Elegimos siempre el más nuevo (ya viene ordenado por modifiedTime desc)
    elegido = archivos[0]
    logger.info(
        f"✅ Archivo elegido para procesar: '{elegido['name']}' "
        f"(id={elegido['id']}, modificado={elegido.get('modifiedTime', 'N/A')})"
    )

    # ── 3. Extensión del nombre ────────────────────────────────────────────
    nombre = elegido["name"]
    if not nombre.lower().endswith(".csv"):
        raise ValueError(
            f"El archivo '{nombre}' no tiene extensión .csv. "
            "Revisá que el archivo subido sea efectivamente un CSV."
        )

    # ── 4. Tamaño ─────────────────────────────────────────────────────────
    size_bytes = int(elegido.get("size", 0))
    if size_bytes == 0:
        raise ValueError(
            f"El archivo '{nombre}' tiene 0 bytes. "
            "El archivo está vacío o Drive aún no terminó de procesar la subida."
        )

        

    logger.info(f"   Tamaño: {size_bytes / 1_048_576:.2f} MB — dentro del límite.")
    return elegido


def _descargar_archivo(service, archivo: dict) -> str:
    """
    Descarga el archivo de Drive a RUTA_TEMP y devuelve la ruta local.
    Usa streaming para no agotar la RAM en archivos grandes.
    """
    os.makedirs(RUTA_TEMP, exist_ok=True)
    ruta_local = os.path.join(RUTA_TEMP, archivo["name"])

    request = service.files().get_media(fileId=archivo["id"])
    buffer = io.FileIO(ruta_local, mode="wb")
    downloader = MediaIoBaseDownload(buffer, request, chunksize=8 * 1024 * 1024)

    logger.info(f"⬇️  Descargando '{archivo['name']}' desde Drive...")
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            logger.info(f"   Progreso: {int(status.progress() * 100)}%")

    buffer.close()
    logger.info(f"✅ Descarga completada → {ruta_local}")
    return ruta_local


# ---------------------------------------------------------------------------
# Función principal (callable de Airflow)
# ---------------------------------------------------------------------------

def discover_input_file(**context) -> str:
    """
    Tarea Airflow: descubre y descarga el CSV más reciente de Google Drive.

    Retorna la ruta local del archivo descargado (via XCom).
    """
    logger.info(f"🔍 Consultando Google Drive (folder_id={GDRIVE_FOLDER_ID})...")

    service = _get_drive_service()

    # 1. Listar
    archivos = _listar_csvs(service)
    logger.info(f"   Archivos CSV encontrados en Drive: {len(archivos)}")

    # 2. Validar y elegir
    elegido = _validar_lista(archivos)

    # 3. Descargar
    ruta_local = _descargar_archivo(service, elegido)

    # 4. Publicar ruta para las tareas siguientes
    return ruta_local
