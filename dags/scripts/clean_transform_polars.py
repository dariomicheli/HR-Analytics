from __future__ import annotations
import logging
import logging.handlers
import re
import sys
from datetime import datetime
import polars as pl
import logging

from scripts.config import (
    EDAD_MAX,
    EDAD_MIN,
    EXP_MAX,
    RUTA_TEMP,
    STRINGS_NULOS,
    VALOR_CENTINELA
)

# ===========================================================================
# CONFIGURACIÓN DE LOGGING
# ===========================================================================


def _setup_logger(name: str = __name__, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = _setup_logger(__name__)

# ===========================================================================
# CONSTANTES Y CONFIGURACIÓN MANTENIDAS
# ===========================================================================

_COLS_TITLE_CASE = ["department", "job_title", "country", "city"]
_COLS_CATEGORICAS_FIJAS = ["department", "job_title",
                           "status", "work_mode", "country", "city", "job_level"]

_TITULOS = [
    r"Univ\.Prof\.", r"Prof\.", r"Dra\.", r"Dr\.",
    r"Mrs\.", r"Miss", r"Mr\.", r"Ms\.",
    r"Sra\.", r"Sr\.", r"Doña", r"Don",
    r"Ing\.", r"Lic\.", r"Arq\.", r"Tte\.", r"Gral\.",
]

_GRADOS = [
    r"B\.Sc\.", r"M\.Sc\.", r"Ph\.D\.", r"B\.Eng\.", r"M\.Eng\.",
    r"B\.A\.", r"M\.A\.", r"M\.D\.", r"J\.D\.",
    r"MBA", r"MSc", r"BSc", r"PhD",
]

_TITULOS_RE = re.compile(
    r"^\s*(?:" + "|".join(_TITULOS) + r")\s+", flags=re.IGNORECASE)
_GRADOS_RE = re.compile(
    r"\s+(?:" + "|".join(_GRADOS) + r")\s*$", flags=re.IGNORECASE)

_PARTICULAS = {
    "van", "von", "de", "del", "den", "der",
    "da", "di", "du", "la", "le", "los", "las", "el",
}

# ===========================================================================
# FUNCIONES AUXILIARES - LIMPIEZA DE TEXTO
# ===========================================================================


def _limpiar_nombre_exacto(nombre: str) -> str:
    """
      - Elimina títulos honoríficos y grados académicos
      - Remueve caracteres no deseados
      - Aplica Title Case inteligente (respeta partículas)
    """
    if not nombre or not isinstance(nombre, str):
        return ""

    nombre = nombre.strip()
    # Eliminar títulos honoríficos y grados académicos
    nombre = _TITULOS_RE.sub("", nombre)
    nombre = _GRADOS_RE.sub("", nombre)

    # Remover caracteres especiales (mantener acentos unicode)
    nombre = re.sub(r"[^\w\s\-\.\']", "", nombre, flags=re.UNICODE)

    # Colapsar espacios múltiples
    nombre = re.sub(r"\s+", " ", nombre).strip()

# Aplicar Title Case inteligente
    palabras = nombre.split()
    palabras_limpias = [
        palabra.lower() if i > 0 and palabra.lower() in _PARTICULAS
        else palabra.capitalize()
        for i, palabra in enumerate(palabras)
    ]

    return " ".join(palabras_limpias)

def _to_snake_case(name: str) -> str:
    """
    Estandariza un texto a snake_case imitando el comportamiento de Pandas:
    Elimina caracteres especiales y colapsa múltiples espacios en guiones bajos.
    """
    if not name:
        return ""
    # 1. Quitar espacios en los extremos y pasar a minúsculas
    name = name.strip().lower()
    # 2. Eliminar caracteres que no sean letras, números o espacios (Ej: corregir "salary ($)" -> "salary ")
    name = re.sub(r"[^\w\s]", "", name)
    # 3. Cambiar uno o más espacios seguidos por un único guion bajo (Ej: "job   title" -> "job_title")
    return re.sub(r"\s+", "_", name)

# ===========================================================================
# FUNCIÓN PRINCIPAL DEL PIPELINE
# ===========================================================================


def clean_data(**context) -> str:
    logger.info("╔" + "=" * 68 + "╗")
    logger.info(
        "║" + " INICIANDO PIPELINE: clean_transform (Polars) ".center(68) + "║")
    logger.info("╚" + "=" * 68 + "╝")

    ti = context.get("ti")
    if ti is None:
        raise ValueError("No TaskInstance (ti) en contexto Airflow")

    extract_filepath = ti.xcom_pull(task_ids="extract_csv")

    # 1. Inicio de contexto Lazy 
    q = pl.scan_parquet(extract_filepath)

    # 2. Estandarizar encabezados a snake_case 
    q = q.rename({
            col: _to_snake_case(col) 
            for col in q.collect_schema().names()
        })

    # 3. Validación de clave primaria (employee_id) 
    # Elimino nulos y duplicados, conservo el primero
    q = q.drop_nulls(subset=["employee_id"]).unique(
        subset=["employee_id"], keep="first")

    # 4. Type Casting Blindado (Casteo a String antes de operaciones de cadena)
    q = q.with_columns([
        pl.col("hire_date").cast(pl.String).str.strptime(
            pl.Date, format="%Y-%m-%d", strict=False),
        pl.col("salary").cast(pl.String).str.replace_all(
            r"[^\d.-]", "").cast(pl.Float32, strict=False),
        pl.col("age").cast(pl.Int32, strict=False),
        pl.col("experience_years").cast(pl.Int32, strict=False),
        pl.col(_COLS_CATEGORICAS_FIJAS).cast(
            pl.String).str.to_lowercase().str.strip_chars()
    ])

    # 5. Limpieza inteligente de nombres propios (Uso de map_elements para mantener partículas)
    q = q.with_columns(
        pl.col("full_name").cast(pl.String).map_elements(
            _limpiar_nombre_exacto, return_dtype=pl.String)
    ).filter(pl.col("full_name") != "")

   # 6. Corrección de Rangos Numéricos usando Window Functions (.over)
    q = q.with_columns([
        pl.when(pl.col("salary") >= 0)
          .then(pl.col("salary"))
          .otherwise(None)
          .min().over(["job_level", "department"]).alias("q_min"),

        pl.when(pl.col("salary") >= 0)
          .then(pl.col("salary"))
          .otherwise(None)
          .max().over(["job_level", "department"]).alias("q_max"),

    ]).with_columns([
        pl.when((pl.col("salary") < 0) &
                (pl.col("salary").abs() >= pl.col("q_min")) &
                (pl.col("salary").abs() <= pl.col("q_max")))
          .then(pl.col("salary").abs())
          .when(pl.col("salary") < 0).then(None)
          .otherwise(pl.col("salary")).alias("salary"),

        pl.when((pl.col("age") < EDAD_MIN) | (pl.col("age") > EDAD_MAX))
          .then(None)
          .otherwise(pl.col("age")).alias("age"),

        pl.when(pl.col("experience_years") < 0)
          .then(pl.col("experience_years").abs())
          .when(pl.col("experience_years") > EXP_MAX).then(None)
          .otherwise(pl.col("experience_years")).alias("experience_years")

    ]).drop(["q_min", "q_max"])

    # 7. Imputación de Numéricas y Categorías Fijas por Mediana
    q = q.with_columns([
        pl.col("salary").fill_null(pl.col("salary").median().over(
            ["job_level", "department"])).fill_null(pl.col("salary").median()),

        # Agregamos .round(0).cast(pl.Int32) para evitar que la mediana convierta los enteros a Float
        pl.col("age")
          .fill_null(pl.col("age").median().over(["job_level", "department"]))
          .fill_null(pl.col("age").median())
          .round(0)
          .cast(pl.Int32),

        pl.col("experience_years")
          .fill_null(pl.col("experience_years").median().over(["job_level", "department"]))
          .fill_null(pl.col("experience_years").median())
          .round(0)
          .cast(pl.Int32),

        pl.col(_COLS_CATEGORICAS_FIJAS).fill_null(VALOR_CENTINELA)
    ])

    # -----------------------------------------------------------------------
    # MATERIALIZACIÓN CONTROLADA (Para reportes y lógicas de conteo adaptativo)
    # -----------------------------------------------------------------------
    logger.info("Evaluando el plan Lazy y materializando registros limpios...")
    df = q.collect()
    total_filas = len(df)

    # 8. Tratamiento adaptativo para performance_rating según volumen de nulos
    if "performance_rating" in df.columns:
        df = df.with_columns(pl.col("performance_rating").cast(
            pl.String).str.to_lowercase().str.strip_chars())
        nulos_perf = df["performance_rating"].null_count()

        if nulos_perf > 0:
            pct_nulos = (nulos_perf / total_filas) * 100
            logger.info(
                f"  performance_rating: {nulos_perf:,} nulos detectados ({pct_nulos:.2f}%)")

            if pct_nulos < 1:
                df = df.drop_nulls(subset=["performance_rating"])
            elif pct_nulos < 5:
                df = df.with_columns(
                    pl.col("performance_rating").fill_null(
                        pl.col("performance_rating").drop_nulls().mode(
                        ).first().over(["job_level", "department"])
                    ).fill_null(VALOR_CENTINELA)
                )
            else:
                df = df.with_columns(pl.col("performance_rating").fill_null(
                    f"unknown_{VALOR_CENTINELA}"))

    # 9. Validaciones lógicas cruzadas (Manteniendo tus Logs de advertencia originales)
    inconsistentes = df.filter(
        pl.col("experience_years") > (pl.col("age") - 16)).height
    if inconsistentes > 0:
        logger.warning(
            f"  ⚠️  {inconsistentes:,} registros detectados: experience_years > (age - 16)")

    salario_cero = df.filter(pl.col("salary") == 0).height
    if salario_cero > 0:
        logger.warning(
            f"  ⚠️  {salario_cero:,} registros detectados con salary = 0")

    fecha_futura = df.filter(pl.col("hire_date") >
                             datetime.now().date()).height
    if fecha_futura > 0:
        logger.warning(
            f"  ⚠️  {fecha_futura:,} registros detectados con hire_date en el futuro")

    # 10. Normalización Final a Title Case
    df = df.with_columns([
        pl.col(c).cast(pl.String).str.to_titlecase() for c in _COLS_TITLE_CASE if c in df.columns
    ])

    if "performance_rating" in df.columns:
        df = df.with_columns(pl.col("performance_rating").str.replace_all(
            "_", " ").str.to_titlecase())

    # Guardado físico final
    ruta_destino = f"{RUTA_TEMP}/clean.parquet"
    df.write_parquet(ruta_destino)
    logger.info("=" * 70)
    logger.info("🎯 REPORTE FINAL DEL PIPELINE (POLARS MIGRATION)")
    logger.info("=" * 70)
    logger.info(f"  Registros procesados finales de salida: {len(df):,}")
    logger.info("  Estructura y Tipos de datos en destino:")
    for col, dtype in zip(df.columns, df.dtypes):
        logger.info(f"    - {col}: {dtype}")
    logger.info("=" * 70)

    return ruta_destino
