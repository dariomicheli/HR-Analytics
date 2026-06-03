# Nombre del archivo
NOMBRE_ARCHIVO = "hr_raw.csv"

# Rutas de archivos
RUTA_INPUT = '/opt/airflow/data/input/'
RUTA_OUTPUT = '/opt/airflow/data/output/'
RUTA_ARCHIVE = '/opt/airflow/data/archive/'
RUTA_TEMP = '/opt/airflow/data/temp/'

# Conexiones
POSTGRES_DWH_CONN_ID = 'postgres_dwh'

# Columnas de la tabla staging
COLUMNAS_STG: list[str] = [
    "employee_id", "full_name", "department", "job_title", "hire_date",
    "performance_rating", "experience_years", "status", "work_mode",
    "salary", "country", "city", "age", "job_level",
]

# ================================================
# Google Drive
# ================================================
"""
Configuración de Google Drive para el sensor y el descubridor.

Requisitos previos en Airflow:
  1. Instalar: pip install apache-airflow-providers-google
  2. Crear una conexión tipo "Google Cloud" con id GDRIVE_CONN_ID
     (Service Account con rol "Viewer" sobre la carpeta de Drive).
  3. Compartir la carpeta de Drive con el email de la Service Account.

GDRIVE_FOLDER_ID:
  Abrís la carpeta en el navegador → la URL es:
  https://drive.google.com/drive/folders/<FOLDER_ID>
  Copiá ese ID aquí.

GDRIVE_MIME_TYPES_PERMITIDOS:
  Filtra solo archivos CSV nativos.
  Si los archivos vienen como Google Sheets exportados usá:
  "application/vnd.google-apps.spreadsheet"
"""

# ID de la carpeta de Google Drive provisto por el usuario
GDRIVE_FOLDER_ID = "1ii1NciG_5E0CLQa6fmYsn83xtMs3RKeV"

# Nombre exacto del Connection Id en la interfaz de Airflow
GDRIVE_CONN_ID = "google_drive_default"

# Solo queremos CSVs nativos subidos a Drive
GDRIVE_MIME_TYPES_PERMITIDOS: list[str] = [
    "text/csv",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",        # algunos clientes suben .csv con este MIME
]

# Cuántos archivos se permiten en la carpeta como máximo (0 = sin límite)
# Si hay más se loguea un WARNING y se toma el más nuevo.
GDRIVE_MAX_ARCHIVOS_ESPERADOS: int = 1


# ================================================
# Clean_Transform
# ================================================
"""
config.py — constantes globales del pipeline HR
================================================
Centraliza todos los parámetros de negocio y de limpieza para que
cualquier su uso en clean_transform:
    from scripts.config import EDAD_MIN, EDAD_MAX, VALOR_CENTINELA
"""

# ---------------------------------------------------------------------------
# Esquema esperado del CSV crudo
# ---------------------------------------------------------------------------
COLUMNAS_ESPERADAS: list[str] = [
    "Employee_ID", "Full_Name", "Department", "Job_Title", "Hire_Date",
    "Performance_Rating", "Experience_Years", "Status", "Work_Mode",
    "Salary", "Country", "City", "Age", "Job_Level",
]

# ---------------------------------------------------------------------------
# Limpieza de texto
# ---------------------------------------------------------------------------
# Strings que deben interpretarse como nulos al leer el CSV
STRINGS_NULOS: list[str] = ["nan", "None", "none", "NULL", ""]

# Centinela explícito para categóricas sin valor (visible en reportes BI)
VALOR_CENTINELA: str = "not_specified"

# ---------------------------------------------------------------------------
# Rangos válidos para columnas numéricas
# ---------------------------------------------------------------------------
EDAD_MIN: int = 18
EDAD_MAX: int = 75
EXP_MAX: int = 50

# ---------------------------------------------------------------------------
# Base de datos / carga
# ---------------------------------------------------------------------------
# Ajustar según entorno (dev / staging / prod)
DB_SCHEMA: str = "hr"
DB_TABLE:  str = "employees"
