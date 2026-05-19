-- =============================================
-- Data Warehouse - Tablas de destino
-- =============================================

-- Tabla de staging
CREATE TABLE IF NOT EXISTS stg_hr (
    employee_id VARCHAR(10) PRIMARY KEY,
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