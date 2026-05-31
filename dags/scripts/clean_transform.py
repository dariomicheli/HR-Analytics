from __future__ import annotations
import logging
import sys
import time
from datetime import datetime, timedelta
import polars as pl

from scripts.config import (
    EDAD_MAX,
    EDAD_MIN,
    EXP_MAX,
    RUTA_TEMP,
    STRINGS_NULOS,
    VALOR_CENTINELA
)

# ===========================================================================
# CONFIGURACIÓN Y CONSTANTES
# ===========================================================================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


# 1. Constantes globales de negocio
_PARTICULAS = {"van", "von", "de", "del", "den", "der", "da", "di", "du", "la", "le", "los", "las", "el"}
_TITULOS = [r"Univ\.Prof\.", r"Prof\.", r"Dra\.", r"Dr\.", r"Mrs\.", r"Miss", r"Mr\.", r"Ms\.", r"Sra\.", r"Sr\.", r"Doña", r"Don", r"Ing\.", r"Lic\.", r"Arq\.", r"Tte\.", r"Gral\."]
_GRADOS = [r"B\.Sc\.", r"M\.Sc\.", r"Ph\.D\.", r"B\.Eng\.", r"M\.Eng\.", r"B\.A\.", r"M\.A\.", r"M\.D\.", r"J\.D\.", r"MBA", r"MSc", r"BSc", r"PhD"]

_PATRON_TITULOS = r"(?i)^\s*(?:" + "|".join(_TITULOS) + r")\s+"
_PATRON_GRADOS  = r"(?i)\s+(?:" + "|".join(_GRADOS)  + r")\s*$"

# Constantes de negocio
FECHA_DATASET         = datetime(2026, 3, 25).date()
EDAD_MINIMA_LABORAL   = 18
FECHA_SOSPECHOSA      = datetime(1950, 1, 1).date()

# Columnas del dataset
_COLS_CATEGORICAS_FIJAS = [
    "department", "job_title", "status", "work_mode",
    "country", "city", "job_level",
]

_COLS_CATEGORICAS_EXTRA = ["performance_rating"]

_COLS_TITLE_CASE = ["department", "job_title", "country", "city"]
_COLS_NUMERICAS  = ["salary", "age", "experience_years"]


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================

def _aplicar_title_case_inteligente(nombre: str | None) -> str:
    """Aplica el formateo de mayúsculas sobre texto que YA está completamente limpio."""
    if not nombre:
        return ""
    palabras = nombre.split()
    palabras_limpias = [
        palabra.lower() if i > 0 and palabra.lower() in _PARTICULAS
        else palabra.capitalize()
        for i, palabra in enumerate(palabras)
    ]
    return " ".join(palabras_limpias)


def _auditar_nulos(df: pl.DataFrame, etapa: str) -> dict[str, int]:
    """
    Audita nulos remanentes.
    Devuelve el dict {col: n_nulos} para que el caller pueda decidir qué loguear.
    Sin collect() extra – opera sobre el DataFrame ya materializado.
    """
    logger.info(f"📋 Auditoría [{etapa}]:")
    resultado: dict[str, int] = {}
    hay_nulos = False
    for col in df.columns:
        nulos = df[col].null_count()
        if nulos > 0:
            pct = (nulos / len(df)) * 100
            logger.warning(f"  ⚠️  {col}: {nulos:,} nulos ({pct:.4f}%)")
            resultado[col] = nulos
            hay_nulos = True
    if not hay_nulos:
        logger.info("  ✅ Sin nulos")
    return resultado


def _nulos_a_null_polars(s: pl.Expr) -> pl.Expr:
    """
    reemplaza representaciones-string de nulo por null real de Polars.

    """
    return (
        pl.when(s.str.to_lowercase().str.strip_chars().is_in(set(STRINGS_NULOS)))
        .then(None)
        .otherwise(s)
    )


def _timer_etapa(nombre: str, n_inicio: int | None = None):
    """Context-manager liviano que loguea el tiempo de cada etapa."""
    class _T:
        def __init__(self):
            self.t0 = time.perf_counter()
        def __enter__(self):
            return self
        def __exit__(self, *_):
            dur = time.perf_counter() - self.t0
            extra = f" | {n_inicio:,} filas entrada" if n_inicio is not None else ""
            logger.info(f"  ⏱  {nombre} completado en {dur:.3f}s{extra}")
    return _T()


# ===========================================================================
# ETAPAS DEL PIPELINE
# ===========================================================================

def _etapa_1_limpieza_basica(q: pl.LazyFrame) -> pl.LazyFrame:
    """ETAPA 1: Normalización de encabezados a snake_case"""
    logger.info("▶️  ETAPA 1: Limpieza Básica")
    import re

    nuevos_nombres = {}
    for col in q.collect_schema().names():
        nombre_limpio = col.strip().lower()
        nombre_limpio = re.sub(r'[^\w\s]', '', nombre_limpio)
        nombre_limpio = re.sub(r'\s+', '_', nombre_limpio)
        nuevos_nombres[col] = nombre_limpio

    return q.rename(nuevos_nombres)


def _etapa_2_validacion_pk(q: pl.LazyFrame) -> pl.LazyFrame:
    """ETAPA 2: Validación de Primary Key (employee_id)"""
    logger.info("▶️  ETAPA 2: Validación de Clave Primaria")
    return (
        q.drop_nulls(subset=["employee_id"])
         .unique(subset=["employee_id"], keep="first", maintain_order=True)

    )


def _etapa_3_type_casting(q: pl.LazyFrame) -> pl.LazyFrame:
    """ETAPA 3: Conversión de tipos de datos + aplicación de STRINGS_NULOS"""
    logger.info("▶️  ETAPA 3: Type Casting")

    schema = q.collect_schema()
    exprs  = []

    # Fechas
    if "hire_date" in schema:
        exprs.append(
            pl.col("hire_date")
            .cast(pl.String)
            .str.strptime(pl.Date, format="%Y-%m-%d", strict=False)
        )

    # Numéricos enteros
    for col in ["age", "experience_years", "year"]:
        if col in schema:
            exprs.append(pl.col(col).cast(pl.Int32, strict=False))

    # Salary

    if "salary" in schema:
        exprs.append(
            pl.col("salary")
            .cast(pl.String)
            .str.replace_all(",", "")
            .str.replace_all(r"[^\d.\-]", "")   # \- escapado → solo el guion literal
            .cast(pl.Float32, strict=False)
            .alias("salary")
        )

    # Categorías fijas
    cols_cat = [c for c in _COLS_CATEGORICAS_FIJAS if c in schema]
    if cols_cat:
        base = (
            pl.col(cols_cat)
            .cast(pl.String)
            .str.strip_chars()
            .str.replace_all(r"\s+", " ")
            .str.to_lowercase()
        )
        exprs.append(base)


    if "performance_rating" in schema:
        pr_limpio = (
            pl.col("performance_rating")
            .cast(pl.String)
            .str.strip_chars()
            .str.replace_all(r"\s+", " ")
            .str.to_lowercase()
        )
        # Reemplazar representaciones-string de nulo por null real
        exprs.append(
            _nulos_a_null_polars(pr_limpio).alias("performance_rating")
        )

    if exprs:
        q = q.with_columns(exprs)

    return q


def _etapa_4_limpieza_nombres(q: pl.LazyFrame) -> pl.LazyFrame:
    """ETAPA 4: Limpieza de nombres optimizada y nativa en Polars"""
    logger.info("▶️  ETAPA 4: Limpieza de Nombres (Versión Corporativa)")

    if "full_name" in q.collect_schema().names():
        q = q.with_columns(
            pl.col("full_name")
              .cast(pl.String)
              .str.strip_chars()
              .str.replace_all(_PATRON_TITULOS, "", literal=False)
              .str.replace_all(_PATRON_GRADOS,  "", literal=False)
              .str.replace_all(r"[^\w\s\-\.\']", "", literal=False)
              .str.replace_all(r"\s+", " ", literal=False)
              .str.strip_chars()
        )

        q = q.with_columns(
            pl.col("full_name").map_elements(
                _aplicar_title_case_inteligente, return_dtype=pl.String
            )
        )

        q = q.filter(
            pl.col("full_name").is_not_null() & (pl.col("full_name").str.len_chars() > 0)
        )

    return q


def _etapa_5_correccion_rangos(q: pl.LazyFrame) -> pl.LazyFrame:
    """ETAPA 5: Corrección de rangos numéricos"""
    logger.info("▶️  ETAPA 5: Corrección de Rangos")

    columnas_disponibles = q.collect_schema().names()
    cols_grupo = [c for c in ["job_level", "department"] if c in columnas_disponibles]

    if cols_grupo:
        salarios_validos = pl.when(pl.col("salary") >= 0).then(pl.col("salary")).otherwise(None)
        q_min = salarios_validos.min().over(cols_grupo)
        q_max = salarios_validos.max().over(cols_grupo)

        expr_salary = (
            pl.when((pl.col("salary") < 0) & (pl.col("salary").abs() >= q_min) & (pl.col("salary").abs() <= q_max))
            .then(pl.col("salary").abs())
            .when(pl.col("salary") < 0)
            .then(None)
            .otherwise(pl.col("salary"))
            .alias("salary")
        )
    else:
        expr_salary = (
            pl.when(pl.col("salary") < 0)
            .then(None)
            .otherwise(pl.col("salary"))
            .alias("salary")
        )

    q = q.with_columns([
        expr_salary,
        pl.when((pl.col("age") < EDAD_MIN) | (pl.col("age") > EDAD_MAX))
        .then(None)
        .otherwise(pl.col("age"))
        .alias("age"),
        pl.col("experience_years").abs().alias("experience_years"),
    ]).with_columns([
        pl.when(pl.col("experience_years") > EXP_MAX)
        .then(None)
        .otherwise(pl.col("experience_years"))
        .alias("experience_years"),
    ])

    return q


def _etapa_6_validacion_cruzada(q: pl.LazyFrame) -> pl.LazyFrame:
    """ETAPA 6: Validaciones lógicas cruzadas"""
    logger.info("▶️  ETAPA 6: Validación Cruzada")

    # Experience no puede superar age - 17.
    # Si age es null la condición evalúa null → se conserva el valor original. ✅
    q = q.with_columns(
        pl.when(pl.col("experience_years") > (pl.col("age") - 16))
        .then(pl.col("age") - 17)
        .otherwise(pl.col("experience_years"))
        .alias("experience_years")
    )

    fecha_hoy = pl.lit(FECHA_DATASET)
    q = q.with_columns(
        pl.when(pl.col("hire_date") > fecha_hoy)
        .then(None)
        .otherwise(pl.col("hire_date"))
        .alias("hire_date")
    )

    return q


def _etapa_7_imputacion_nulos(q: pl.LazyFrame) -> pl.LazyFrame:
    """
    ETAPA 7: Imputación de nulos de age y experience_years.

    NOTA: salary ya NO se imputa aquí. El orden correcto es:
      1. Etapa 9A (eager) → reemplaza salary == 0 por mediana de grupo
      2. Etapa 9B (eager) → nullifica outliers IQR por grupo
      3. Etapa 9C (eager) → imputa los nulos resultantes (ceros + outliers + originales)
    Esto garantiza que la mediana de grupo usada para imputar no esté
    contaminada ni por ceros ni por outliers.
    """
    logger.info("▶️  ETAPA 7: Imputación de Nulos (age · experience_years · categorías)")

    q = q.with_columns([
        # salary: se deja para las etapas eager 9A/9B/9C
        pl.col("age")
          .fill_null(pl.col("age").median().over(["job_level", "department"])),
        pl.col("experience_years")
          .fill_null(pl.col("experience_years").median().over(["job_level", "department"])),
        pl.col(_COLS_CATEGORICAS_FIJAS).fill_null(VALOR_CENTINELA),
        # performance_rating NO recibe centinela aquí; su lógica adaptativa
        # es responsabilidad exclusiva de etapa 10.
    ]).with_columns([
        # Fallback global para grupos sin ningún valor válido
        pl.col("age")
          .fill_null(pl.col("age").median()).round(0).cast(pl.Int32),
        pl.col("experience_years")
          .fill_null(pl.col("experience_years").median()).round(0).cast(pl.Int32),
    ])

    # hire_date: imputación determinística diferida a etapa 8 (necesita
    # materialización eager para operar con medianas de grupo por fecha).

    return q

def _etapa_8_correccion_edad_minima_laboral(df: pl.DataFrame) -> pl.DataFrame:
    """
    ETAPA 8: Corrección de hire_date + imputación de nulos de hire_date.

    Sub-etapas:
      8A. Imputación de hire_date nula usando la mediana del grupo (job_level × department).
          Fallback: mediana global. Tipo de salida garantizado: pl.Date.
      8B. Ajuste de hire_date en activos cuya edad_al_contratar < EDAD_MINIMA_LABORAL.
      8C. Log de fechas sospechosas (< 1950) para auditoría.
    """
    logger.info("▶️  ETAPA 8: Imputación hire_date + Corrección Edad Mínima Laboral")
    fecha_dataset_lit = pl.lit(FECHA_DATASET).cast(pl.Date)

    # ── 8A: Imputar hire_date nula ──────────────────────────────────────────
    nulos_hire = df["hire_date"].null_count()
    if nulos_hire > 0:
        logger.warning(f"  ⚠️  8A: {nulos_hire:,} hire_date nulas → imputando por mediana de grupo")

        # Convertimos la fecha a días-desde-epoch (Int32) para poder calcular
        # medianas numéricas con Polars sin romper el tipo Date.
        df = df.with_columns(
            pl.col("hire_date").cast(pl.Int32).alias("_hire_epoch")
        )

        # Mediana de grupo en días-epoch
        mediana_grupo_epoch = (
            df.group_by(["job_level", "department"])
              .agg(
                  pl.col("_hire_epoch").drop_nulls().median()
                    .round(0).cast(pl.Int32).alias("_hire_epoch_grupo")
              )
        )

        # Mediana global como fallback
        mediana_global_epoch = int(
            df["_hire_epoch"].drop_nulls().median() or 0
        )

        df = (
            df.join(mediana_grupo_epoch, on=["job_level", "department"], how="left")
              .with_columns(
                  pl.col("_hire_epoch")
                    .fill_null(pl.col("_hire_epoch_grupo"))
                    .fill_null(mediana_global_epoch)
                    .cast(pl.Int32)
                    .alias("_hire_epoch")
              )
              .drop("_hire_epoch_grupo")
        )

        # Reconstruir columna hire_date desde epoch → pl.Date
        df = df.with_columns(
            pl.col("_hire_epoch").cast(pl.Date).alias("hire_date")
        ).drop("_hire_epoch")

        nulos_post = df["hire_date"].null_count()
        logger.info(
            f"  ✅ 8A: hire_date nulas tras imputación: {nulos_post:,} "
            f"(mediana global epoch={mediana_global_epoch})"
        )
    else:
        logger.info("  ✅ 8A: Sin nulos en hire_date – imputación omitida")

    # ── 8B: Ajuste por edad mínima laboral (solo activos) ──────────────────
    es_activo_con_datos = (
        (pl.col("status") == "active") &
        (pl.col("hire_date").is_not_null()) &
        (pl.col("age").is_not_null())
    )

    df = df.with_columns(
        pl.when(es_activo_con_datos)
          .then(
              pl.col("age")
              - ((fecha_dataset_lit - pl.col("hire_date")).dt.total_days() / 365.25)
          )
          .otherwise(None)
          .alias("edad_al_contratar")
    )

    edad_negativa = df.filter(pl.col("edad_al_contratar") < 0).height
    edad_menor_18 = df.filter(
        pl.col("edad_al_contratar").is_not_null() &
        (pl.col("edad_al_contratar") >= 0) &
        (pl.col("edad_al_contratar") < EDAD_MINIMA_LABORAL)
    ).height

    if edad_negativa > 0:
        logger.warning(f"  ⚠️  8B: {edad_negativa:,} activos con edad_al_contratar < 0 (hire_date futura)")

    if edad_menor_18 > 0:
        logger.warning(
            f"  ⚠️  8B: {edad_menor_18:,} activos contratados con < {EDAD_MINIMA_LABORAL} años "
            "→ ajustando hire_date"
        )
        años_faltantes = EDAD_MINIMA_LABORAL - pl.col("edad_al_contratar")
        df = df.with_columns(
            pl.when(
                pl.col("edad_al_contratar").is_not_null() &
                (pl.col("edad_al_contratar") < EDAD_MINIMA_LABORAL) &
                (pl.col("edad_al_contratar") >= 0)
            )
            .then(
                pl.col("hire_date")
                + pl.duration(days=(años_faltantes * 365.25).cast(pl.Int32))
            )
            .otherwise(pl.col("hire_date"))
            .cast(pl.Date)          # garantiza que no mute a Object
            .alias("hire_date")
        )
    else:
        logger.info("  ✅ 8B: Sin hire_dates a corregir por edad mínima")

    # ── 8C: Auditoría de fechas sospechosas ────────────────────────────────
    fecha_sospechosa_count = df.filter(
        (pl.col("status") == "active") &
        (pl.col("hire_date").is_not_null()) &
        (pl.col("hire_date") < pl.lit(FECHA_SOSPECHOSA).cast(pl.Date))
    ).height

    if fecha_sospechosa_count > 0:
        logger.warning(
            f"  ⚠️  8C: {fecha_sospechosa_count:,} hire_date ACTIVAS < {FECHA_SOSPECHOSA} → "
            "revisar origen de datos"
        )
    else:
        logger.info("  ✅ 8C: Sin hire_date sospechosas")

    return df.drop("edad_al_contratar")

def _etapa_9_salary_pipeline(df: pl.DataFrame) -> pl.DataFrame:
    """
    ETAPA 9: Pipeline completo de saneamiento de salary en tres sub-etapas ordenadas.

    Orden crítico de negocio:
      9A. Reemplazar salary == 0 → mediana del grupo (excluyendo ceros y nulos).
          Esto evita que los ceros contaminen el IQR del paso siguiente.
      9B. Nullificar outliers IQR por grupo (job_level × department).
          Los valores fuera de [Q1 - 1.5·IQR, Q3 + 1.5·IQR] pasan a None
          para ser imputados limpiamente en 9C.
      9C. Imputar todos los nulos de salary (originales + generados en 9A/9B)
          usando la mediana del grupo. Fallback: mediana global.
    """
    logger.info("▶️  ETAPA 9: Pipeline Salary (9A: ceros → 9B: outliers IQR → 9C: imputación)")

    # ── 9A: Corrección de ceros ────────────────────────────────────────────
    salarios_cero = df.filter(pl.col("salary") == 0).height

    if salarios_cero > 0:
        logger.warning(f"  ⚠️  9A: {salarios_cero:,} salarios == 0 → imputando por mediana de grupo (excl. ceros)")

        mediana_global_no_cero = (
            df.filter(pl.col("salary") > 0)["salary"].median()
        )

        mediana_grupo_no_cero = (
            df.group_by(["job_level", "department"])
              .agg(
                  pl.col("salary")
                    .filter(pl.col("salary") > 0)
                    .median()
                    .alias("_sal_med_grupo")
              )
        )

        df = (
            df.join(mediana_grupo_no_cero, on=["job_level", "department"], how="left")
              .with_columns(
                  pl.when(pl.col("salary") == 0)
                    .then(
                        pl.col("_sal_med_grupo")
                          .fill_null(pl.lit(mediana_global_no_cero))
                    )
                    .otherwise(pl.col("salary"))
                    .alias("salary")
              )
              .drop("_sal_med_grupo")
        )

        ceros_post = df.filter(pl.col("salary") == 0).height
        logger.info(
            f"  ✅ 9A: ceros restantes: {ceros_post:,} "
            f"| mediana global de referencia: ${mediana_global_no_cero:,.2f}"
        )
    else:
        logger.info("  ✅ 9A: Sin salarios == 0")

    # ── 9B: Nullificación de outliers IQR por grupo ───────────────────────
    logger.info("  🔍 9B: Calculando outliers IQR por grupo (job_level × department)")

    stats_grupo = (
        df.group_by(["job_level", "department"])
          .agg([
              pl.col("salary").quantile(0.25).alias("_q1"),
              pl.col("salary").quantile(0.75).alias("_q3"),
          ])
          .with_columns([
              (pl.col("_q3") - pl.col("_q1")).alias("_iqr"),
          ])
          .with_columns([
              (pl.col("_q1") - 1.5 * pl.col("_iqr")).alias("_lim_inf"),
              (pl.col("_q3") + 1.5 * pl.col("_iqr")).alias("_lim_sup"),
          ])
          .select(["job_level", "department", "_lim_inf", "_lim_sup"])
    )

    df = df.join(stats_grupo, on=["job_level", "department"], how="left")

    outliers_count = df.filter(
        pl.col("salary").is_not_null() &
        (
            (pl.col("salary") < pl.col("_lim_inf")) |
            (pl.col("salary") > pl.col("_lim_sup"))
        )
    ).height

    df = df.with_columns(
        pl.when(
            pl.col("salary").is_not_null() &
            (
                (pl.col("salary") < pl.col("_lim_inf")) |
                (pl.col("salary") > pl.col("_lim_sup"))
            )
        )
        .then(None)          # → pasa a nulo para imputar limpiamente en 9C
        .otherwise(pl.col("salary"))
        .alias("salary")
    ).drop(["_lim_inf", "_lim_sup"])

    pct_out = (outliers_count / len(df)) * 100 if len(df) > 0 else 0.0
    logger.warning(
        f"  ⚠️  9B: {outliers_count:,} outliers ({pct_out:.4f}%) nullificados por IQR de grupo"
    ) if outliers_count > 0 else logger.info("  ✅ 9B: Sin outliers IQR detectados")

    # ── 9C: Imputación final de todos los nulos de salary ─────────────────
    nulos_salary = df["salary"].null_count()
    logger.info(f"  🔧 9C: {nulos_salary:,} nulos de salary a imputar (originales + 9A + 9B)")

    if nulos_salary > 0:
        mediana_global = df.filter(pl.col("salary").is_not_null())["salary"].median()

        mediana_grupo_final = (
            df.group_by(["job_level", "department"])
              .agg(
                  pl.col("salary").drop_nulls().median().alias("_sal_med_final")
              )
        )

        df = (
            df.join(mediana_grupo_final, on=["job_level", "department"], how="left")
              .with_columns(
                  pl.col("salary")
                    .fill_null(pl.col("_sal_med_final"))
                    .fill_null(pl.lit(mediana_global))
                    .alias("salary")
              )
              .drop("_sal_med_final")
        )

        nulos_post_9c = df["salary"].null_count()
        logger.info(
            f"  ✅ 9C: nulos restantes: {nulos_post_9c:,} "
            f"| mediana global fallback: ${mediana_global:,.2f}"
        )

        # Auditoría IQR post-imputación (solo informativa, sin modificar datos)
        q1  = df["salary"].quantile(0.25)
        q3  = df["salary"].quantile(0.75)
        iqr = q3 - q1
        logger.info(
            f"  📊 9C post-IQR info: Q1=${q1:,.0f} | Q3=${q3:,.0f} | "
            f"rango limpio=[${q1 - 1.5*iqr:,.0f} – ${q3 + 1.5*iqr:,.0f}]"
        )
    else:
        logger.info("  ✅ 9C: Sin nulos de salary – imputación omitida")

    return df


def _etapa_10_performance_rating_adaptativo(df: pl.DataFrame) -> pl.DataFrame:
    """
    ETAPA 10: Tratamiento adaptativo de performance_rating.

    """
    logger.info("▶️  ETAPA 10: Imputación Adaptativa de Performance_Rating")

    if "performance_rating" not in df.columns:
        return df

    # Segunda línea de defensa: normalizar y re-aplicar STRINGS_NULOS
    # sobre cualquier residuo que etapa 3 no haya visto.
    df = df.with_columns(
        pl.when(
            pl.col("performance_rating")
              .cast(pl.String)
              .str.to_lowercase()
              .str.strip_chars()
              .is_in(set(STRINGS_NULOS) | {""})
        )
        .then(None)
        .otherwise(pl.col("performance_rating").cast(pl.String).str.to_lowercase().str.strip_chars())
        .alias("performance_rating")
    )

    nulos_perf = df["performance_rating"].null_count()
    total      = len(df)

    if nulos_perf == 0:
        logger.info("  ✅ Sin nulos en performance_rating")
        return df

    pct_nulos = (nulos_perf / total) * 100
    logger.info(f"  performance_rating: {nulos_perf:,} nulos ({pct_nulos:.4f}%)")

    if pct_nulos < 0.5:
        logger.info(f"    → < 0.5%: eliminando {nulos_perf:,} filas")
        df = df.drop_nulls(subset=["performance_rating"])

    elif pct_nulos < 3:
        logger.info(f"    → 0.5–3%: imputando por moda de grupo (job_level × department)")

        perf_moda = (
            df.group_by(["job_level", "department"])
              .agg(
                  pl.col("performance_rating")
                    .drop_nulls()
                    .mode()
                    .first()
                    .alias("perf_mode")
              )
        )

        df = (
            df.join(perf_moda, on=["job_level", "department"], how="left")
              .with_columns(
                  pl.col("performance_rating")
                    .fill_null(pl.col("perf_mode"))
                    .fill_null(VALOR_CENTINELA)
              )
              .drop("perf_mode")
        )

    else:
        logger.error(f"    ❌ ≥ 3%: DEMASIADOS NULOS ({pct_nulos:.2f}%)")
        logger.error("    → ACCIÓN REQUERIDA: Revisar proceso de extracción de performance_rating")
        df = df.with_columns(
            pl.col("performance_rating").fill_null(f"unknown_{VALOR_CENTINELA}")
        )

    return df


def _etapa_11_normalizacion_final(df: pl.DataFrame) -> pl.DataFrame:
    """ETAPA 11: Normalización estética final (Title Case)"""
    logger.info("▶️  ETAPA 11: Normalización Final")

    for col in _COLS_TITLE_CASE:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.String).str.to_titlecase())

    if "performance_rating" in df.columns:
        df = df.with_columns(
            pl.col("performance_rating")
              .str.replace_all("_", " ")
              .str.to_titlecase()
        )

    return df


def _etapa_12_experience_activos(df: pl.DataFrame) -> pl.DataFrame:
    """
    ETAPA 12: Reglas de negocio de experience_years para empleados ACTIVOS.

    Regla A – Corrección de antigüedad real:
      Si experience_years == 0 O es menor a los años reales transcurridos
      desde hire_date hasta FECHA_DATASET, se reemplaza por la antigüedad
      calculada (años_reales). Si el grupo (job_level × department) tiene
      una mediana mayor aún, se usa esa como piso.

    Regla B – Forzar actualización cuando experience original < años reales:
      Para cualquier activo donde la experiencia registrada sea inferior a
      la antigüedad efectiva en la empresa, se fuerza el valor calculado.

    Solo afecta filas con status == 'active'.
    Empleados inactivos/terminated no se modifican.
    """
    logger.info("▶️  ETAPA 12: Corrección de experience_years para Empleados Activos")

    if "hire_date" not in df.columns or "experience_years" not in df.columns:
        logger.warning("  ⚠️  Columnas hire_date o experience_years ausentes – etapa omitida")
        return df

    fecha_dataset_lit = pl.lit(FECHA_DATASET).cast(pl.Date)

    # Calcular antigüedad real en años para todos los activos con hire_date válida
    df = df.with_columns(
        pl.when(
            (pl.col("status") == "active") &
            pl.col("hire_date").is_not_null()
        )
        .then(
            ((fecha_dataset_lit - pl.col("hire_date")).dt.total_days() / 365.25)
            .round(2)
        )
        .otherwise(None)
        .cast(pl.Float64)
        .alias("_antiguedad_real")
    )

    # Mediana de experience_years por grupo para activos (usado como piso de referencia)
    med_exp_grupo = (
        df.filter(pl.col("status") == "active")
          .group_by(["job_level", "department"])
          .agg(
              pl.col("experience_years")
                .drop_nulls()
                .median()
                .alias("_med_exp_grupo")
          )
    )

    df = df.join(med_exp_grupo, on=["job_level", "department"], how="left")

    # ── Regla A: experience_years == 0 ────────────────────────────────────
    # Aplicable solo a activos con antigüedad real calculable.
    cond_regla_a = (
        (pl.col("status") == "active") &
        pl.col("_antiguedad_real").is_not_null() &
        (pl.col("experience_years") == 0)
    )

    # El valor correcto es el máximo entre la antigüedad real y la mediana del grupo
    valor_regla_a = (
        pl.max_horizontal(
            pl.col("_antiguedad_real"),
            pl.col("_med_exp_grupo").fill_null(pl.col("_antiguedad_real"))
        )
        .round(0)
        .cast(pl.Int32)
    )

    n_regla_a = df.filter(cond_regla_a).height
    if n_regla_a > 0:
        logger.warning(
            f"  ⚠️  12A: {n_regla_a:,} activos con experience_years == 0 "
            "→ corrigiendo con antigüedad real (o mediana de grupo si mayor)"
        )
    else:
        logger.info("  ✅ 12A: Sin activos con experience_years == 0")

    df = df.with_columns(
        pl.when(cond_regla_a)
          .then(valor_regla_a)
          .otherwise(pl.col("experience_years"))
          .alias("experience_years")
    )

    # ── Regla B: experience_years < antigüedad real (post-corrección 12A) ─
    # Si el valor registrado es menor que los años que el empleado lleva
    # en la empresa, se fuerza la antigüedad real como valor mínimo.
    cond_regla_b = (
        (pl.col("status") == "active") &
        pl.col("_antiguedad_real").is_not_null() &
        (pl.col("experience_years").cast(pl.Float64) < pl.col("_antiguedad_real"))
    )

    n_regla_b = df.filter(cond_regla_b).height
    if n_regla_b > 0:
        logger.warning(
            f"  ⚠️  12B: {n_regla_b:,} activos con experience_years < antigüedad real "
            "→ actualizando al valor de antigüedad"
        )
    else:
        logger.info("  ✅ 12B: Sin activos con experience_years inferior a la antigüedad")

    df = df.with_columns(
        pl.when(cond_regla_b)
          .then(pl.col("_antiguedad_real").round(0).cast(pl.Int32))
          .otherwise(pl.col("experience_years"))
          .alias("experience_years")
    )

    # ── Limpieza de columnas auxiliares ───────────────────────────────────
    df = df.drop(["_antiguedad_real", "_med_exp_grupo"])

    # ── Auditoría post-etapa ───────────────────────────────────────────────
    total_activos = df.filter(pl.col("status") == "active").height
    afectados = n_regla_a + n_regla_b
    logger.info(
        f"  📊 12 resumen: {afectados:,} / {total_activos:,} activos corregidos "
        f"(12A={n_regla_a:,}, 12B={n_regla_b:,})"
    )

    return df



    """ETAPA 11: Normalización estética final (Title Case)"""
    logger.info("▶️  ETAPA 11: Normalización Final")

    for col in _COLS_TITLE_CASE:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.String).str.to_titlecase())

    if "performance_rating" in df.columns:
        df = df.with_columns(
            pl.col("performance_rating")
              .str.replace_all("_", " ")
              .str.to_titlecase()
        )

    return df


# ===========================================================================
# FUNCIÓN PRINCIPAL PARA AIRFLOW
# ===========================================================================

def clean_data(**context) -> str:
    """
    Pipeline completo de limpieza y transformación de datos HR en Polars.

    ORDEN DE ETAPAS
    ───────────────
    Lazy  (1-7):  snake_case → PK → tipos → nombres → rangos → validación cruzada
                  → imputación age/exp (salary diferido a eager)
    Eager (8-12+):
      8   hire_date: imputación por mediana de grupo + corrección edad mínima laboral
      9   salary pipeline: 9A ceros → 9B outliers IQR (→ None) → 9C imputación
      10  performance_rating adaptativo
      12  experience_years para activos (Regla A: ceros, Regla B: < antigüedad)
      11  normalización estética final (Title Case)
    """

    t_pipeline = time.perf_counter()

    logger.info("╔" + "=" * 68 + "╗")
    logger.info("║" + " PIPELINE: clean_transform ".center(68) + "║")
    logger.info("║" + " 12 ETAPAS + REGLAS DE NEGOCIO ".center(68) + "║")
    logger.info("╚" + "=" * 68 + "╝")

    ti = context.get("ti")
    if ti is None:
        raise ValueError("❌ No TaskInstance (ti) en contexto Airflow")

    extract_filepath = ti.xcom_pull(task_ids="extract_csv")

    # ── Carga perezosa ─────────────────────────────────────────────────────
    q = pl.scan_parquet(extract_filepath)
    n_original = q.select(pl.len()).collect()[0, 0]
    logger.info(f"\n📊 Filas en dataset entrada: {n_original:,}")

    # ── Etapas lazy (1-7) ──────────────────────────────────────────────────
    etapas_lazy = [
        ("Etapa 1  – snake_case",          _etapa_1_limpieza_basica),
        ("Etapa 2  – PK",                  _etapa_2_validacion_pk),
        ("Etapa 3  – type casting",        _etapa_3_type_casting),
        ("Etapa 4  – nombres",             _etapa_4_limpieza_nombres),
        ("Etapa 5  – rangos",              _etapa_5_correccion_rangos),
        ("Etapa 6  – validación cruzada",  _etapa_6_validacion_cruzada),
        # Etapa 7: imputa age + experience_years. salary se deja para etapa 9
        # (debe pasar primero por corrección de ceros e IQR con datos reales).
        ("Etapa 7  – imputación age/exp",  _etapa_7_imputacion_nulos),
    ]
    for label, fn in etapas_lazy:
        t0 = time.perf_counter()
        q = fn(q)
        logger.info(f"  ⏱  {label} encolado en {time.perf_counter() - t0:.4f}s")

    # ── Materialización ────────────────────────────────────────────────────
    logger.info("\n⚙️  Materializando datos (etapas 8-12 requieren datos en memoria)…")
    t0 = time.perf_counter()
    df = q.collect()
    n_post_lazy = len(df)
    logger.info(
        f"  ⏱  Collect completado en {time.perf_counter() - t0:.3f}s "
        f"| Δ filas: {n_post_lazy - n_original:+,} "
        f"({(n_post_lazy - n_original) / n_original * 100:+.2f}%)"
    )
    _auditar_nulos(df, "Post-Etapa 7")

    # ── Etapas eager (8-12+) ───────────────────────────────────────────────
    # El orden es intencionalmente diferente al número de etapa para respetar
    # las dependencias de negocio:
    #   8  → hire_date limpia (la necesita etapa 12 para calcular antigüedad)
    #   9  → salary saneado (ceros, IQR, imputación)
    #   10 → performance_rating (independiente)
    #   12 → experience_years activos (depende de hire_date ya corregida)
    #   11 → estética final (siempre al último)
    etapas_eager = [
        ("Etapa 8  – hire_date + edad mínima",   _etapa_8_correccion_edad_minima_laboral),
        ("Etapa 9  – salary (ceros→IQR→imputa)", _etapa_9_salary_pipeline),
        ("Etapa 10 – performance_rating",        _etapa_10_performance_rating_adaptativo),
        ("Etapa 12 – experience activos",        _etapa_12_experience_activos),
        ("Etapa 11 – normalización final",       _etapa_11_normalizacion_final),
    ]
    for label, fn in etapas_eager:
        t0     = time.perf_counter()
        n_prev = len(df)
        df     = fn(df)
        delta  = len(df) - n_prev
        logger.info(
            f"  ⏱  {label}: {time.perf_counter() - t0:.3f}s "
            f"| Δ filas esta etapa: {delta:+,}"
        )

    # ── Reporte final ──────────────────────────────────────────────────────
    t_total = time.perf_counter() - t_pipeline
    logger.info("\n" + "=" * 70)
    logger.info("🎯 REPORTE FINAL DEL PIPELINE")
    logger.info("=" * 70)
    logger.info(f"  ⏱  Tiempo total pipeline:         {t_total:.2f}s")
    logger.info(f"  Filas entrada:                    {n_original:,}")
    logger.info(f"  Filas post-lazy (etapas 1-7):     {n_post_lazy:,} ({n_post_lazy - n_original:+,})")
    logger.info(f"  Filas salida final:               {len(df):,} ({len(df) - n_original:+,} total, {(len(df) - n_original) / n_original * 100:+.2f}%)")

    logger.info("\n  Tipos finales:")
    for col, dtype in zip(df.columns, df.dtypes):
        logger.info(f"    {col:<28} {dtype}")

    logger.info("\n  Nulos residuales:")
    nulos_finales = {c: df[c].null_count() for c in df.columns if df[c].null_count() > 0}
    if nulos_finales:
        logger.warning(f"    ⚠️  {len(nulos_finales)} columnas con nulos remanentes:")
        for col, n in nulos_finales.items():
            pct = n / len(df) * 100
            logger.warning(f"      {col:<28} {n:>8,}  ({pct:.4f}%)")
    else:
        logger.info("    ✅ Dataset completamente limpio – sin nulos")

    logger.info("=" * 70)

    # ── Persistencia ───────────────────────────────────────────────────────
    ruta_destino = f"{RUTA_TEMP}/clean.parquet"
    t0 = time.perf_counter()
    df.write_parquet(ruta_destino)
    logger.info(
        f"✅ Pipeline completado. Guardado en: {ruta_destino} "
        f"({time.perf_counter() - t0:.3f}s)"
    )

    return ruta_destino