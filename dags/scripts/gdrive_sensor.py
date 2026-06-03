"""
gdrive_sensor.py — Sensor custom para detectar CSVs en Google Drive
====================================================================

Reemplaza al FileSensor local. En cada poke consulta la API de Drive
y retorna True (pasa a la siguiente tarea) si hay al menos un CSV
válido en la carpeta configurada.

Uso en el DAG:
    from scripts.gdrive_sensor import GDriveCSVSensor

    tarea_esperar = GDriveCSVSensor(
        task_id="esperar_csv_en_drive",
        poke_interval=120,
        timeout=60 * 60 * 6,   # 6 horas máximo esperando
        mode="reschedule",
    )
"""

import logging
from airflow.sensors.base import BaseSensorOperator
from airflow.providers.google.common.hooks.base_google import GoogleBaseHook
from googleapiclient.discovery import build

from scripts.config import (
    GDRIVE_CONN_ID,
    GDRIVE_FOLDER_ID,
    GDRIVE_MIME_TYPES_PERMITIDOS,
)

logger = logging.getLogger(__name__)


class GDriveCSVSensor(BaseSensorOperator):
    """
    Sensor que hace poke a una carpeta de Google Drive y retorna True
    cuando encuentra al menos un archivo CSV (no en papelera, tamaño > 0).

    Parámetros
    ----------
    gdrive_conn_id : str
        Connection ID de Airflow con credenciales de Google Cloud.
    folder_id : str
        ID de la carpeta de Drive a vigilar.
    mime_types : list[str]
        Lista de MIME types considerados válidos.
    """

    # Airflow serializa estos atributos para poder re-renderizarlos con Jinja
    template_fields = ("folder_id",)

    def __init__(
        self,
        gdrive_conn_id: str = GDRIVE_CONN_ID,
        folder_id: str = GDRIVE_FOLDER_ID,
        mime_types: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.gdrive_conn_id = gdrive_conn_id
        self.folder_id = folder_id
        self.mime_types = mime_types or GDRIVE_MIME_TYPES_PERMITIDOS

    # ------------------------------------------------------------------
    def poke(self, context) -> bool:
        """
        Lógica ejecutada en cada intervalo de poke.
        Retorna True si hay al menos un CSV válido en la carpeta.
        """
        logger.info(
            f"👁  [GDriveCSVSensor] Revisando carpeta Drive: {self.folder_id}"
        )

        try:
            service = self._get_drive_service()
            archivos = self._listar_csvs(service)
        except Exception as exc:
            # Si la API falla (timeout, credenciales, etc.) logueamos
            # pero NO fallamos el sensor: volvemos a intentar en el próximo poke.
            logger.warning(
                f"⚠️  Error consultando Drive (se reintentará): {exc}"
            )
            return False

        # Filtramos archivos con tamaño 0 (subida incompleta)
        archivos_validos = [
            a for a in archivos if int(a.get("size", 0)) > 0
        ]

        if not archivos_validos:
            logger.info(
                "   No hay archivos CSV válidos todavía. "
                f"(encontrados: {len(archivos)}, con tamaño > 0: {len(archivos_validos)})"
            )
            return False

        # Log informativo de lo que hay
        for a in archivos_validos:
            size_mb = int(a.get("size", 0)) / 1_048_576
            logger.info(
                f"   ✅ Encontrado: '{a['name']}' "
                f"| {size_mb:.2f} MB "
                f"| modificado: {a.get('modifiedTime', 'N/A')}"
            )

        logger.info(
            f"   Total archivos CSV válidos: {len(archivos_validos)}. "
            "Activando pipeline."
        )
        return True

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _get_drive_service(self):
        hook = GoogleBaseHook(gcp_conn_id=self.gdrive_conn_id)
        credentials = hook.get_credentials()
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def _listar_csvs(self, service) -> list[dict]:
        mime_filter = " or ".join(
            f"mimeType='{m}'" for m in self.mime_types
        )
        query = (
            f"'{self.folder_id}' in parents"
            f" and ({mime_filter})"
            f" and trashed=false"
        )
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )
        return response.get("files", [])
