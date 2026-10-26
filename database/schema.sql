CREATE DATABASE IF NOT EXISTS stackly_oneerp
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE stackly_oneerp;

CREATE TABLE IF NOT EXISTS fiscal_years (
  id INT AUTO_INCREMENT PRIMARY KEY,
  company_code VARCHAR(30) NOT NULL,
  code VARCHAR(20) NOT NULL,
  name VARCHAR(100) NOT NULL,
  variant VARCHAR(20) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  period_count INT NOT NULL DEFAULT 12,
  description VARCHAR(500),
  status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
  active_company_code VARCHAR(30)
    GENERATED ALWAYS AS (CASE WHEN status = 'ACTIVE' THEN company_code ELSE NULL END) STORED,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_fiscal_year_company_code UNIQUE (company_code, code),
  CONSTRAINT uq_fiscal_year_active_company UNIQUE (active_company_code),
  CONSTRAINT ck_fiscal_year_dates CHECK (start_date < end_date),
  CONSTRAINT ck_fiscal_year_variant CHECK (variant IN ('APR_MAR', 'JAN_DEC')),
  CONSTRAINT ck_fiscal_year_status CHECK (status IN ('DRAFT', 'ACTIVE')),
  CONSTRAINT ck_fiscal_year_period_count CHECK (period_count = 12),
  INDEX ix_fiscal_year_company_dates (company_code, start_date, end_date)
);

CREATE TABLE IF NOT EXISTS fiscal_periods (
  id INT AUTO_INCREMENT PRIMARY KEY,
  fiscal_year_id INT NOT NULL,
  period_number INT NOT NULL,
  name VARCHAR(60) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
  CONSTRAINT fk_fiscal_period_year FOREIGN KEY (fiscal_year_id)
    REFERENCES fiscal_years(id) ON DELETE CASCADE,
  CONSTRAINT uq_fiscal_period_number UNIQUE (fiscal_year_id, period_number),
  CONSTRAINT ck_fiscal_period_number CHECK (period_number BETWEEN 1 AND 12),
  CONSTRAINT ck_fiscal_period_dates CHECK (start_date <= end_date),
  CONSTRAINT ck_fiscal_period_status CHECK (status IN ('OPEN', 'CLOSED'))
);
