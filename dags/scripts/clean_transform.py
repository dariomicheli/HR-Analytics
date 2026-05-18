"""
clean_transform(df)          ← punto de entrada único (público)
    ├── _paso_encabezados_y_texto()
    │       ├── _estandarizar_encabezados()
    │       ├── _limpiar_texto_general()
    │       ├── _aplicar_title_case()
    │       └── _limpiar_columna_nombres()
    │               └── _limpiar_nombre()   ← función pura, testeable
    ├── _paso_clave_primaria()
    ├── _paso_casteo_tipos()
    ├── _paso_nulos_categoricas()
    │       └── _imputar_performance_rating()
    └── _paso_rango_numericos()
            ├── _corregir_salary()
            ├── _corregir_age()
            └── _corregir_experience_years()

clean_transform.py
==================

Limpieza y transformación del DataFrame de empleados.

Responsabilidades:
    1. Estandarizar encabezados (snake_case)
    2. Limpiar texto y nombres
    3. Validar / limpiar clave primaria
    4. Castear tipos
    5. Tratar nulos en categóricas
    6. Corregir valores fuera de rango en numéricas

Contrato de interfaz
--------------------
    Entrada : pd.DataFrame con las columnas originales del CSV (casing libre)
    Salida  : pd.DataFrame limpio, listo para quality_checks → load

"""

# ---------------------------------------------------------------------------
# Librerias y Importacion de constantes 
# ---------------------------------------------------------------------------


# Librerias Utilizas
import logging
import pandas as pd
import logging
import re
import numpy as np

logger = logging.getLogger(__name__)

# Importacion de constantes
from __future__ import annotations

from scripts.config import (
    EDAD_MAX,
    EDAD_MIN,
    EXP_MAX,
    STRINGS_NULOS,
    VALOR_CENTINELA,
)

# ---------------------------------------------------------------------------
# Constantes locales 
# ---------------------------------------------------------------------------

_COLS_TITLE_CASE = ["department", "job_title", "country", "city"]

_COLS_TEXTO_DB = [
    "department", "job_title", "status", "work_mode",
    "country", "city", "job_level", "performance_rating",
]

_COLS_CATEGORICAS_FIJAS = [
    "department", "job_title", "status", "work_mode",
    "country", "city", "job_level",
]

# ===========================================================================
# Punto de entrada público
# ===========================================================================


def clean_data(**context) -> pd.DataFrame:
    
    """
    Ejecuta el pipeline completo de limpieza y transformación.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame crudo proveniente de extract.py.

    Retorna
    -------
    pd.DataFrame
        DataFrame limpio, listo para quality_checks → load.
    """
    logger.info("── Iniciando clean_transform ──────────────────────────────")
    ti = context['ti']
    df = ti.xcom_pull(task_ids='extract_csv')



# ===========================================================================
# Funciones auxiliares
# ===========================================================================


def _estandarizar_encabezados(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte todos los encabezados a snake_case estricto:
    minúsculas, sin espacios laterales, sin caracteres especiales.
    """
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[^\w\s]", "", regex=True)
        .str.replace(r"\s+", "_", regex=True)
    )
    logger.debug("Encabezados normalizados a snake_case.")
    return df


def _limpiar_texto_general(df: pd.DataFrame) -> pd.DataFrame:
    
    """Trim + colapso de espacios en todas las columnas de texto."""

    cols_obj = df.select_dtypes(include=["object", "string"]).columns
    df[cols_obj] = df[cols_obj].apply(
        lambda col: col.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    )
    return df


def _aplicar_title_case(df: pd.DataFrame) -> pd.DataFrame:

    """Title-case en columnas categóricas con sentido semántico."""
    
    cols = [c for c in _COLS_TITLE_CASE if c in df.columns]
    if cols:
        df[cols] = df[cols].apply(lambda col: col.str.title())
    return df


def _limpiar_nombre(nombre: str) -> str:
    """
    Normaliza un nombre personal:
      - Elimina títulos honoríficos y grados académicos
      - Remueve caracteres no deseados
      - Aplica Title Case inteligente (respeta partículas)
    """
    if pd.isna(nombre) or not isinstance(nombre, str):
        return ""

    nombre = nombre.strip()
    nombre = _TITULOS_RE.sub("", nombre)
    nombre = _GRADOS_RE.sub("", nombre)
    nombre = re.sub(r"[^\w\s\-\.\']", "", nombre, flags=re.UNICODE)
    nombre = re.sub(r"\s+", " ", nombre).strip()

    palabras = nombre.split()
    palabras_limpias = [
        palabra.lower() if i > 0 and palabra.lower() in _PARTICULAS
        else palabra.capitalize()
        for i, palabra in enumerate(palabras)
    ]
    return " ".join(palabras_limpias)


def _limpiar_columna_nombres(df: pd.DataFrame, col: str = "full_name") -> pd.DataFrame:
    """Aplica `_limpiar_nombre` y descarta filas que queden vacías."""

    if col not in df.columns:
        logger.warning("Columna '%s' no encontrada. Se omite limpieza de nombres.", col)
        return df

    df[col] = df[col].astype("string").apply(_limpiar_nombre)

    vacias = df[col].eq("").sum()
    
    if vacias > 0:
        df = df[df[col] != ""].copy()
        logger.warning("  → %s: %s filas vacías o nulas eliminadas.", col, f"{vacias:,}")

    logger.info("✓ Limpieza de nombres completada.")
    return df


# ===========================================================================
# Pasos del pipeline (ordenados y con firma clara)
# ===========================================================================


def _paso_encabezados_y_texto(df: pd.DataFrame) -> pd.DataFrame:
    df = _estandarizar_encabezados(df)
    df = _limpiar_texto_general(df)
    df = _aplicar_title_case(df)
    df = _limpiar_columna_nombres(df)
    return df


def _paso_clave_primaria(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina nulos y duplicados en employee_id."""
    nulos = df["employee_id"].isna().sum()
    if nulos > 0:
        logger.warning("  → employee_id: %s registros con ID nulo eliminados.", f"{nulos:,}")
        df = df.dropna(subset=["employee_id"])

    duplicados = df["employee_id"].duplicated().sum()
    if duplicados > 0:
        logger.warning(
            "  → employee_id: %s IDs duplicados. Conservando primera aparición.",
            f"{duplicados:,}",
        )
        df = df.drop_duplicates(subset=["employee_id"], keep="first")

    logger.info("✓ Clave primaria validada. Filas activas: %s", f"{len(df):,}")
    return df


def _paso_casteo_tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Castea fechas, salario, texto y enteros secundarios."""

    # ── Fechas ────────────────────────────────────────────────────────────
    df["hire_date"] = pd.to_datetime(df["hire_date"], errors="coerce")
    nats = df["hire_date"].isna().sum()
    if nats > 0:
        logger.warning("  → hire_date: %s fechas inválidas → NaT.", f"{nats:,}")

    # ── Salary ────────────────────────────────────────────────────────────
    if df["salary"].dtype == object:
        df["salary"] = df["salary"].str.replace(r"[^\d.-]", "", regex=True)
    df["salary"] = pd.to_numeric(df["salary"], errors="coerce").astype("float32").round(2)

    # ── Columnas de texto → str limpio, nulos literales → NaN ─────────────
    # Mantenemos str (no category) por compatibilidad con drivers SQL.
    cols_texto = [c for c in _COLS_TEXTO_DB if c in df.columns]
    for col in cols_texto:
        df[col] = df[col].astype(str).str.strip().replace(STRINGS_NULOS, np.nan)

    # ── Enteros secundarios (Int16) ───────────────────────────────────────
    for col in ("experience_years", "age"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int16")

    logger.info("✓ Tipos casteados. Filas activas: %s", f"{len(df):,}")
    return df


def _paso_nulos_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Imputa nulos en columnas categóricas con centinela o estrategia adaptativa
    para performance_rating.
    """

    # Centinela fijo para categóricas no críticas
    cols_fijas = [c for c in _COLS_CATEGORICAS_FIJAS if c in df.columns]
    for col in cols_fijas:
        nulos = df[col].isna().sum()
        if nulos > 0:
            df[col] = df[col].fillna(VALOR_CENTINELA)
            logger.info("  → %s: %s nulos → '%s'.", col, f"{nulos:,}", VALOR_CENTINELA)

    # Estrategia adaptativa para performance_rating
    if "performance_rating" in df.columns:
        df = _imputar_performance_rating(df)

    logger.info("✓ Nulos en categóricas tratados.")
    return df


def _imputar_performance_rating(df: pd.DataFrame) -> pd.DataFrame:
    """
    < 1%  → drop (bajo impacto; evita inventar datos de rendimiento)
    1–5%  → moda por grupo (job_level × department)
    ≥ 5%  → centinela 'unknown_performance'
    """
    ratio  = df["performance_rating"].isna().mean()
    n_nulos = df["performance_rating"].isna().sum()

    if n_nulos == 0:
        return df

    if ratio < 0.01:
        logger.info(
            "  → performance_rating: %.2f%% faltantes (< 1%%). Eliminando %s filas.",
            ratio * 100, f"{n_nulos:,}",
        )
        df = df.dropna(subset=["performance_rating"])

    elif ratio < 0.05:
        logger.info(
            "  → performance_rating: %.2f%% faltantes (1–5%%). Imputando por moda de grupo.",
            ratio * 100,
        )
        fallback = (
            df["performance_rating"].mode().iloc[0]
            if not df["performance_rating"].mode().empty
            else VALOR_CENTINELA
        )
        moda_grupo = df.groupby(["job_level", "department"])["performance_rating"].transform(
            lambda x: x.mode().iloc[0] if not x.mode().empty else fallback
        )
        df["performance_rating"] = df["performance_rating"].fillna(moda_grupo)

    else:
        logger.warning(
            "  ⚠ performance_rating: %.2f%% nulos (≥ 5%%). Asignando 'unknown_performance'.",
            ratio * 100,
        )
        df["performance_rating"] = df["performance_rating"].fillna("unknown_performance")

    return df


def _paso_rango_numericos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige valores fuera de rango en salary, age y experience_years.
    """
    df = _corregir_salary(df)
    df = _corregir_age(df)
    df = _corregir_experience_years(df)
    logger.info("✓ Rangos numéricos corregidos.")
    return df


def _corregir_salary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Negativos dentro del rango del grupo → abs().
    Negativos fuera del rango del grupo → NA → mediana de grupo.
    """
    mask_neg = df["salary"] < 0
    n_neg    = mask_neg.sum()

    if n_neg > 0:
        group_stats = (
            df[df["salary"] >= 0]
            .groupby(["job_level", "department"])["salary"]
            .agg(lower="min", upper="max")
        )
        df = df.join(group_stats, on=["job_level", "department"])

        abs_sal   = df["salary"].abs()
        in_range  = mask_neg & (abs_sal >= df["lower"]) & (abs_sal <= df["upper"])
        out_range = mask_neg & ~in_range

        df.loc[in_range,  "salary"] = abs_sal[in_range]
        df.loc[out_range, "salary"] = pd.NA
        df.drop(columns=["lower", "upper"], inplace=True)

        logger.info(
            "  → salary negativos: %s detectados | %s corregidos con abs() | %s → NA.",
            f"{n_neg:,}", f"{in_range.sum():,}", f"{out_range.sum():,}",
        )

    # Imputación grupal (cubre NAs originales + los generados arriba)
    med_grupo  = df.groupby(["job_level", "department"])["salary"].transform("median")
    med_global = df["salary"].median()
    df["salary"] = (
        df["salary"]
        .fillna(med_grupo)
        .fillna(med_global)
        .round(0)
        .astype("float32")
    )
    return df


def _corregir_age(df: pd.DataFrame) -> pd.DataFrame:
    mask_inv = (df["age"] < EDAD_MIN) | (df["age"] > EDAD_MAX)
    n_inv    = mask_inv.sum()
    if n_inv > 0:
        df.loc[mask_inv, "age"] = pd.NA
        logger.warning(
            "  → age: %s valores fuera de [%s, %s] → NA.",
            f"{n_inv:,}", EDAD_MIN, EDAD_MAX,
        )
    return df


def _corregir_experience_years(df: pd.DataFrame) -> pd.DataFrame:
    mask_neg = df["experience_years"] < 0
    n_neg    = mask_neg.sum()
    if n_neg > 0:
        df.loc[mask_neg, "experience_years"] = df.loc[mask_neg, "experience_years"].abs()
        logger.warning("  → experience_years: %s negativos corregidos con abs().", f"{n_neg:,}")

    mask_max = df["experience_years"] > EXP_MAX
    n_max    = mask_max.sum()
    if n_max > 0:
        df.loc[mask_max, "experience_years"] = pd.NA
        logger.warning(
            "  → experience_years: %s valores > %s → NA.", f"{n_max:,}", EXP_MAX,
        )
    return df


def _resumen_final(df: pd.DataFrame) -> None:
    """Loguea nulos remanentes (intencionales) al finalizar el pipeline."""
    nulos = df.isna().sum()
    nulos = nulos[nulos > 0]
    if nulos.empty:
        logger.info("✅ clean_transform completado. %s filas. Sin nulos remanentes.", f"{len(df):,}")
    else:
        logger.warning(
            "✅ clean_transform completado. %s filas. Nulos remanentes (intencionales): %s",
            f"{len(df):,}", nulos.to_dict(),
        )




    # La columna 'Year' es redundante (derivable de hire_date)
    df = df.drop(columns=["Year"], errors="ignore")

    df = _paso_encabezados_y_texto(df)   # 1. Headers + texto + nombres
    df = _paso_clave_primaria(df)        # 2. PK: nulos y duplicados
    df = _paso_casteo_tipos(df)          # 3. Fechas, salary, str, Int16
    df = _paso_nulos_categoricas(df)     # 4. Imputación categóricas
    df = _paso_rango_numericos(df)       # 5. Rangos: salary, age, exp

    _resumen_final(df)
    
    df=df.reset_index(drop=True)

    logger.info("── clean_transform finalizado ─────────────────────────────")
    return df 


