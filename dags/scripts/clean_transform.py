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

    # Experience no puede superar age - 16.
    # Si age es null la condición evalúa null → se conserva el valor original. ✅
    q = q.with_columns(
        pl.when(pl.col("experience_years") > (pl.col("age") - 16))
        .then(pl.col("age") - 16)
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
    """ETAPA 7: Imputación de nulos (previo a etapas 8-11)"""
    logger.info("▶️  ETAPA 7: Imputación de Nulos Básicos")

    q = q.with_columns([
        pl.col("salary")
          .fill_null(pl.col("salary").median().over(["job_level", "department"])),
        pl.col("age")
          .fill_null(pl.col("age").median().over(["job_level", "department"])),
        pl.col("experience_years")
          .fill_null(pl.col("experience_years").median().over(["job_level", "department"])),
        pl.col(_COLS_CATEGORICAS_FIJAS).fill_null(VALOR_CENTINELA),
        # performance_rating NO recibe centinela aquí; su lógica adaptativa
        # es responsabilidad exclusiva de etapa 10.
    ]).with_columns([
        # Fallback global para los grupos que no tienen ningún valor válido
        pl.col("salary").fill_null(pl.col("salary").median()),
        pl.col("age")
          .fill_null(pl.col("age").median()).round(0).cast(pl.Int32),
        pl.col("experience_years")
          .fill_null(pl.col("experience_years").median()).round(0).cast(pl.Int32),
    ])

    # hire_date: no hay imputación determinística segura; se deja como null
    # para que etapa 8 la gestione junto con la validación de edad mínima.

    return q


def _etapa_8_correccion_edad_minima_laboral(df: pl.DataFrame) -> pl.DataFrame:
    """
    ETAPA 8: REGLA DE NEGOCIO – Corrección de hire_date por edad mínima laboral.
    SOLO APLICA A EMPLEADOS ACTIVOS.
    """
    logger.info("▶️  ETAPA 8: Corrección por Edad Mínima Laboral (SOLO ACTIVOS)")

    es_activo_con_datos = (
        (pl.col("status") == "active") &    # normalizado en etapa 3
        (pl.col("hire_date").is_not_null()) &
        (pl.col("age").is_not_null())
    )

    df = df.with_columns(
        pl.when(es_activo_con_datos)
          .then(
              pl.col("age") - ((FECHA_DATASET - pl.col("hire_date")).dt.total_days() / 365.25)
          )
          .otherwise(None)
          .alias("edad_al_contratar")
    )

    edad_negativa  = df.filter(pl.col("edad_al_contratar") <  0).height
    edad_menor_18  = df.filter(
        (pl.col("edad_al_contratar") >= 0) & (pl.col("edad_al_contratar") < EDAD_MINIMA_LABORAL)
    ).height

    if edad_negativa > 0:
        logger.warning(f"  ⚠️  {edad_negativa:,} activos con edad_al_contratar < 0 (hire_date futura)")

    if edad_menor_18 > 0:
        logger.warning(f"  ⚠️  {edad_menor_18:,} activos contratados con < 18 años → ajustando hire_date")
        años_faltantes = EDAD_MINIMA_LABORAL - pl.col("edad_al_contratar")
        df = df.with_columns(
            pl.when(
                pl.col("edad_al_contratar").is_not_null() &
                (pl.col("edad_al_contratar") < EDAD_MINIMA_LABORAL) &
                (pl.col("edad_al_contratar") >= 0)
            )
            .then(pl.col("hire_date") + pl.duration(days=(años_faltantes * 365.25).cast(pl.Int32)))
            .otherwise(pl.col("hire_date"))
            .alias("hire_date")
        )

    fecha_sospechosa_count = df.filter(
        (pl.col("status") == "active") &
        (pl.col("hire_date").is_not_null()) &
        (pl.col("hire_date") < FECHA_SOSPECHOSA)
    ).height

    if fecha_sospechosa_count > 0:
        logger.warning(f"  ⚠️  {fecha_sospechosa_count:,} hire_date ACTIVAS < 1950: revisar origen de datos")

    return df.drop("edad_al_contratar")


def _etapa_9_imputacion_salary_ceros(df: pl.DataFrame) -> pl.DataFrame:
    """ETAPA 9: REGLA DE NEGOCIO – Imputación de salary == 0 (antes del análisis IQR)"""
    logger.info("▶️  ETAPA 9: Imputación de Salary == 0")

    salarios_cero = df.filter(pl.col("salary") == 0).height

    if salarios_cero > 0:
        logger.warning(f"  ⚠️  {salarios_cero:,} salarios == 0 detectados → imputando")

        mediana_global = df.filter(pl.col("salary") > 0)["salary"].median()
        mediana_grupo  = (
            pl.col("salary").filter(pl.col("salary") > 0)
            .median().over(["job_level", "department"])
        )

        df = df.with_columns(
            pl.when(pl.col("salary") == 0)
              .then(mediana_grupo.fill_null(mediana_global))
              .otherwise(pl.col("salary"))
              .alias("salary")
        )
        logger.info(f"    → Mediana global (excluyendo ceros): ${mediana_global:,.2f}")

    # Análisis IQR post-imputación (sin collect extra)
    if len(df) > 0:
        q1  = df["salary"].quantile(0.25)
        q3  = df["salary"].quantile(0.75)
        iqr = q3 - q1
        lim_inf = q1 - 1.5 * iqr
        lim_sup = q3 + 1.5 * iqr

        outliers = df.filter(
            (pl.col("salary") < lim_inf) | (pl.col("salary") > lim_sup)
        ).height

        pct_out = (outliers / len(df)) * 100
        logger.info(
            f"  Outliers salary (post-imputación): {outliers:,} ({pct_out:.4f}%) "
            f"| Rango IQR: [${lim_inf:,.0f} – ${lim_sup:,.0f}]"
        )

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


# ===========================================================================
# FUNCIÓN PRINCIPAL PARA AIRFLOW
# ===========================================================================

def clean_data(**context) -> str:
    """
    Pipeline completo de limpieza y transformación de datos HR en Polars.


    """

    t_pipeline = time.perf_counter()

    logger.info("╔" + "=" * 68 + "╗")
    logger.info("║" + " PIPELINE: clean_transform ".center(68) + "║")
    logger.info("║" + " 11 ETAPAS + REGLAS DE NEGOCIO ".center(68)          + "║")
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
        ("Etapa 1 – snake_case",       _etapa_1_limpieza_basica),
        ("Etapa 2 – PK",               _etapa_2_validacion_pk),
        ("Etapa 3 – type casting",     _etapa_3_type_casting),
        ("Etapa 4 – nombres",          _etapa_4_limpieza_nombres),
        ("Etapa 5 – rangos",           _etapa_5_correccion_rangos),
        ("Etapa 6 – validación cruzada", _etapa_6_validacion_cruzada),
        ("Etapa 7 – imputación nulos", _etapa_7_imputacion_nulos),
    ]
    for label, fn in etapas_lazy:
        t0 = time.perf_counter()
        q = fn(q)
        logger.info(f"  ⏱  {label} encolado en {time.perf_counter() - t0:.4f}s")

    # ── Materialización ────────────────────────────────────────────────────
    logger.info("\n⚙️  Materializando datos (etapas 8-11 requieren datos en memoria)…")
    t0 = time.perf_counter()
    df = q.collect()
    n_post_lazy = len(df)
    logger.info(
        f"  ⏱  Collect completado en {time.perf_counter() - t0:.3f}s "
        f"| Δ filas: {n_post_lazy - n_original:+,} "
        f"({(n_post_lazy - n_original) / n_original * 100:+.2f}%)"
    )
    _auditar_nulos(df, "Post-Etapa 7")

    # ── Etapas eager (8-11) ────────────────────────────────────────────────
    etapas_eager = [
        ("Etapa 8  – edad mínima laboral",   _etapa_8_correccion_edad_minima_laboral),
        ("Etapa 9  – salary ceros/IQR",      _etapa_9_imputacion_salary_ceros),
        ("Etapa 10 – performance_rating",    _etapa_10_performance_rating_adaptativo),
        ("Etapa 11 – normalización final",   _etapa_11_normalizacion_final),
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
    logger.info(f"  ⏱  Tiempo total pipeline:  {t_total:.2f}s")
    logger.info(f"  Filas entrada:             {n_original:,}")
    logger.info(f"  Filas post-lazy (etapas 1-7): {n_post_lazy:,} ({n_post_lazy - n_original:+,})")
    logger.info(f"  Filas salida final:        {len(df):,} ({len(df) - n_original:+,} total, {(len(df) - n_original) / n_original * 100:+.2f}%)")

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
