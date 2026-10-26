CREATE DATABASE IF NOT EXISTS stackly_oneerp
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE stackly_oneerp;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(254) NOT NULL UNIQUE,
  display_name VARCHAR(100) NOT NULL,
  password_hash VARCHAR(256) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fiscal_years (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id INT NOT NULL,
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
  CONSTRAINT uq_fiscal_year_company_code UNIQUE (owner_id, company_code, code),
  CONSTRAINT uq_fiscal_year_active_company UNIQUE (owner_id, active_company_code),
  CONSTRAINT fk_fiscal_year_owner FOREIGN KEY (owner_id)
    REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT ck_fiscal_year_dates CHECK (start_date < end_date),
  CONSTRAINT ck_fiscal_year_variant CHECK (variant IN ('APR_MAR', 'JAN_DEC')),
  CONSTRAINT ck_fiscal_year_status CHECK (status IN ('DRAFT', 'ACTIVE')),
  CONSTRAINT ck_fiscal_year_period_count CHECK (period_count = 12),
  INDEX ix_fiscal_year_company_dates (owner_id, company_code, start_date, end_date),
  INDEX ix_fiscal_years_owner_id (owner_id)
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

CREATE TABLE IF NOT EXISTS auth_sessions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  token_hash CHAR(64) NOT NULL UNIQUE,
  user_id INT NOT NULL,
  expires_at DATETIME NOT NULL,
  CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE,
  INDEX ix_auth_sessions_user (user_id)
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id INT AUTO_INCREMENT PRIMARY KEY,
  token_hash CHAR(64) NOT NULL UNIQUE,
  user_id INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME NOT NULL,
  used_at DATETIME,
  CONSTRAINT fk_password_reset_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE,
  INDEX ix_password_reset_user_created (user_id, created_at),
  INDEX ix_password_reset_tokens_user_id (user_id)
);

CREATE TABLE IF NOT EXISTS workspace_members (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_user_id INT NOT NULL,
  member_user_id INT NOT NULL,
  role VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_workspace_member_owner FOREIGN KEY (owner_user_id)
    REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_workspace_member_user FOREIGN KEY (member_user_id)
    REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT uq_workspace_member UNIQUE (owner_user_id, member_user_id),
  CONSTRAINT ck_workspace_member_role CHECK (role IN ('admin', 'requester', 'approver')),
  INDEX ix_workspace_member_owner (owner_user_id),
  INDEX ix_workspace_member_user (member_user_id)
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

CREATE TABLE IF NOT EXISTS approval_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  workspace_owner_id INT NOT NULL,
  module_id VARCHAR(40) NOT NULL,
  record_id INT NOT NULL,
  actor_id INT NOT NULL,
  action VARCHAR(20) NOT NULL,
  comment VARCHAR(500),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_approval_workspace_owner FOREIGN KEY (workspace_owner_id)
    REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_approval_record FOREIGN KEY (record_id)
    REFERENCES module_records(id) ON DELETE CASCADE,
  CONSTRAINT fk_approval_actor FOREIGN KEY (actor_id)
    REFERENCES users(id) ON DELETE CASCADE,
  INDEX ix_approval_record_history (workspace_owner_id, module_id, record_id, id)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id INT NOT NULL,
  source_module VARCHAR(40) NOT NULL,
  source_record_id INT NOT NULL,
  line_number INT NOT NULL,
  account_code VARCHAR(40) NOT NULL,
  account_name VARCHAR(160) NOT NULL,
  account_type VARCHAR(40) NOT NULL,
  posting_date DATE NOT NULL,
  document_no VARCHAR(160) NOT NULL,
  description VARCHAR(500) NOT NULL,
  debit_minor BIGINT NOT NULL DEFAULT 0,
  credit_minor BIGINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_ledger_owner FOREIGN KEY (owner_id)
    REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT uq_ledger_source_line UNIQUE (owner_id, source_module, source_record_id, line_number),
  INDEX ix_ledger_owner_account_date (owner_id, account_code, posting_date)
);

CREATE TABLE IF NOT EXISTS invoice_settlements (
  id INT AUTO_INCREMENT PRIMARY KEY,
  owner_id INT NOT NULL,
  invoice_record_id INT NOT NULL,
  module_id VARCHAR(40) NOT NULL,
  payment_reference VARCHAR(100) NOT NULL,
  posting_date DATE NOT NULL,
  amount_minor BIGINT NOT NULL,
  cash_account_code VARCHAR(40) NOT NULL,
  cash_account_name VARCHAR(160) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_settlement_owner FOREIGN KEY (owner_id)
    REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_settlement_invoice FOREIGN KEY (invoice_record_id)
    REFERENCES module_records(id) ON DELETE RESTRICT,
  CONSTRAINT ck_settlement_module CHECK (module_id IN ('ap', 'ar')),
  CONSTRAINT ck_settlement_amount CHECK (amount_minor > 0),
  CONSTRAINT uq_settlement_payment_reference UNIQUE (owner_id, module_id, payment_reference),
  INDEX ix_settlement_owner_invoice (owner_id, invoice_record_id)
);
