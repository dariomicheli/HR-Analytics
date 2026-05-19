# ---------------------------------------------------------------------------
# Librerias 
# ---------------------------------------------------------------------------
from __future__ import annotations
import logging
import logging.handlers
import pandas as pd
import numpy as np
import re
import sys
from typing import Callable, Optional, Tuple
from pathlib import Path
from datetime import datetime

# ===========================================================================
# CONFIGURACIÓN DE LOGGING
# ===========================================================================

def _setup_logger(
    name: str = __name__,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Configura logger con formato estructurado y handler a consola + archivo.
    
    Parameters
    ----------
    name : str
        Nombre del logger
    level : int
        Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Returns
    -------
    logging.Logger
        Logger configurado
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evitar duplicación si el logger ya tiene handlers
    if logger.handlers:
        return logger
    
    # Formato detallado para trazabilidad
    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

logger = _setup_logger(__name__)

# ===========================================================================
# CONSTANTES Y CONFIGURACIÓN
# ===========================================================================

# Importar constantes del módulo de configuración
# En producción, descomentar y adaptar rutas según la estructura real
from scripts.config import (
        EDAD_MAX,      
        EDAD_MIN,      
        EXP_MAX,      
        STRINGS_NULOS,  
        VALOR_CENTINELA)

 # Constantes locales del módulo
_COLS_TITLE_CASE = ["department", "job_title", "country", "city"]
_COLS_TEXTO_DB = ["department", "job_title", "status", "work_mode","country", "city", "job_level", "performance_rating"]
_COLS_CATEGORICAS_FIJAS = ["department", "job_title", "status", "work_mode","country", "city", "job_level"]
_COLS_NUMERICAS = ["salary", "age", "experience_years"]
_COLS_FECHAS = ["hire_date"]
_COLS_IDENTIFICADORES = ["employee_id"]

# Títulos honoríficos y grados académicos a eliminar de nombres
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
    r"^\s*(?:" + "|".join(_TITULOS) + r")\s+",
    flags=re.IGNORECASE,
)

_GRADOS_RE = re.compile(
    r"\s+(?:" + "|".join(_GRADOS) + r")\s*$",
    flags=re.IGNORECASE,
)

# Partículas que permanecen en minúscula dentro de un nombre
_PARTICULAS = {
    "van", "von", "de", "del", "den", "der",
    "da", "di", "du", "la", "le", "los", "las", "el",
}

# Valores válidos esperados en columnas categóricas
_VALID_STATUS = {"active", "inactive", "on_leave", "terminated", VALOR_CENTINELA}
_VALID_WORK_MODE = {"on-site", "hybrid", "remote", VALOR_CENTINELA}
_VALID_JOB_LEVEL = {"junior", "mid", "senior", "manager", "executive", VALOR_CENTINELA}
_VALID_PERFORMANCE = {"excellent", "good", "satisfactory", "needs improvement", f"unknown_{VALOR_CENTINELA}", VALOR_CENTINELA}

# ===========================================================================
# DECORADORES Y UTILIDADES
# ===========================================================================

def _timer_etapa(nombre_etapa: str) -> Callable:
    """
    Decorador que registra tiempo de ejecución de una etapa.
    
    Parameters
    ----------
    nombre_etapa : str
        Nombre descriptivo de la etapa
        
    Returns
    -------
    Callable
        Decorador funcional
    """
    def decorador(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            inicio = datetime.now()
            logger.info(f"▶️  Iniciando: {nombre_etapa}")
            try:
                resultado = func(*args, **kwargs)
                duracion = (datetime.now() - inicio).total_seconds()
                logger.info(f"✅ {nombre_etapa} completada en {duracion:.2f}s")
                return resultado
            except Exception as e:
                duracion = (datetime.now() - inicio).total_seconds()
                logger.error(f"❌ {nombre_etapa} falló en {duracion:.2f}s: {str(e)}")
                raise
        return wrapper
    return decorador

def _log_cambios(
    df_antes: pd.DataFrame,
    df_despues: pd.DataFrame,
    etapa: str,
    columnas_afectadas: Optional[list] = None
) -> None:
    """
    Loguea cambios entre DataFrames.
    
    Parameters
    ----------
    df_antes : pd.DataFrame
        DataFrame antes de transformación
    df_despues : pd.DataFrame
        DataFrame después de transformación
    etapa : str
        Nombre de la etapa
    columnas_afectadas : list, optional
        Columnas que fueron modificadas
    """
    filas_antes = len(df_antes)
    filas_despues = len(df_despues)
    filas_eliminadas = filas_antes - filas_despues
    
    logger.debug(f"  {etapa}: {filas_antes:,} → {filas_despues:,} filas " +
                f"({filas_eliminadas:+,})")
    
    if columnas_afectadas:
        logger.debug(f"  Columnas afectadas: {', '.join(columnas_afectadas)}")

# ===========================================================================
# FUNCIONES AUXILIARES - LIMPIEZA DE TEXTO
# ===========================================================================

def _limpiar_nombre(nombre: str) -> str:
    """
    Normaliza nombres personales:
      - Elimina títulos honoríficos y grados académicos
      - Remueve caracteres no deseados
      - Aplica Title Case inteligente (respeta partículas)
    """
    if pd.isna(nombre) or not isinstance(nombre, str):
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

def _normalizar_texto(texto: str) -> str:
    """
    Normaliza texto genérico: trim y colapso de espacios.

    """
    if not isinstance(texto, str):
        return texto
    
    texto = texto.strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto

# ===========================================================================
# ETAPA 1: LIMPIEZA BÁSICA
# ===========================================================================

@_timer_etapa("ETAPA 1: Limpieza Básica")
def _etapa_limpieza_basica(df: pd.DataFrame) -> pd.DataFrame:
    """
    Eliminación de columnas redundantes
    Estandarización de encabezados
    Limpieza de espacios en las columnas
    
    """
    #0. Control de ingreso del df
    if df.empty:
        raise ValueError("❌ DataFrame vacío recibido en limpieza básica")
    
    logger.info(f"  Input: {len(df):,} filas × {len(df.columns)} columnas")
    
    # 1. Eliminar columnas redundantes
    df = df.drop(columns=["Year"], errors="ignore")
    
    # 2. Estandarizar encabezados a snake_case
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[^\w\s]", "", regex=True)
        .str.replace(r"\s+", "_", regex=True)
    )
    logger.debug(f"  Encabezados normalizados a snake_case: {list(df.columns)}")
    
    # 3. Limpieza de espacios en columnas de texto
    cols_excluir = {"employee_id", "hire_date", "salary"}
    cols_texto = [
        c for c in df.select_dtypes(include=["object", "string"]).columns
        if c not in cols_excluir
    ]
    
    df[cols_texto] = df[cols_texto].apply(
        lambda col: (
            col.astype("string")
               .str.strip()
               .str.replace(r"\s+", " ", regex=True)
        ),
        axis=0
    )
    logger.debug(f"  Limpieza de espacios en {len(cols_texto)} columnas de texto")
    
    logger.info(f"  Output: {len(df):,} filas × {len(df.columns)} columnas")
    return df

# ===========================================================================
# ETAPA 2: LIMPIEZA DE NOMBRES Y CLAVE PRIMARIA
# ===========================================================================

@_timer_etapa("ETAPA 2: Limpieza de Nombres y Validación de Claves")
def _etapa_limpieza_claves(df: pd.DataFrame) -> pd.DataFrame:
    """
        Segunda etapa: limpieza de nombres propios y validación de claves primarias.
    """
    filas_antes = len(df)
    
    # 1. Limpiar columna de nombres
    if "full_name" in df.columns:
        df["full_name"] = df["full_name"].astype("string").apply(_limpiar_nombre)
        
        # Eliminar filas con nombres vacíos tras limpieza
        mask_nombres_vacios = df["full_name"].eq("")
        n_vacios = mask_nombres_vacios.sum()
        
        if n_vacios > 0:
            logger.warning(f"  ⚠️  {n_vacios:,} nombres quedaron vacíos tras limpieza. Eliminando.")
            df = df[~mask_nombres_vacios]
        
        logger.debug(f"  Nombres normalizados y validados")
    
    # 2. Validar clave primaria (employee_id)
    if "employee_id" not in df.columns:
        raise ValueError("❌ Columna 'employee_id' no encontrada. Es clave primaria requerida.")
    
    # Eliminar nulos en clave primaria
    n_nulos_id = df["employee_id"].isna().sum()
    if n_nulos_id > 0:
        logger.warning(f"  ⚠️  {n_nulos_id:,} employee_id nulos. Eliminando.")
        df = df.dropna(subset=["employee_id"])
    
    # Eliminar duplicados (mantener primer ocurrencia)
    n_duplicados = df["employee_id"].duplicated().sum()
    if n_duplicados > 0:
        logger.warning(f"  ⚠️  {n_duplicados:,} employee_id duplicados. Conservando primer ocurrencia.")
        df = df.drop_duplicates(subset=["employee_id"], keep="first")
    
    filas_eliminadas = filas_antes - len(df)
    if filas_eliminadas > 0:
        logger.info(f"  Filas eliminadas por claves: {filas_eliminadas:,}")
    
    if df.empty:
        raise ValueError("❌ No quedan registros válidos tras validación de claves primarias")
    
    logger.info(f"  Filas activas: {len(df):,}")
    return df

# ===========================================================================
# ETAPA 3: TYPE CASTING Y NORMALIZACIÓN
# ===========================================================================

@_timer_etapa("ETAPA 3: Type Casting y Normalización")
def _etapa_type_casting(df: pd.DataFrame) -> pd.DataFrame:
    """
    Tercera etapa: conversión explícita de tipos y normalización.
    -Casteo fechas 
    -Limpieza y casteo de salarios
    -Casteo de columnas numericas
    -Casteo de textos categoricos
    
    """
    
    # 1. Procesar fechas (hire_date)
    if "hire_date" in df.columns:
        try:
            df["hire_date"] = pd.to_datetime(
                df["hire_date"],
                errors="coerce",
                format="%Y-%m-%d"
            )
            n_nats = df["hire_date"].isna().sum()
            if n_nats > 0:
                logger.warning(f"  ⚠️  {n_nats:,} hire_date inválidas → NaT")
            logger.debug("  hire_date → datetime64[ns]")
        except Exception as e:
            logger.error(f"  ❌ Error al procesar hire_date: {str(e)}")
            raise
    
    # 2. Procesar salary (convertir a float limpio)
    if "salary" in df.columns:
        try:
            # Si es string, eliminar caracteres no numéricos
            if df["salary"].dtype == "object":
                df["salary"] = (
                    df["salary"]
                    .astype("string")
                    .str.replace(r"[^\d.-]", "", regex=True)
                )
            
            df["salary"] = pd.to_numeric(df["salary"], errors="coerce")
            
            # Convertir a float32 para optimizar memoria
            df["salary"] = df["salary"].astype("float32")
            
            n_nones = df["salary"].isna().sum()
            if n_nones > 0:
                logger.warning(f"  ⚠️  {n_nones:,} salary inválidos → NaN")
            
            logger.debug("  salary → float32")
        except Exception as e:
            logger.error(f"  ❌ Error al procesar salary: {str(e)}")
            raise
    
    # 3. Procesar columnas numéricas (age, experience_years)
    for col in ["age", "experience_years"]:
        if col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")
                n_nones = df[col].isna().sum()
                if n_nones > 0:
                    logger.warning(f"  ⚠️  {n_nones:,} {col} inválidos → NA")
                logger.debug(f"  {col} → Int32")
            except Exception as e:
                logger.error(f"  ❌ Error al procesar {col}: {str(e)}")
                raise
    
    # 4. Normalizar textos categóricos a minúsculas (para posterior validación)
    cols_cat = [c for c in _COLS_TEXTO_DB if c in df.columns]
    for col in cols_cat:
        df[col] = (
            df[col]
            .astype("string")
            .str.strip()
            .str.lower()
        )
        logger.debug(f"  {col} → string (minúsculas)")
    
    logger.info(f"  Types casteados exitosamente")
    return df

# ===========================================================================
# ETAPA 4: CORRECCIONES DE RANGOS NUMÉRICOS
# ===========================================================================

@_timer_etapa("ETAPA 4: Correcciones de Rangos Numéricos")
def _etapa_correciones_rangos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cuarta etapa: detección y corrección de valores fuera de rango.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con tipos casteados
        
    Returns
    -------
    pd.DataFrame
        DataFrame con valores corregidos
    """
    
    # 1. Corregir salary (negativos)
    if "salary" in df.columns:
        mask_neg = df["salary"] < 0
        n_neg = mask_neg.sum()
        
        if n_neg > 0:
            logger.warning(f"  ⚠️  {n_neg:,} salary negativos detectados")
            
            # Estrategia: calcular rango válido por grupo (job_level × department)
            cols_grupo = [c for c in ["job_level", "department"] if c in df.columns]
            
            if cols_grupo:
                group_stats = (
                    df[df["salary"] >= 0]
                    .groupby(cols_grupo, observed=True)["salary"]
                    .agg(q_min="min", q_max="max", q_median="median")
                    .reset_index()
                )
                
                df_merged = df.merge(group_stats, on=cols_grupo, how="left")
                
                # Negativos dentro del rango del grupo → abs()
                abs_sal = df["salary"].abs()
                in_range = mask_neg & (abs_sal >= df_merged["q_min"]) & (abs_sal <= df_merged["q_max"])
                
                # Negativos fuera del rango → NaN
                out_range = mask_neg & ~in_range
                
                n_corregidos = in_range.sum()
                n_fuera = out_range.sum()
                
                df.loc[in_range, "salary"] = abs_sal[in_range]
                df.loc[out_range, "salary"] = np.nan
                
                logger.info(f"    → {n_corregidos:,} corregidos con abs() | {n_fuera:,} → NaN")
    
    # 2. Corregir age (rango válido: EDAD_MIN - EDAD_MAX)
    if "age" in df.columns:
        mask_inv = (df["age"] < EDAD_MIN) | (df["age"] > EDAD_MAX)
        n_inv = mask_inv.sum()
        
        if n_inv > 0:
            logger.warning(f"  ⚠️  {n_inv:,} age fuera de [{EDAD_MIN}, {EDAD_MAX}] → NaN")
            df.loc[mask_inv, "age"] = np.nan
    
    # 3. Corregir experience_years (negativos y máximo)
    if "experience_years" in df.columns:
        # Negativos → abs()
        mask_neg = df["experience_years"] < 0
        n_neg = mask_neg.sum()
        
        if n_neg > 0:
            logger.warning(f"  ⚠️  {n_neg:,} experience_years negativos → abs()")
            df.loc[mask_neg, "experience_years"] = df.loc[mask_neg, "experience_years"].abs()
        
        # Mayores a EXP_MAX → NaN
        mask_max = df["experience_years"] > EXP_MAX
        n_max = mask_max.sum()
        
        if n_max > 0:
            logger.warning(f"  ⚠️  {n_max:,} experience_years > {EXP_MAX} → NaN")
            df.loc[mask_max, "experience_years"] = np.nan
    
    logger.info("  Rangos numéricos corregidos")
    return df

# ===========================================================================
# ETAPA 5: IMPUTACIÓN DE NULOS (CATEGORÍAS)
# ===========================================================================

@_timer_etapa("ETAPA 5: Imputación de Nulos en Categorías")
def _etapa_imputacion_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Quinta etapa: tratamiento de nulos en columnas categóricas.
    Estrategia adaptativa según % de nulos.
    
    """
    
    # 1. Categorías fijas: usar VALOR_CENTINELA
    cols_fijas = [c for c in _COLS_CATEGORICAS_FIJAS if c in df.columns]
    
    for col in cols_fijas:
        n_nulos = df[col].isna().sum()
        
        if n_nulos > 0:
            pct_nulos = (n_nulos / len(df)) * 100
            logger.debug(f"  {col}: {n_nulos:,} nulos ({pct_nulos:.2f}%)")
            
            # Relleno simple: usar VALOR_CENTINELA
            df[col] = df[col].fillna(VALOR_CENTINELA)
            logger.debug(f"    → Relleno con '{VALOR_CENTINELA}'")
    
    # 2. Performance_rating: estrategia adaptativa
    if "performance_rating" in df.columns:
        n_nulos = df["performance_rating"].isna().sum()
        
        if n_nulos > 0:
            pct_nulos = (n_nulos / len(df)) * 100
            logger.info(f"  performance_rating: {n_nulos:,} nulos ({pct_nulos:.2f}%)")
            
            if pct_nulos < 1:
                # Muy pocos nulos: eliminar filas
                logger.info(f"    → < 1%: eliminando {n_nulos:,} filas")
                df = df.dropna(subset=["performance_rating"]).copy()
            
            elif pct_nulos < 5:
                # Pocos nulos: imputar por moda de grupo
                logger.info(f"    → 1-5%: imputando por moda de grupo (job_level × department)")
                
                cols_grupo = [c for c in ["job_level", "department"] if c in df.columns]
                
                if cols_grupo:
                    fallback = (
                        df["performance_rating"].mode().iloc[0]
                        if not df["performance_rating"].mode().empty
                        else VALOR_CENTINELA
                    )
                    
                    moda_grupo = df.groupby(cols_grupo, observed=True)["performance_rating"].transform(
                        lambda x: x.mode().iloc[0] if not x.mode().empty else fallback
                    )
                    
                    df["performance_rating"] = df["performance_rating"].fillna(moda_grupo)
                else:
                    # Sin columnas de grupo, usar moda global
                    moda_global = (
                        df["performance_rating"].mode().iloc[0]
                        if not df["performance_rating"].mode().empty
                        else VALOR_CENTINELA
                    )
                    df["performance_rating"] = df["performance_rating"].fillna(moda_global)
            
            else:
                # Muchos nulos: usar centinela
                logger.warning(f"    → ≥ 5%: usando centinela '{VALOR_CENTINELA}'")
                df["performance_rating"] = df["performance_rating"].fillna(f"unknown_{VALOR_CENTINELA}")
    
    logger.info("  Categorías imputadas")
    return df

# ===========================================================================
# ETAPA 6: IMPUTACIÓN DE NULOS (NUMÉRICAS)
# ===========================================================================

@_timer_etapa("ETAPA 6: Imputación de Nulos en Numéricas")
def _etapa_imputacion_numericas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sexta etapa: imputación de nulos en columnas numéricas.
    Estrategia: mediana por grupo, fallback a mediana global.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con nulos categóricos tratados
        
    Returns
    -------
    pd.DataFrame
        DataFrame sin nulos en numéricas (imputadas)
    """
    
    cols_numericas = [c for c in _COLS_NUMERICAS if c in df.columns]
    
    for col in cols_numericas:
        n_nulos = df[col].isna().sum()
        
        if n_nulos > 0:
            pct_nulos = (n_nulos / len(df)) * 100
            logger.info(f"  {col}: {n_nulos:,} nulos ({pct_nulos:.2f}%)")
            
            # Intentar imputar por grupo (si existen columnas de agrupación)
            cols_grupo = [c for c in ["job_level", "department"] if c in df.columns]
            
            if cols_grupo and len(df) > 1:
                mediana_grupo = df.groupby(cols_grupo, observed=True)[col].transform("median")
                df[col] = df[col].fillna(mediana_grupo)
                n_nulos_post_grupo = df[col].isna().sum()
                logger.debug(f"    → Imputación por grupo: {n_nulos - n_nulos_post_grupo:,} valores")
                
                if n_nulos_post_grupo > 0:
                    # Fallback a mediana global
                    mediana_global = df[col].median()
                    if pd.notna(mediana_global):
                        df[col] = df[col].fillna(mediana_global)
                        logger.debug(f"    → Fallback global: {n_nulos_post_grupo:,} valores")
            else:
                # Sin grupos: mediana global directa
                mediana_global = df[col].median()
                if pd.notna(mediana_global):
                    df[col] = df[col].fillna(mediana_global)
                    logger.debug(f"    → Mediana global: {n_nulos:,} valores")
    
    logger.info("  Numéricas imputadas")
    return df

# ===========================================================================
# ETAPA 7: VALIDACIONES DE CONSISTENCIA
# ===========================================================================

@_timer_etapa("ETAPA 7: Validaciones de Consistencia Cruzada")
def _etapa_validaciones_cruzadas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Séptima etapa: validaciones lógicas entre columnas relacionadas.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con nulos tratados
        
    Returns
    -------
    pd.DataFrame
        DataFrame validado (con warnings si hay inconsistencias)
    """
    
    # 1. Validar experience_years vs age
    if "experience_years" in df.columns and "age" in df.columns:
        # Experiencia no puede ser mayor que edad - 16 (edad mínima laboral hipotética)
        mask_inconsistente = df["experience_years"] > (df["age"] - 16)
        n_inconsistentes = mask_inconsistente.sum()
        
        if n_inconsistentes > 0:
            logger.warning(f"  ⚠️  {n_inconsistentes:,} registros: experience_years > (age - 16)")
            logger.debug("    Consejo: Revisar datos de origen para empleados antiguos")
    
    # 2. Validar salary > 0
    if "salary" in df.columns:
        mask_cero = df["salary"] == 0
        n_cero = mask_cero.sum()
        
        if n_cero > 0:
            logger.warning(f"  ⚠️  {n_cero:,} registros con salary = 0")
    
    # 3. Validar hire_date ≤ fecha actual
    if "hire_date" in df.columns:
        fecha_actual = pd.Timestamp.now()
        mask_futura = df["hire_date"] > fecha_actual
        n_futura = mask_futura.sum()
        
        if n_futura > 0:
            logger.warning(f"  ⚠️  {n_futura:,} hire_date en el futuro")
    
    # 4. Validar status válido
    if "status" in df.columns:
        status_invalidos = ~df["status"].isin(_VALID_STATUS)
        n_invalidos = status_invalidos.sum()
        
        if n_invalidos > 0:
            valores_invalidos = df[status_invalidos]["status"].unique()
            logger.warning(f"  ⚠️  {n_invalidos:,} status inválidos: {set(valores_invalidos)}")
    
    # 5. Validar work_mode válido
    if "work_mode" in df.columns:
        work_mode_invalidos = ~df["work_mode"].isin(_VALID_WORK_MODE)
        n_invalidos = work_mode_invalidos.sum()
        
        if n_invalidos > 0:
            valores_invalidos = df[work_mode_invalidos]["work_mode"].unique()
            logger.warning(f"  ⚠️  {n_invalidos:,} work_mode inválidos: {set(valores_invalidos)}")
    
    # 6. Validar job_level válido
    if "job_level" in df.columns:
        job_level_invalidos = ~df["job_level"].isin(_VALID_JOB_LEVEL)
        n_invalidos = job_level_invalidos.sum()
        
        if n_invalidos > 0:
            valores_invalidos = df[job_level_invalidos]["job_level"].unique()
            logger.warning(f"  ⚠️  {n_invalidos:,} job_level inválidos: {set(valores_invalidos)}")
    
    logger.info("  Validaciones cruzadas completadas")
    return df

# ===========================================================================
# ETAPA 8: NORMALIZACIÓN FINAL (TITLE CASE Y FORMAT)
# ===========================================================================

@_timer_etapa("ETAPA 8: Normalización Final de Formato")
def _etapa_normalizacion_final(df: pd.DataFrame) -> pd.DataFrame:
    """
    Octava etapa: aplicación de Title Case en campos semánticos.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame validado
        
    Returns
    -------
    pd.DataFrame
        DataFrame con formato final normalizado
    """
    
    # Aplicar Title Case en columnas específicas
    cols_title = [c for c in _COLS_TITLE_CASE if c in df.columns]
    
    for col in cols_title:
        # Title case aplicado (convertir a string primero)
        df[col] = df[col].astype("string").str.title()
        logger.debug(f"  {col} → Title Case")
    
    # Aplicar Title Case especial para performance_rating (si existe)
    if "performance_rating" in df.columns:
        df["performance_rating"] = (
            df["performance_rating"]
            .astype("string")
            .str.replace("_", " ")
            .str.title()
        )
        logger.debug("  performance_rating → Title Case")
    
    logger.info("  Formatos finales normalizados")
    return df

# ===========================================================================
# ETAPA 9: REPORTE FINAL Y VALIDACIÓN
# ===========================================================================

def _etapa_reporte_final(
    df: pd.DataFrame,
    df_original: pd.DataFrame
) -> None:
    """
    Novena etapa: generación de reporte final de calidad.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame procesado
    df_original : pd.DataFrame
        DataFrame original (para comparación)
    """
    
    logger.info("=" * 70)
    logger.info("🎯 REPORTE FINAL DEL PIPELINE")
    logger.info("=" * 70)
    
    # Estadísticas globales
    logger.info(f"Filas procesadas:")
    logger.info(f"  Entrada:  {len(df_original):,}")
    logger.info(f"  Salida:   {len(df):,}")
    logger.info(f"  Cambio:   {len(df) - len(df_original):+,} ({((len(df) - len(df_original)) / len(df_original) * 100):.2f}%)")
    
    logger.info(f"\nColumnas procesadas:")
    logger.info(f"  Total: {len(df.columns)}")
    logger.info(f"  Nombres: {list(df.columns)}")
    
    # Nulos remanentes
    logger.info(f"\nNulos remanentes:")
    nulos_remanentes = df.isna().sum()
    nulos_remanentes = nulos_remanentes[nulos_remanentes > 0]
    
    if nulos_remanentes.empty:
        logger.info("  ✅ Ninguno (completamente limpio)")
    else:
        for col, n in nulos_remanentes.items():
            pct = (n / len(df)) * 100
            logger.info(f"  {col}: {n:,} ({pct:.2f}%) - INTENCIONAL")
    
    # Tipos de datos
    logger.info(f"\nTipos de datos finales:")
    for col, dtype in df.dtypes.items():
        logger.info(f"  {col}: {dtype}")
    
    logger.info("=" * 70)
    logger.info("✅ Pipeline completado exitosamente")
    logger.info("=" * 70)

# ===========================================================================
# FUNCIÓN PRINCIPAL DEL PIPELINE
# ===========================================================================

def clean_data(**context) -> pd.DataFrame:
    """
    PIPELINE COMPLETO DE LIMPIEZA Y TRANSFORMACIÓN DE DATOS
    
    Ejecuta el proceso ETL completo en 9 etapas:
    
    1. Limpieza Básica: encabezados, espacios, columnas redundantes
    2. Limpieza de Nombres: normalización de nombres propios y claves
    3. Type Casting: conversión consistente de tipos
    4. Correcciones de Rangos: validación de valores numéricos
    5. Imputación Categóricas: tratamiento de nulos en categorías
    6. Imputación Numéricas: completado de valores faltantes
    7. Validaciones Cruzadas: verificación de consistencia lógica
    8. Normalización Final: format final de presentación
    9. Reporte Final: generación de métricas de calidad
    
    """
    
    logger.info("╔" + "=" * 68 + "╗")
    logger.info("║" + " INICIANDO PIPELINE: clean_transform ".center(68) + "║")
    logger.info("╚" + "=" * 68 + "╝")

    ti = context.get("ti")
    if ti is None:
        raise ValueError("No TaskInstance (ti) en contexto Airflow")
    df = ti.xcom_pull(task_ids="extract_csv")

    try:
        # Guardar DataFrame original para comparación
        df_original = df.copy()
        
        # ETAPAS DEL PIPELINE (secuencial)
        df = _etapa_limpieza_basica(df)
        df = _etapa_limpieza_claves(df)
        df = _etapa_type_casting(df)
        df = _etapa_correciones_rangos(df)
        df = _etapa_imputacion_categoricas(df)
        df = _etapa_imputacion_numericas(df)
        df = _etapa_validaciones_cruzadas(df)
        df = _etapa_normalizacion_final(df)
        
        # REPORTE FINAL
        _etapa_reporte_final(df, df_original)
        
        # Reset de índices para limpieza final
        df = df.reset_index(drop=True)
        
        return df
    
    except Exception as e:
        logger.critical(f"❌ PIPELINE FALLIDO: {str(e)}")
        logger.critical("Traceback:", exc_info=True)
        raise


