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
