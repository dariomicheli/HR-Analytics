-- =============================================
-- Data Warehouse - Tablas de destino
-- =============================================

-- Tabla de staging
CREATE TABLE IF NOT EXISTS stg_hr (
    employee_id VARCHAR(10),
    full_name VARCHAR(200),
    department VARCHAR(100),
    job_title VARCHAR(100),
    hire_date DATE NOT NULL,
    performance_rating VARCHAR(20),
    experience_years INTEGER,
    status VARCHAR(20),
    work_mode VARCHAR(20),
    salary DECIMAL(12, 2),
    country VARCHAR(100),
    city VARCHAR(100),
    age INTEGER,    
    job_level VARCHAR(20),    
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- TODO: Definir aquí las vistas materializadas para el consumo del dashboard.

CREATE MATERIALIZED VIEW gold_hr_hiring_evolution AS
SELECT
    EXTRACT(YEAR FROM hire_date) AS hire_year,
    EXTRACT(MONTH FROM hire_date) AS hire_month,
    to_char(hire_date, 'YYYY-MM') AS hire_month_year,
    country,
    city,
    department,
    job_title,
    AVG(salary) AS avg_salary,
    min(salary) AS min_salary,
    max(salary) AS max_salary,
    sum(salary) AS total_salary,
    AVG(experience_years) AS avg_experience,
    min(experience_years) AS min_experience,
    max(experience_years) AS max_experience,
    AVG(age) AS avg_age,
    MAX(age) AS max_age,
    MIN(age) AS min_age,
    COUNT(*) AS employee_count
FROM stg_hr
GROUP BY 1, 2, 3, 4, 5, 6, 7;

CREATE MATERIALIZED VIEW gold_hr_active_summary AS
SELECT
    country,
    city,
    department,
    job_title,
    performance_rating,
    work_mode,
    job_level,
    salary,
    experience_years,
    CAST(EXTRACT(YEAR FROM AGE(CURRENT_DATE, hire_date)) AS INTEGER) AS tenure_years,
    age
FROM stg_hr
where status = 'active';

-- Índices para que los filtros cruzados de Metabase sean instantáneos
CREATE INDEX idx_active_dept ON gold_hr_active_summary(department);
CREATE INDEX idx_active_country ON gold_hr_active_summary(country);
CREATE INDEX idx_active_city ON gold_hr_active_summary(city);
CREATE INDEX idx_active_job_title ON gold_hr_active_summary(job_title);
CREATE INDEX idx_active_performance ON gold_hr_active_summary(performance_rating);
CREATE INDEX idx_active_work_mode ON gold_hr_active_summary(work_mode);
CREATE INDEX idx_active_job_level ON gold_hr_active_summary(job_level);

create index idx_hiring_evolution_hire_month_year on gold_hr_hiring_evolution(hire_month_year);
CREATE INDEX idx_hiring_evolution_dept ON gold_hr_hiring_evolution(department);
CREATE INDEX idx_hiring_evolution_country ON gold_hr_hiring_evolution(country);
CREATE INDEX idx_hiring_evolution_city ON gold_hr_hiring_evolution(city);
CREATE INDEX idx_hiring_evolution_job_title ON gold_hr_hiring_evolution(job_title);
