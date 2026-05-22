import polars as pl
import logging
import re
from scripts.config import RUTA_TEMP, EDAD_MIN, EDAD_MAX, EXP_MAX, VALOR_CENTINELA

logger = logging.getLogger(__name__)

# Constantes de limpieza originales mantenidas intactas
_TITULOS = [r"Univ\.Prof\.", r"Prof\.", r"Dra\.", r"Dr\.", r"Mrs\.", r"Miss", r"Mr\.", r"Ms\.",
            r"Sra\.", r"Sr\.", r"Doña", r"Don", r"Ing\.", r"Lic\.", r"Arq\.", r"Tte\.", r"Gral\."]
_GRADOS = [r"B\.Sc\.", r"M\.Sc\.", r"Ph\.D\.", r"B\.Eng\.", r"M\.Eng\.",
           r"B\.A\.", r"M\.A\.", r"M\.D\.", r"J\.D\.", r"MBA", r"MSc", r"BSc", r"PhD"]
_PARTICULAS = {"van", "von", "de", "del", "den", "der",
               "da", "di", "du", "la", "le", "los", "las", "el"}

_TITULOS_RE = re.compile(
    r"^\s*(?:" + "|".join(_TITULOS) + r")\s+", flags=re.IGNORECASE)
_GRADOS_RE = re.compile(
    r"\s+(?:" + "|".join(_GRADOS) + r")\s*$", flags=re.IGNORECASE)


def _limpiar_nombre_exacto(nombre: str) -> str:
    """Tu función original, mantenida para respetar la lógica de partículas."""
    if not nombre:
        return ""
    nombre = _TITULOS_RE.sub("", nombre)
    nombre = _GRADOS_RE.sub("", nombre)
    nombre = re.sub(r"[^\w\s\-\.\']", "", nombre, flags=re.UNICODE)
    palabras = re.sub(r"\s+", " ", nombre).strip().split()
    return " ".join([p.lower() if i > 0 and p.lower() in _PARTICULAS else p.capitalize() for i, p in enumerate(palabras)])


def clean_data(**context) -> str:
    ti = context.get("ti")
    extract_filepath = ti.xcom_pull(task_ids="extract_csv")

    logger.info("Iniciando pipeline exacto con Polars...")

    # ---------------------------------------------------------
    # 1. EJECUCIÓN LAZY: Limpieza base, casteos y límites
    # ---------------------------------------------------------
    q = pl.scan_parquet(extract_filepath)

    q = (
        q.rename({col: col.strip().lower().replace(" ", "_")
                 for col in q.columns})
        .drop_nulls(subset=["employee_id"])
        .unique(subset=["employee_id"], keep="first")
        .with_columns([
            pl.col("hire_date").str.strptime(
                pl.Date, format="%Y-%m-%d", strict=False),
            pl.col("salary").str.replace_all(
                r"[^\d.-]", "").cast(pl.Float32, strict=False),
            pl.col("age").cast(pl.Int32, strict=False),
            pl.col("experience_years").cast(pl.Int32, strict=False),
            pl.col(["department", "job_title", "status", "work_mode", "country",
                   "city", "job_level"]).str.to_lowercase().str.strip_chars()
        ])
    )

    # Limpieza de nombres aplicando tu función de Python
    q = q.with_columns(
        pl.col("full_name").map_elements(
            _limpiar_nombre_exacto, return_dtype=pl.String)
    ).filter(pl.col("full_name") != "")

    # Limpieza de rangos numéricos igual a Pandas
    q = q.with_columns([
        pl.col("salary").min().over(
            ["job_level", "department"]).alias("q_min"),
        pl.col("salary").max().over(["job_level", "department"]).alias("q_max")
    ]).with_columns([
        pl.when((pl.col("salary") < 0) & (pl.col("salary").abs() >= pl.col(
            "q_min")) & (pl.col("salary").abs() <= pl.col("q_max")))
          .then(pl.col("salary").abs())
          .when(pl.col("salary") < 0).then(None)
          .otherwise(pl.col("salary")).alias("salary"),
        pl.when((pl.col("age") < EDAD_MIN) | (pl.col("age") > EDAD_MAX)).then(
            None).otherwise(pl.col("age")).alias("age"),
        pl.when(pl.col("experience_years") < 0).then(
            pl.col("experience_years").abs())
          .when(pl.col("experience_years") > EXP_MAX).then(None).otherwise(pl.col("experience_years")).alias("experience_years")
    ]).drop(["q_min", "q_max"])

    # Imputación de Numéricas y Categóricas Fijas
    q = q.with_columns([
        pl.col("salary").fill_null(pl.col("salary").median().over(
            ["job_level", "department"])).fill_null(pl.col("salary").median()),
        pl.col("age").fill_null(pl.col("age").median().over(
            ["job_level", "department"])).fill_null(pl.col("age").median()),
        pl.col("experience_years").fill_null(pl.col("experience_years").median().over(
            ["job_level", "department"])).fill_null(pl.col("experience_years").median()),
        pl.col(["department", "job_title", "status", "work_mode",
               "country", "city", "job_level"]).fill_null(VALOR_CENTINELA)
    ])

    # ---------------------------------------------------------
    # 2. MATERIALIZACIÓN PARA LOGS Y LÓGICA ADAPTATIVA
    # ---------------------------------------------------------
    # Ejecutamos el plan. Como Polars es súper eficiente, esto ocupa poca RAM
    df = q.collect()
    total_filas = len(df)

    # Lógica Adaptativa de performance_rating
    if "performance_rating" in df.columns:
        nulos_perf = df["performance_rating"].null_count()
        if nulos_perf > 0:
            pct_nulos = (nulos_perf / total_filas) * 100
            if pct_nulos < 1:
                df = df.drop_nulls(subset=["performance_rating"])
            elif pct_nulos < 5:
                # Imputar por moda de grupo
                df = df.with_columns(
                    pl.col("performance_rating").fill_null(
                        pl.col("performance_rating").drop_nulls().mode(
                        ).first().over(["job_level", "department"])
                    ).fill_null(VALOR_CENTINELA)
                )
            else:
                df = df.with_columns(pl.col("performance_rating").fill_null(
                    f"unknown_{VALOR_CENTINELA}"))

    # Validaciones cruzadas (Logs)
    inconsistentes = df.filter(
        pl.col("experience_years") > (pl.col("age") - 16)).height
    if inconsistentes > 0:
        logger.warning(
            f"⚠️ {inconsistentes:,} registros: experience_years > (age - 16)")

    salario_cero = df.filter(pl.col("salary") == 0).height
    if salario_cero > 0:
        logger.warning(f"⚠️ {salario_cero:,} registros con salary = 0")

    # ---------------------------------------------------------
    # 3. NORMALIZACIÓN FINAL Y GUARDADO
    # ---------------------------------------------------------
    cols_title = ["department", "job_title", "country", "city"]
    df = df.with_columns([
        pl.col(c).str.to_titlecase() for c in cols_title if c in df.columns
    ])

    if "performance_rating" in df.columns:
        df = df.with_columns(pl.col("performance_rating").str.replace_all(
            "_", " ").str.to_titlecase())

    ruta_destino = f"{RUTA_TEMP}/clean.parquet"
    df.write_parquet(ruta_destino)

    logger.info(
        "✅ Pipeline completado respetando 100% de las reglas originales.")
    return ruta_destino
