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

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(254) NOT NULL UNIQUE,
  display_name VARCHAR(100) NOT NULL,
  password_hash VARCHAR(256) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  token_hash CHAR(64) NOT NULL UNIQUE,
  user_id INT NOT NULL,
  expires_at DATETIME NOT NULL,
  CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE,
  INDEX ix_auth_sessions_user (user_id)
);

CREATE TABLE IF NOT EXISTS module_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id INT NOT NULL,
  module_id VARCHAR(40) NOT NULL,
  name VARCHAR(160) NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'Draft',
  data JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_module_record_owner FOREIGN KEY (owner_id)
    REFERENCES users(id) ON DELETE CASCADE,
  INDEX ix_module_records_owner_module (owner_id, module_id)
);
