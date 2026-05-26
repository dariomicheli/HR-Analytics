import logging
from airflow.providers.postgres.hooks.postgres import PostgresHook
from scripts.config import POSTGRES_DWH_CONN_ID

"""
QUALITY CHECK

Ejecuta controles de calidad post-carga sobre la tabla stg_hr.

Validaciones realizadas:
- Verifica que la tabla no esté vacía.
- Detecta employee_id duplicados.
- Controla nulos en columnas críticas (employee_id, hire_date)
  y reporta nulos en columnas relevantes (salary, status).
- Valida valores permitidos en status.
- Detecta salarios inválidos (<= 0).
- Revisa el rango de fechas de hire_date.

Las validaciones críticas detienen el pipeline mediante excepciones.
Las no críticas generan advertencias en logs para análisis posterior.
"""

# +----------------------------+-------------+
# | Control                    | Acción     |
# +----------------------------+-------------+
# | Tabla vacía                | ❌ Falla   |
# | employee_id duplicado      | ❌ Falla   |
# | employee_id nulo           | ❌ Falla   |
# | hire_date nulo             | ❌ Falla   |
# | salary nulo                | ⚠️ Warning |
# | status nulo                | ⚠️ Warning |
# | status inválido            | ⚠️ Warning |
# | salary <= 0                | ⚠️ Warning |
# | hire_date fuera de rango   | ⚠️ Warning |
# +----------------------------+-------------+
#
# Las validaciones críticas detienen el pipeline mediante
# excepciones. Las restantes se registran como advertencias.
# -------------------------------------------------------------

def quality_checks(**context):
    """
    Checks de calidad post-carga sobre la tabla stg_hr.

    Ejecuta una serie de validaciones sobre los datos recién cargados
    y falla el pipeline si alguna regla crítica no se cumple.
    """
    logging.info("🔍 Iniciando quality checks sobre stg_hr...")

    hook = PostgresHook(postgres_conn_id=POSTGRES_DWH_CONN_ID)

    # ── 1. Conteo de filas ────────────────────────────────────────────────
    filas_totales = hook.get_first("SELECT COUNT(*) FROM stg_hr")[0]
    logging.info(f"  Filas cargadas en stg_hr: {filas_totales:,}")

    if filas_totales == 0:
        raise ValueError("❌ CALIDAD FALLIDA: La tabla stg_hr quedó vacía tras la carga.")

    # ── 2. Duplicados en employee_id ──────────────────────────────────────
    duplicados = hook.get_first("""
        SELECT COUNT(*) FROM (
            SELECT employee_id
            FROM stg_hr
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        ) dups
    """)[0]

    if duplicados > 0:
        raise ValueError(
            f"❌ CALIDAD FALLIDA: {duplicados} employee_ids duplicados en stg_hr. "
            "Revisar la etapa de validación de PK en clean_transform."
        )
    logging.info("  ✅ Sin duplicados en employee_id")

    # ── 3. Nulos en columnas críticas ─────────────────────────────────────
    checks_nulos = {
        "employee_id": "SELECT COUNT(*) FROM stg_hr WHERE employee_id IS NULL",
        "hire_date":   "SELECT COUNT(*) FROM stg_hr WHERE hire_date IS NULL",
        "salary":      "SELECT COUNT(*) FROM stg_hr WHERE salary IS NULL",
        "status":      "SELECT COUNT(*) FROM stg_hr WHERE status IS NULL",
    }

    for col, query in checks_nulos.items():
        nulos = hook.get_first(query)[0]
        pct = (nulos / filas_totales) * 100 if filas_totales > 0 else 0

        if col in ("employee_id", "hire_date") and nulos > 0:
            raise ValueError(f"❌ CALIDAD FALLIDA: {nulos} nulos en columna crítica '{col}'")

        if nulos > 0:
            logging.warning(f"  ⚠️  {col}: {nulos:,} nulos ({pct:.2f}%)")
        else:
            logging.info(f"  ✅ {col}: sin nulos")

    # ── 4. Valores de status inesperados ──────────────────────────────────
    status_inesperados = hook.get_first("""
        SELECT COUNT(*)
        FROM stg_hr
        WHERE status NOT IN ('active', 'resigned', 'terminated', 'retired')
    """)[0]

    if status_inesperados > 0:
        logging.warning(
            f"  ⚠️  {status_inesperados} filas con status fuera de ('active', 'inactive')"
        )

    # ── 5. Salarios negativos o cero ──────────────────────────────────────
    salarios_invalidos = hook.get_first(
        "SELECT COUNT(*) FROM stg_hr WHERE salary <= 0"
    )[0]

    if salarios_invalidos > 0:
        logging.warning(f"  ⚠️  {salarios_invalidos} filas con salary <= 0")
    else:
        logging.info("  ✅ Todos los salarios son positivos")

    # ── 6. Rango de hire_date ─────────────────────────────────────────────
    fecha_min, fecha_max = hook.get_first(
        "SELECT MIN(hire_date), MAX(hire_date) FROM stg_hr"
    )
    logging.info(f"  hire_date rango: {fecha_min} → {fecha_max}")

    if fecha_max and str(fecha_max) > "2026-03-25":
        logging.warning(f"  ⚠️  hire_date máxima ({fecha_max}) supera la fecha del dataset")

    # ── Resumen final ─────────────────────────────────────────────────────
    logging.info("=" * 60)
    logging.info(f"✅ Quality checks completados | {filas_totales:,} filas validadas")
    logging.info("=" * 60)

    return {
        "filas_totales": filas_totales,
        "duplicados_employee_id": duplicados,
        "hire_date_rango": f"{fecha_min} → {fecha_max}",
    }