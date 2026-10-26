import calendar
import hashlib
import hmac
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, relationship, selectinload, sessionmaker
from starlette.staticfiles import StaticFiles


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stackly_oneerp.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
engine_options = {"pool_pre_ping": True, "future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    __table_args__ = (
        UniqueConstraint("company_code", "code", name="uq_fiscal_year_company_code"),
        UniqueConstraint("active_company_code", name="uq_fiscal_year_active_company"),
        CheckConstraint("start_date < end_date", name="ck_fiscal_year_dates"),
        CheckConstraint("variant IN ('APR_MAR', 'JAN_DEC')", name="ck_fiscal_year_variant"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE')", name="ck_fiscal_year_status"),
        CheckConstraint("period_count = 12", name="ck_fiscal_year_period_count"),
        Index("ix_fiscal_year_company_dates", "company_code", "start_date", "end_date"),
    )

    id = Column(Integer, primary_key=True)
    company_code = Column(String(30), nullable=False)
    code = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    variant = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    period_count = Column(Integer, nullable=False, default=12)
    description = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT")
    active_company_code = Column(
        String(30),
        Computed("CASE WHEN status = 'ACTIVE' THEN company_code ELSE NULL END", persisted=True),
    )
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    periods = relationship(
        "FiscalPeriod",
        back_populates="fiscal_year",
        cascade="all, delete-orphan",
        order_by="FiscalPeriod.period_number",
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(254), nullable=False, unique=True, index=True)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)


class ModuleRecord(Base):
    __tablename__ = "module_records"
    __table_args__ = (
        Index("ix_module_records_owner_module", "owner_id", "module_id"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(String(40), nullable=False)
    name = Column(String(160), nullable=False)
    status = Column(String(40), nullable=False, default="Draft")
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_owner_account_date", "owner_id", "account_code", "posting_date"),
        UniqueConstraint(
            "owner_id",
            "source_module",
            "source_record_id",
            "line_number",
            name="uq_ledger_source_line",
        ),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_module = Column(String(40), nullable=False)
    source_record_id = Column(Integer, nullable=False)
    line_number = Column(Integer, nullable=False)
    account_code = Column(String(40), nullable=False)
    account_name = Column(String(160), nullable=False)
    account_type = Column(String(40), nullable=False)
    posting_date = Column(Date, nullable=False)
    document_no = Column(String(160), nullable=False)
    description = Column(String(500), nullable=False)
    debit_minor = Column(BigInteger, nullable=False, default=0)
    credit_minor = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"
    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "period_number", name="uq_fiscal_period_number"),
        CheckConstraint("period_number BETWEEN 1 AND 12", name="ck_fiscal_period_number"),
        CheckConstraint("start_date <= end_date", name="ck_fiscal_period_dates"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_fiscal_period_status"),
    )

    id = Column(Integer, primary_key=True)
    fiscal_year_id = Column(Integer, ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False)
    period_number = Column(Integer, nullable=False)
    name = Column(String(60), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
    fiscal_year = relationship("FiscalYear", back_populates="periods")


class FiscalYearCreate(BaseModel):
    company: str = Field(
        min_length=1,
        max_length=30,
        validation_alias=AliasChoices("company", "company_code"),
    )
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    variant: Literal["APR_MAR", "JAN_DEC"]
    start: date = Field(validation_alias=AliasChoices("start", "start_date"))
    end: date = Field(validation_alias=AliasChoices("end", "end_date"))
    period_count: int = Field(
        default=12,
        ge=12,
        le=12,
        validation_alias=AliasChoices("period_count", "periods"),
    )
    description: str | None = Field(default=None, max_length=500)

    @field_validator("company", "code", "name", mode="before")
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("company", "code")
    @classmethod
    def normalize_codes(cls, value):
        return value.upper()

    @model_validator(mode="after")
    def validate_calendar(self):
        if self.end <= self.start:
            raise ValueError("End date must be after start date.")
        if self.variant == "APR_MAR":
            if (self.start.month, self.start.day) != (4, 1):
                raise ValueError("April–March years must start on 1 April.")
            if (self.end.month, self.end.day) != (3, 31) or self.end.year != self.start.year + 1:
                raise ValueError("April–March years must end on 31 March of the next year.")
        elif (self.start.month, self.start.day) != (1, 1):
            raise ValueError("January–December years must start on 1 January.")
        elif (self.end.month, self.end.day) != (12, 31) or self.end.year != self.start.year:
            raise ValueError("January–December years must end on 31 December of the same year.")
        return self


class FiscalPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_number: int
    name: str
    start_date: date
    end_date: date
    status: str


class FiscalYearOut(BaseModel):
    id: int
    company: str
    code: str
    name: str
    variant: str
    start: date
    end: date
    period_count: int
    description: str | None
    status: str
    periods: list[FiscalPeriodOut] = Field(default_factory=list)


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email", "display_name", mode="before")
    @classmethod
    def strip_values(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value.lower()


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str


class AuthOut(BaseModel):
    user: UserOut


class ModuleRecordCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    status: str = Field(default="Draft", min_length=1, max_length=40)
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("name", "status", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ModuleRecordUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = Field(default=None, min_length=1, max_length=40)
    data: dict[str, object] | None = None

    @model_validator(mode="after")
    def reject_null_updates(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Updated fields cannot be null.")
        return self


class ModuleRecordOut(BaseModel):
    id: int
    module_id: str
    name: str
    status: str
    data: dict[str, object]
    created_at: datetime
    updated_at: datetime


class LedgerAccountOut(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    opening_debit_minor: int
    opening_credit_minor: int
    period_debit_minor: int
    period_credit_minor: int
    closing_debit_minor: int
    closing_credit_minor: int


class TrialBalanceOut(BaseModel):
    start_date: date
    end_date: date
    currency: str = "INR"
    accounts: list[LedgerAccountOut]
    total_debit_minor: int
    total_credit_minor: int
    balanced: bool


class AccountOptionOut(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    status: str


class LedgerLineOut(BaseModel):
    id: int
    source_module: str
    source_record_id: int
    line_number: int
    account_code: str
    account_name: str
    account_type: str
    posting_date: date
    document_no: str
    description: str
    debit_minor: int
    credit_minor: int


class BudgetVarianceOut(BaseModel):
    record_id: int
    budget_name: str
    account_code: str
    account_name: str
    start_date: date
    end_date: date
    budget_minor: int
    actual_minor: int
    variance_minor: int


class FiscalPeriodDetailOut(BaseModel):
    id: int
    fiscal_year_id: int
    fiscal_year_code: str
    fiscal_year_status: str
    period_number: int
    name: str
    start_date: date
    end_date: date
    status: str


def serialize_fiscal_period_detail(period: FiscalPeriod, year: FiscalYear) -> FiscalPeriodDetailOut:
    return FiscalPeriodDetailOut(
        id=period.id,
        fiscal_year_id=year.id,
        fiscal_year_code=year.code,
        fiscal_year_status=year.status,
        period_number=period.period_number,
        name=period.name,
        start_date=period.start_date,
        end_date=period.end_date,
        status=period.status,
    )


def serialize_year(year: FiscalYear, include_periods: bool = True) -> FiscalYearOut:
    return FiscalYearOut(
        id=year.id,
        company=year.company_code,
        code=year.code,
        name=year.name,
        variant=year.variant,
        start=year.start_date,
        end=year.end_date,
        period_count=year.period_count,
        description=year.description,
        status=year.status,
        periods=year.periods if include_periods else [],
    )


def generate_periods(start: date, end: date) -> list[FiscalPeriod]:
    periods = []
    cursor = start
    for period_number in range(1, 13):
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        period_end = min(date(cursor.year, cursor.month, last_day), end)
        periods.append(
            FiscalPeriod(
                period_number=period_number,
                name=cursor.strftime("%B %Y"),
                start_date=cursor,
                end_date=period_end,
                status="OPEN",
            )
        )
        if period_end == end:
            break
        next_month = cursor.month % 12 + 1
        next_year = cursor.year + (cursor.month == 12)
        cursor = date(next_year, next_month, 1)
    return periods


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


PASSWORD_ITERATIONS = 310_000
SESSION_LIFETIME = timedelta(days=7)
bearer_scheme = HTTPBearer(auto_error=False)
MODULE_IDS = {
    "company",
    "fiscal-period",
    "chart-of-accounts",
    "journal-entry",
    "general-ledger",
    "trial-balance",
    "ap",
    "ar",
    "fixed-assets",
    "budgeting",
    "gst",
    "financial-reports",
}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"{PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        iterations, salt_hex, digest_hex = encoded.split("$", 2)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + SESSION_LIFETIME,
        )
    )
    return token


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else request.cookies.get("stackly_session")
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if auth_session is None:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    user = db.get(User, auth_session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User account not found.")
    return user


def parse_posting_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Posting date must be a valid ISO date.") from error
    raise HTTPException(status_code=422, detail="A posting date is required.")


def amount_to_minor(value: object) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Amounts must be valid numbers.")
    if not amount.is_finite() or amount < 0:
        raise HTTPException(status_code=422, detail="Amounts must be finite and non-negative.")
    if amount > Decimal("92233720368547758.07"):
        raise HTTPException(status_code=422, detail="Amount exceeds the supported 64-bit ledger limit.")
    try:
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as error:
        raise HTTPException(status_code=422, detail="Amount exceeds the supported precision.") from error
    if rounded != amount:
        raise HTTPException(status_code=422, detail="Amounts may have at most two decimal places.")
    amount_minor = int(rounded * 100)
    if amount_minor > 9_223_372_036_854_775_807:
        raise HTTPException(status_code=422, detail="Amount exceeds the supported 64-bit ledger limit.")
    return amount_minor


def get_accounts_by_code(db: Session, owner_id: int) -> dict[str, ModuleRecord]:
    records = db.scalars(
        select(ModuleRecord).where(
            ModuleRecord.owner_id == owner_id,
            ModuleRecord.module_id == "chart-of-accounts",
        )
    ).all()
    accounts: dict[str, ModuleRecord] = {}
    for record in records:
        code = record.data.get("account_code")
        if isinstance(code, str) and code.strip():
            accounts[code.strip().upper()] = record
    return accounts


def validate_chart_account(
    db: Session,
    owner_id: int,
    account_status: str,
    data: dict[str, object],
    exclude_id: int | None = None,
) -> dict[str, object]:
    code = data.get("account_code")
    account_type = data.get("account_type")
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=422, detail="An account code is required.")
    normalized_code = code.strip().upper()
    if len(normalized_code) > 40:
        raise HTTPException(status_code=422, detail="Account codes cannot exceed 40 characters.")
    if not isinstance(account_type, str) or account_type not in {"Asset", "Liability", "Equity", "Income", "Expense"}:
        raise HTTPException(status_code=422, detail="Choose a valid chart-of-accounts type.")
    if account_status not in {"Draft", "Active", "Inactive"}:
        raise HTTPException(status_code=422, detail="Chart-of-accounts status must be Draft, Active, or Inactive.")
    existing = db.scalars(
        select(ModuleRecord).where(
            ModuleRecord.owner_id == owner_id,
            ModuleRecord.module_id == "chart-of-accounts",
        )
    ).all()
    if any(
        account.id != exclude_id
        and isinstance(account.data.get("account_code"), str)
        and account.data["account_code"].strip().upper() == normalized_code
        for account in existing
    ):
        raise HTTPException(status_code=409, detail=f"Account code {normalized_code} already exists.")
    return {**data, "account_code": normalized_code}


def require_account(
    accounts: dict[str, ModuleRecord],
    code: object,
    allowed_types: set[str],
) -> ModuleRecord:
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=422, detail="Select a chart-of-accounts code for every posting line.")
    account = accounts.get(code.strip().upper())
    if account is None or account.status != "Active":
        raise HTTPException(status_code=422, detail=f"Account {code} does not exist or is not active.")
    account_type = account.data.get("account_type")
    if account_type not in allowed_types:
        allowed = ", ".join(sorted(allowed_types))
        raise HTTPException(status_code=422, detail=f"Account {code} must have type {allowed}.")
    return account


def calculate_invoice_tax(data: dict[str, object], amount_minor: int) -> tuple[int, list[tuple[str, int]]]:
    mode = data.get("tax_mode") or "None"
    if mode == "None":
        return 0, []
    if not isinstance(mode, str) or mode not in {"IGST", "CGST+SGST"}:
        raise HTTPException(status_code=422, detail="Choose IGST, CGST+SGST, or None for invoice tax.")
    try:
        rate = Decimal(str(data.get("tax_rate")))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="GST rate must be a valid number.")
    if not rate.is_finite() or rate <= 0 or rate > 100:
        raise HTTPException(status_code=422, detail="GST rate must be greater than zero and no more than 100%.")
    total_tax_minor = int(
        (Decimal(amount_minor) * rate / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if total_tax_minor <= 0:
        raise HTTPException(status_code=422, detail="GST amount rounds to zero; increase the taxable amount or rate.")
    if mode == "IGST":
        return total_tax_minor, [(str(data.get("tax_account_code") or ""), total_tax_minor)]

    if data.get("cgst_rate") is not None and data.get("sgst_rate") is not None:
        try:
            cgst_rate = Decimal(str(data["cgst_rate"]))
            sgst_rate = Decimal(str(data["sgst_rate"]))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=422, detail="CGST and SGST rates must be valid numbers.")
        if (
            not cgst_rate.is_finite()
            or not sgst_rate.is_finite()
            or cgst_rate <= 0
            or sgst_rate <= 0
            or cgst_rate + sgst_rate > 100
        ):
            raise HTTPException(status_code=422, detail="CGST and SGST rates must be positive and total no more than 100%.")
        cgst_minor = int(
            (Decimal(amount_minor) * cgst_rate / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        sgst_minor = int(
            (Decimal(amount_minor) * sgst_rate / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        total_tax_minor = cgst_minor + sgst_minor
    else:
        cgst_minor = total_tax_minor // 2
        sgst_minor = total_tax_minor - cgst_minor
    if total_tax_minor <= 0:
        raise HTTPException(status_code=422, detail="GST amount rounds to zero; increase the taxable amount or rate.")
    tax_lines = []
    if cgst_minor:
        tax_lines.append((str(data.get("cgst_account_code") or ""), cgst_minor))
    if sgst_minor:
        tax_lines.append((str(data.get("sgst_account_code") or ""), sgst_minor))
    return total_tax_minor, tax_lines


def make_posting_lines(
    module_id: str,
    record: ModuleRecord,
    accounts: dict[str, ModuleRecord],
) -> tuple[date, str, list[dict[str, object]]]:
    data = record.data
    posting_date = parse_posting_date(data.get("posting_date") or data.get("invoice_date"))
    document_no_value = data.get("document_no") or data.get("invoice_no") or record.name
    document_no = str(document_no_value).strip()[:160] or record.name
    descriptions: list[dict[str, object]] = []

    if module_id == "journal-entry":
        raw_lines = data.get("lines")
        if not isinstance(raw_lines, list) or len(raw_lines) < 2:
            raise HTTPException(status_code=422, detail="A journal entry needs at least two posting lines.")
        for index, raw_line in enumerate(raw_lines, start=1):
            if not isinstance(raw_line, dict):
                raise HTTPException(status_code=422, detail="Each journal line must be an object.")
            debit_minor = amount_to_minor(raw_line.get("debit", 0))
            credit_minor = amount_to_minor(raw_line.get("credit", 0))
            if (debit_minor == 0) == (credit_minor == 0):
                raise HTTPException(status_code=422, detail="Each journal line must have either a debit or a credit.")
            account = require_account(accounts, raw_line.get("account_code"), {"Asset", "Liability", "Equity", "Income", "Expense"})
            descriptions.append(
                {
                    "line_number": index,
                    "account": account,
                    "debit_minor": debit_minor,
                    "credit_minor": credit_minor,
                    "description": str(raw_line.get("description") or record.name)[:500],
                }
            )
    elif module_id in {"ap", "ar"}:
        amount_minor = amount_to_minor(data.get("amount"))
        if amount_minor <= 0:
            raise HTTPException(status_code=422, detail="Invoice amount must be greater than zero.")
        tax_minor, tax_lines = calculate_invoice_tax(data, amount_minor)
        if module_id == "ap":
            offset_type, control_type = "Expense", "Liability"
            tax_type = "Asset"
            offset_debit, control_credit = amount_minor, amount_minor + tax_minor
        else:
            offset_type, control_type = "Income", "Asset"
            tax_type = "Liability"
            offset_debit, control_credit = amount_minor + tax_minor, amount_minor
        offset_account = require_account(accounts, data.get("account_code"), {offset_type})
        control_account = require_account(accounts, data.get("control_account_code"), {control_type})
        descriptions = []
        if module_id == "ap":
            descriptions.append({
                "line_number": 1,
                "account": offset_account,
                "debit_minor": offset_debit,
                "credit_minor": 0,
                "description": record.name,
            })
            for index, (tax_code, tax_line_minor) in enumerate(tax_lines, start=2):
                tax_account = require_account(accounts, tax_code, {tax_type})
                descriptions.append({
                    "line_number": index,
                    "account": tax_account,
                    "debit_minor": tax_line_minor,
                    "credit_minor": 0,
                    "description": f"{record.name} GST",
                })
            descriptions.append({
                "line_number": len(descriptions) + 1,
                "account": control_account,
                "debit_minor": 0,
                "credit_minor": control_credit,
                "description": record.name,
            })
        else:
            descriptions.append({
                "line_number": 1,
                "account": control_account,
                "debit_minor": offset_debit,
                "credit_minor": 0,
                "description": record.name,
            })
            descriptions.append({
                "line_number": 2,
                "account": offset_account,
                "debit_minor": 0,
                "credit_minor": amount_minor,
                "description": record.name,
            })
            for index, (tax_code, tax_line_minor) in enumerate(tax_lines, start=3):
                tax_account = require_account(accounts, tax_code, {tax_type})
                descriptions.append({
                    "line_number": index,
                    "account": tax_account,
                    "debit_minor": 0,
                    "credit_minor": tax_line_minor,
                    "description": f"{record.name} GST",
                })
    else:
        raise HTTPException(status_code=400, detail="This module does not support ledger posting.")

    total_debits = sum(int(line["debit_minor"]) for line in descriptions)
    total_credits = sum(int(line["credit_minor"]) for line in descriptions)
    if total_debits <= 0 or total_debits != total_credits:
        raise HTTPException(status_code=422, detail="Posting lines must have equal, non-zero debit and credit totals.")
    return posting_date, document_no, descriptions


def write_ledger_entries(
    db: Session,
    owner_id: int,
    record: ModuleRecord,
    posting_date: date,
    document_no: str,
    lines: list[dict[str, object]],
) -> None:
    for line in lines:
        account = line["account"]
        if not isinstance(account, ModuleRecord):
            raise RuntimeError("Posting line account was not resolved.")
        db.add(
            LedgerEntry(
                owner_id=owner_id,
                source_module=record.module_id,
                source_record_id=record.id,
                line_number=int(line["line_number"]),
                account_code=str(account.data["account_code"]).upper(),
                account_name=account.name,
                account_type=str(account.data["account_type"]),
                posting_date=posting_date,
                document_no=document_no,
                description=str(line["description"]),
                debit_minor=int(line["debit_minor"]),
                credit_minor=int(line["credit_minor"]),
            )
        )


def get_trial_balance(
    db: Session,
    owner_id: int,
    start_date: date,
    end_date: date,
) -> TrialBalanceOut:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date.")
    accounts = get_accounts_by_code(db, owner_id)
    entries = db.scalars(
        select(LedgerEntry)
        .where(
            LedgerEntry.owner_id == owner_id,
            LedgerEntry.posting_date <= end_date,
        )
        .order_by(LedgerEntry.posting_date, LedgerEntry.id)
    ).all()
    balances: dict[str, dict[str, object]] = {
        code: {
            "opening_debit_minor": 0,
            "opening_credit_minor": 0,
            "period_debit_minor": 0,
            "period_credit_minor": 0,
            "latest": None,
        }
        for code in accounts
    }
    for entry in entries:
        row = balances.setdefault(
            entry.account_code,
            {
                "opening_debit_minor": 0,
                "opening_credit_minor": 0,
                "period_debit_minor": 0,
                "period_credit_minor": 0,
                "latest": None,
            },
        )
        prefix = "opening" if entry.posting_date < start_date else "period"
        row[f"{prefix}_debit_minor"] += entry.debit_minor
        row[f"{prefix}_credit_minor"] += entry.credit_minor
        row["latest"] = entry

    output_rows = []
    for code, row in balances.items():
        account = accounts.get(code)
        latest = row["latest"]
        account_name = account.name if account else (latest.account_name if latest else code)
        account_type = str(account.data.get("account_type")) if account else (latest.account_type if latest else "Unknown")
        closing_net = (
            int(row["opening_debit_minor"]) - int(row["opening_credit_minor"])
            + int(row["period_debit_minor"]) - int(row["period_credit_minor"])
        )
        opening_net = int(row["opening_debit_minor"]) - int(row["opening_credit_minor"])
        output_rows.append(
            LedgerAccountOut(
                account_code=code,
                account_name=account_name,
                account_type=account_type,
                opening_debit_minor=max(opening_net, 0),
                opening_credit_minor=max(-opening_net, 0),
                period_debit_minor=row["period_debit_minor"],
                period_credit_minor=row["period_credit_minor"],
                closing_debit_minor=max(closing_net, 0),
                closing_credit_minor=max(-closing_net, 0),
            )
        )
    output_rows.sort(key=lambda row: row.account_code)
    total_debits = sum(row.closing_debit_minor for row in output_rows)
    total_credits = sum(row.closing_credit_minor for row in output_rows)
    return TrialBalanceOut(
        start_date=start_date,
        end_date=end_date,
        accounts=output_rows,
        total_debit_minor=total_debits,
        total_credit_minor=total_credits,
        balanced=total_debits == total_credits,
    )


def require_open_period(db: Session, posting_date: date) -> None:
    period = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.start_date <= posting_date, FiscalPeriod.end_date >= posting_date)
    ).first()
    if period is None:
        raise HTTPException(status_code=422, detail="Posting date is outside a configured fiscal period.")
    fiscal_period, fiscal_year = period
    if fiscal_year.status != "ACTIVE":
        raise HTTPException(status_code=422, detail="The fiscal year for this posting date is not active.")
    if fiscal_period.status != "OPEN":
        raise HTTPException(status_code=409, detail="The fiscal period for this posting date is closed.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Stackly OneERP Fiscal Year API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=AuthOut, status_code=201)
def register(payload: RegisterIn, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    token = create_session(db, user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from error
    response.set_cookie(
        "stackly_session",
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )
    return AuthOut(user=user)


@app.post("/api/auth/login", response_model=AuthOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    token = create_session(db, user)
    db.commit()
    response.set_cookie(
        "stackly_session",
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        path="/",
    )
    return AuthOut(user=user)


@app.get("/api/auth/me", response_model=UserOut)
def current_user(user: User = Depends(get_current_user)):
    return user


@app.post("/api/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else request.cookies.get("stackly_session")
    if token:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
        if auth_session:
            db.delete(auth_session)
            db.commit()
    response.delete_cookie("stackly_session", path="/", httponly=True, samesite="lax")
    return None


@app.get("/api/modules/{module_id}/records", response_model=list[ModuleRecordOut])
def list_module_records(
    module_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in MODULE_IDS:
        raise HTTPException(status_code=404, detail="Module not found.")
    records = db.scalars(
        select(ModuleRecord)
        .where(ModuleRecord.owner_id == user.id, ModuleRecord.module_id == module_id)
        .order_by(ModuleRecord.updated_at.desc(), ModuleRecord.id.desc())
    ).all()
    return records


@app.post(
    "/api/modules/{module_id}/records",
    response_model=ModuleRecordOut,
    status_code=status.HTTP_201_CREATED,
)
def create_module_record(
    module_id: str,
    payload: ModuleRecordCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in MODULE_IDS:
        raise HTTPException(status_code=404, detail="Module not found.")
    if module_id in {"journal-entry", "ap", "ar"} and payload.status == "Posted":
        raise HTTPException(status_code=422, detail="Use the Post action to create ledger entries.")
    if module_id == "fixed-assets" and payload.status == "Posted":
        raise HTTPException(status_code=422, detail="Use the acquisition action to post this asset to the ledger.")
    record_data = payload.data
    if module_id == "chart-of-accounts":
        record_data = validate_chart_account(db, user.id, payload.status, record_data)
    record = ModuleRecord(
        owner_id=user.id,
        module_id=module_id,
        name=payload.name,
        status=payload.status,
        data=record_data,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.patch("/api/modules/{module_id}/records/{record_id}", response_model=ModuleRecordOut)
def update_module_record(
    module_id: str,
    record_id: int,
    payload: ModuleRecordUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in MODULE_IDS:
        raise HTTPException(status_code=404, detail="Module not found.")
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record.status == "Posted":
        raise HTTPException(status_code=409, detail="Posted records are locked against changes.")
    updates = payload.model_dump(exclude_unset=True)
    if module_id == "chart-of-accounts":
        account_code = str(record.data.get("account_code", "")).strip().upper()
        if db.scalar(
            select(LedgerEntry.id).where(
                LedgerEntry.owner_id == user.id,
                LedgerEntry.account_code == account_code,
            ).limit(1)
        ):
            raise HTTPException(status_code=409, detail="Accounts with posted ledger activity are locked against changes.")
        next_status = str(updates.get("status", record.status))
        next_data = updates.get("data", record.data)
        if not isinstance(next_data, dict):
            raise HTTPException(status_code=422, detail="Chart-of-accounts data must be an object.")
        updates["data"] = validate_chart_account(
            db,
            user.id,
            next_status,
            next_data,
            exclude_id=record.id,
        )
    if module_id == "fixed-assets" and db.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.owner_id == user.id,
            LedgerEntry.source_module == module_id,
            LedgerEntry.source_record_id == record.id,
        ).limit(1)
    ):
        raise HTTPException(status_code=409, detail="Assets with ledger entries are locked against changes.")
    for field, value in updates.items():
        if field == "status" and value == "Posted" and module_id in {"journal-entry", "ap", "ar"}:
            raise HTTPException(status_code=422, detail="Use the Post action to create ledger entries.")
        if field == "status" and value == "Posted" and module_id == "fixed-assets":
            raise HTTPException(status_code=422, detail="Use the acquisition action to post this asset to the ledger.")
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


@app.delete("/api/modules/{module_id}/records/{record_id}", status_code=204)
def delete_module_record(
    module_id: str,
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in MODULE_IDS:
        raise HTTPException(status_code=404, detail="Module not found.")
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record.status == "Posted":
        raise HTTPException(status_code=409, detail="Posted records cannot be deleted.")
    if module_id == "chart-of-accounts":
        account_code = str(record.data.get("account_code", "")).strip().upper()
        if db.scalar(
            select(LedgerEntry.id).where(
                LedgerEntry.owner_id == user.id,
                LedgerEntry.account_code == account_code,
            ).limit(1)
        ):
            raise HTTPException(status_code=409, detail="Accounts with posted ledger activity cannot be deleted.")
    if module_id == "fixed-assets" and db.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.owner_id == user.id,
            LedgerEntry.source_module == module_id,
            LedgerEntry.source_record_id == record.id,
        ).limit(1)
    ):
        raise HTTPException(status_code=409, detail="Assets with ledger entries cannot be deleted.")
    db.delete(record)
    db.commit()
    return None


@app.get("/api/accounting/accounts", response_model=list[AccountOptionOut])
def list_posting_accounts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = get_accounts_by_code(db, user.id)
    return [
        AccountOptionOut(
            account_code=code,
            account_name=record.name,
            account_type=str(record.data.get("account_type", "Unknown")),
            status=record.status,
        )
        for code, record in sorted(accounts.items())
    ]


@app.get("/api/fiscal-periods", response_model=list[FiscalPeriodDetailOut])
def list_fiscal_periods(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .order_by(FiscalYear.start_date.desc(), FiscalPeriod.period_number)
    ).all()
    return [serialize_fiscal_period_detail(period, year) for period, year in rows]


@app.post("/api/fiscal-periods/{period_id}/close", response_model=FiscalPeriodDetailOut)
def close_fiscal_period(
    period_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    period = db.get(FiscalPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Fiscal period not found.")
    period.status = "CLOSED"
    db.commit()
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    return serialize_fiscal_period_detail(*row)


@app.post("/api/fiscal-periods/{period_id}/reopen", response_model=FiscalPeriodDetailOut)
def reopen_fiscal_period(
    period_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    period = db.get(FiscalPeriod, period_id)
    if period is None:
        raise HTTPException(status_code=404, detail="Fiscal period not found.")
    period.status = "OPEN"
    db.commit()
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    return serialize_fiscal_period_detail(*row)


@app.post(
    "/api/modules/{module_id}/records/{record_id}/post",
    response_model=ModuleRecordOut,
)
def post_accounting_record(
    module_id: str,
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in {"journal-entry", "ap", "ar"}:
        raise HTTPException(status_code=404, detail="This module does not support ledger posting.")
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record.status == "Posted":
        raise HTTPException(status_code=409, detail="This record has already been posted.")
    posting_date, document_no, lines = make_posting_lines(
        module_id,
        record,
        get_accounts_by_code(db, user.id),
    )
    require_open_period(db, posting_date)
    write_ledger_entries(db, user.id, record, posting_date, document_no, lines)
    if module_id in {"ap", "ar"}:
        taxable_minor = amount_to_minor(record.data.get("amount"))
        tax_minor, _ = calculate_invoice_tax(record.data, taxable_minor)
        record.data = {
            **record.data,
            "taxable_amount_minor": taxable_minor,
            "tax_amount_minor": tax_minor,
        }
    record.status = "Posted"
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This source record already has ledger entries.") from error
    db.refresh(record)
    return record


@app.post("/api/modules/fixed-assets/records/{record_id}/post-acquisition", response_model=ModuleRecordOut)
def post_fixed_asset_acquisition(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == "fixed-assets",
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found.")
    existing_entries = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.owner_id == user.id,
            LedgerEntry.source_module == "fixed-assets",
            LedgerEntry.source_record_id == record.id,
        )
    ).all()
    if existing_entries:
        raise HTTPException(status_code=409, detail="This asset already has ledger entries.")
    posting_date = parse_posting_date(record.data.get("acquisition_date"))
    cost_minor = amount_to_minor(record.data.get("cost"))
    if cost_minor <= 0:
        raise HTTPException(status_code=422, detail="Asset cost must be greater than zero.")
    accounts = get_accounts_by_code(db, user.id)
    asset_account = require_account(accounts, record.data.get("asset_account_code"), {"Asset"})
    offset_account = require_account(
        accounts,
        record.data.get("acquisition_offset_account_code"),
        {"Asset", "Liability", "Equity"},
    )
    if asset_account.id == offset_account.id:
        raise HTTPException(status_code=422, detail="Choose a different acquisition offset account.")
    require_open_period(db, posting_date)
    write_ledger_entries(
        db,
        user.id,
        record,
        posting_date,
        str(record.data.get("asset_code") or record.name)[:160],
        [
            {
                "line_number": 1,
                "account": asset_account,
                "debit_minor": cost_minor,
                "credit_minor": 0,
                "description": f"{record.name} acquisition",
            },
            {
                "line_number": 2,
                "account": offset_account,
                "debit_minor": 0,
                "credit_minor": cost_minor,
                "description": f"{record.name} acquisition",
            },
        ],
    )
    record.status = "Active"
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This asset already has ledger entries.") from error
    db.refresh(record)
    return record


@app.post("/api/modules/fixed-assets/records/{record_id}/depreciate", response_model=ModuleRecordOut)
def depreciate_fixed_asset(
    record_id: int,
    period_end: date = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == "fixed-assets",
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found.")
    if record.status != "Active":
        raise HTTPException(status_code=409, detail="Post the asset acquisition before depreciating it.")
    if period_end.day != calendar.monthrange(period_end.year, period_end.month)[1]:
        raise HTTPException(status_code=422, detail="Depreciation date must be the last day of a month.")
    acquired_on = parse_posting_date(record.data.get("acquisition_date"))
    elapsed_months = (period_end.year - acquired_on.year) * 12 + period_end.month - acquired_on.month
    if elapsed_months <= 0:
        raise HTTPException(status_code=422, detail="Depreciation starts in the month after acquisition.")

    source_entries = db.scalars(
        select(LedgerEntry)
        .where(
            LedgerEntry.owner_id == user.id,
            LedgerEntry.source_module == "fixed-assets",
            LedgerEntry.source_record_id == record.id,
        )
        .order_by(LedgerEntry.line_number)
    ).all()
    depreciation_entries = [entry for entry in source_entries if entry.line_number >= 3]
    if len(depreciation_entries) % 2:
        raise HTTPException(status_code=409, detail="Existing depreciation entries are incomplete; contact an administrator.")
    if not source_entries:
        raise HTTPException(status_code=409, detail="Post the asset acquisition before depreciating it.")
    if elapsed_months != len(depreciation_entries) // 2 + 1:
        raise HTTPException(status_code=409, detail="Depreciation must be posted one month at a time in sequence.")

    cost_minor = amount_to_minor(record.data.get("cost"))
    salvage_minor = amount_to_minor(record.data.get("salvage_value") or 0)
    if salvage_minor > cost_minor:
        raise HTTPException(status_code=422, detail="Salvage value cannot exceed asset cost.")
    try:
        useful_life = Decimal(str(record.data.get("useful_life_years")))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Useful life must be a positive whole number of years.")
    if not useful_life.is_finite() or useful_life <= 0 or useful_life != useful_life.to_integral_value():
        raise HTTPException(status_code=422, detail="Useful life must be a positive whole number of years.")
    useful_months = int(useful_life) * 12
    depreciable_minor = cost_minor - salvage_minor
    if depreciable_minor <= 0 or elapsed_months > useful_months:
        raise HTTPException(status_code=409, detail="The asset has no remaining depreciable value.")
    monthly_base, extra_cents = divmod(depreciable_minor, useful_months)
    depreciation_minor = monthly_base + (1 if elapsed_months <= extra_cents else 0)
    previous_depreciation_minor = sum(entry.debit_minor for entry in depreciation_entries)
    depreciation_minor = min(depreciation_minor, depreciable_minor - previous_depreciation_minor)
    if depreciation_minor <= 0:
        raise HTTPException(status_code=409, detail="The asset has no remaining depreciable value.")

    accounts = get_accounts_by_code(db, user.id)
    accumulated_account = require_account(
        accounts,
        record.data.get("accumulated_depreciation_account_code"),
        {"Asset"},
    )
    expense_account = require_account(
        accounts,
        record.data.get("depreciation_expense_account_code"),
        {"Expense"},
    )
    require_open_period(db, period_end)
    document_no = f"DEP-{record.data.get('asset_code') or record.id}-{period_end:%Y%m}"
    first_line = 3 + len(depreciation_entries)
    write_ledger_entries(
        db,
        user.id,
        record,
        period_end,
        document_no,
        [
            {
                "line_number": first_line,
                "account": expense_account,
                "debit_minor": depreciation_minor,
                "credit_minor": 0,
                "description": f"{record.name} straight-line depreciation",
            },
            {
                "line_number": first_line + 1,
                "account": accumulated_account,
                "debit_minor": 0,
                "credit_minor": depreciation_minor,
                "description": f"{record.name} accumulated depreciation",
            },
        ],
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Depreciation for this asset and period already exists.") from error
    db.refresh(record)
    return record


@app.get("/api/accounting/trial-balance", response_model=TrialBalanceOut)
def trial_balance(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    default_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    return get_trial_balance(
        db,
        user.id,
        start_date or default_start,
        end_date or today,
    )


@app.get("/api/accounting/general-ledger", response_model=list[LedgerLineOut])
def general_ledger(
    account_code: str | None = Query(default=None, max_length=40),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(LedgerEntry).where(LedgerEntry.owner_id == user.id)
    if account_code:
        statement = statement.where(LedgerEntry.account_code == account_code.strip().upper())
    if start_date:
        statement = statement.where(LedgerEntry.posting_date >= start_date)
    if end_date:
        statement = statement.where(LedgerEntry.posting_date <= end_date)
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date.")
    return db.scalars(statement.order_by(LedgerEntry.posting_date, LedgerEntry.id)).all()


@app.get("/api/accounting/budget-variance", response_model=list[BudgetVarianceOut])
def budget_variance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    budgets = db.scalars(
        select(ModuleRecord)
        .where(
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == "budgeting",
            ModuleRecord.status == "Approved",
        )
        .order_by(ModuleRecord.name)
    ).all()
    accounts = get_accounts_by_code(db, user.id)
    output: list[BudgetVarianceOut] = []
    for budget in budgets:
        account_code = budget.data.get("account_code")
        if not isinstance(account_code, str) or not account_code.strip():
            continue
        account_code = account_code.strip().upper()
        account = accounts.get(account_code)
        if account is None or account.data.get("account_type") != "Expense":
            continue
        start = parse_posting_date(budget.data.get("start_date"))
        end = parse_posting_date(budget.data.get("end_date"))
        if end < start:
            raise HTTPException(status_code=422, detail=f"Budget {budget.name} has an end date before its start date.")
        budget_minor = amount_to_minor(budget.data.get("amount"))
        actual = db.scalar(
            select(
                func.coalesce(func.sum(LedgerEntry.debit_minor - LedgerEntry.credit_minor), 0)
            ).where(
                LedgerEntry.owner_id == user.id,
                LedgerEntry.account_code == account_code,
                LedgerEntry.posting_date >= start,
                LedgerEntry.posting_date <= end,
            )
        )
        actual_minor = int(actual or 0)
        output.append(
            BudgetVarianceOut(
                record_id=budget.id,
                budget_name=budget.name,
                account_code=account_code,
                account_name=account.name,
                start_date=start,
                end_date=end,
                budget_minor=budget_minor,
                actual_minor=actual_minor,
                variance_minor=budget_minor - actual_minor,
            )
        )
    return output


@app.get("/api/accounting/financial-report")
def financial_report(
    report_type: Literal["income_statement", "balance_sheet"] = Query(...),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    default_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    report_start = start_date or default_start
    report_end = end_date or today
    if report_type == "income_statement" and report_end < report_start:
        raise HTTPException(status_code=422, detail="End date must be on or after start date.")

    statement = select(LedgerEntry).where(
        LedgerEntry.owner_id == user.id,
        LedgerEntry.posting_date <= report_end,
    )
    if report_type == "income_statement":
        statement = statement.where(LedgerEntry.posting_date >= report_start)
    entries = db.scalars(statement.order_by(LedgerEntry.posting_date, LedgerEntry.id)).all()
    balances: dict[str, dict[str, object]] = {}
    for entry in entries:
        row = balances.setdefault(
            entry.account_code,
            {
                "account_name": entry.account_name,
                "account_type": entry.account_type,
                "debit_minor": 0,
                "credit_minor": 0,
            },
        )
        row["debit_minor"] = int(row["debit_minor"]) + entry.debit_minor
        row["credit_minor"] = int(row["credit_minor"]) + entry.credit_minor

    lines: list[dict[str, object]] = []
    total_income = 0
    total_expenses = 0
    total_assets = 0
    total_liabilities = 0
    total_equity = 0
    for code, row in sorted(balances.items()):
        account_type = str(row["account_type"])
        debit = int(row["debit_minor"])
        credit = int(row["credit_minor"])
        if report_type == "income_statement":
            if account_type == "Income":
                amount = credit - debit
                total_income += amount
            elif account_type == "Expense":
                amount = debit - credit
                total_expenses += amount
            else:
                continue
        elif account_type == "Asset":
            amount = debit - credit
            total_assets += amount
        elif account_type == "Liability":
            amount = credit - debit
            total_liabilities += amount
        elif account_type == "Equity":
            amount = credit - debit
            total_equity += amount
        elif account_type == "Income":
            total_income += credit - debit
            continue
        elif account_type == "Expense":
            total_expenses += debit - credit
            continue
        else:
            continue
        lines.append({
            "account_code": code,
            "account_name": row["account_name"],
            "account_type": account_type,
            "amount_minor": amount,
        })

    if report_type == "income_statement":
        net_income = total_income - total_expenses
        return {
            "report_type": report_type,
            "start_date": report_start,
            "end_date": report_end,
            "currency": "INR",
            "lines": lines,
            "total_income_minor": total_income,
            "total_expenses_minor": total_expenses,
            "net_income_minor": net_income,
        }

    current_earnings = total_income - total_expenses
    if current_earnings:
        lines.append({
            "account_code": "CURRENT-EARNINGS",
            "account_name": "Current earnings (unclosed)",
            "account_type": "Equity",
            "amount_minor": current_earnings,
        })
    return {
        "report_type": report_type,
        "as_of_date": report_end,
        "currency": "INR",
        "lines": lines,
        "total_assets_minor": total_assets,
        "total_liabilities_minor": total_liabilities,
        "total_equity_minor": total_equity + current_earnings,
        "total_liabilities_and_equity_minor": total_liabilities + total_equity + current_earnings,
        "balanced": total_assets == total_liabilities + total_equity + current_earnings,
    }


@app.get("/api/accounting/gst-summary")
def gst_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invoices = db.scalars(
        select(ModuleRecord).where(
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id.in_(("ap", "ar")),
            ModuleRecord.status == "Posted",
        )
    ).all()
    totals: dict[tuple[str, str, str], dict[str, int]] = {}
    for invoice in invoices:
        data = invoice.data
        tax_minor = data.get("tax_amount_minor", 0)
        if not isinstance(tax_minor, int) or tax_minor <= 0:
            continue
        mode = str(data.get("tax_mode", "Unknown"))
        rate = str(data.get("tax_rate", "0"))
        direction = "input" if invoice.module_id == "ap" else "output"
        key = (direction, mode, rate)
        row = totals.setdefault(key, {"taxable_minor": 0, "tax_minor": 0, "invoice_count": 0})
        row["taxable_minor"] += int(data.get("taxable_amount_minor", 0))
        row["tax_minor"] += tax_minor
        row["invoice_count"] += 1
    return [
        {
            "direction": direction,
            "tax_mode": mode,
            "rate": rate,
            **values,
        }
        for (direction, mode, rate), values in sorted(totals.items())
    ]


@app.get("/api/accounting/dashboard-summary")
def dashboard_summary(
    period: Literal["This Year", "This Quarter", "This Month"] = Query(default="This Year"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    fiscal_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    if period == "This Month":
        start_date = today.replace(day=1)
    elif period == "This Quarter":
        quarter_offset = ((today.year - fiscal_start.year) * 12 + today.month - fiscal_start.month) // 3
        start_month_index = fiscal_start.year * 12 + fiscal_start.month - 1 + quarter_offset * 3
        start_date = date(start_month_index // 12, start_month_index % 12 + 1, 1)
    else:
        start_date = fiscal_start

    company_count = db.scalar(
        select(func.count(ModuleRecord.id)).where(
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == "company",
        )
    ) or 0
    account_count = db.scalar(
        select(func.count(ModuleRecord.id)).where(
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == "chart-of-accounts",
            ModuleRecord.status == "Active",
        )
    ) or 0
    active_year_count = db.scalar(
        select(func.count(FiscalYear.id)).where(FiscalYear.status == "ACTIVE")
    ) or 0
    open_period_count = db.scalar(
        select(func.count(FiscalPeriod.id))
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.status == "OPEN", FiscalYear.status == "ACTIVE")
    ) or 0
    period_entries = db.scalars(
        select(LedgerEntry).where(
            LedgerEntry.owner_id == user.id,
            LedgerEntry.posting_date >= start_date,
            LedgerEntry.posting_date <= today,
        )
    ).all()
    total_income_minor = sum(
        entry.credit_minor - entry.debit_minor
        for entry in period_entries
        if entry.account_type == "Income"
    )
    total_expenses_minor = sum(
        entry.debit_minor - entry.credit_minor
        for entry in period_entries
        if entry.account_type == "Expense"
    )

    recent_entries = db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.owner_id == user.id)
        .order_by(LedgerEntry.posting_date.desc(), LedgerEntry.id.desc())
        .limit(300)
    ).all()
    grouped: dict[tuple[str, int, str], dict[str, object]] = {}
    for entry in recent_entries:
        key = (entry.source_module, entry.source_record_id, entry.document_no)
        row = grouped.setdefault(
            key,
            {
                "date": entry.posting_date,
                "doc": entry.document_no,
                "module": entry.source_module,
                "description": entry.description,
                "debit_minor": 0,
                "credit_minor": 0,
            },
        )
        row["debit_minor"] = int(row["debit_minor"]) + entry.debit_minor
        row["credit_minor"] = int(row["credit_minor"]) + entry.credit_minor
    module_labels = {
        "journal-entry": "Journal Entry",
        "ap": "Accounts Payable",
        "ar": "Accounts Receivable",
        "fixed-assets": "Fixed Assets",
    }
    recent_transactions = [
        {
            "date": row["date"],
            "doc": row["doc"],
            "module": module_labels.get(str(row["module"]), str(row["module"])),
            "description": row["description"],
            "amount_minor": max(int(row["debit_minor"]), int(row["credit_minor"])),
            "status": "Posted",
        }
        for row in list(grouped.values())[:8]
    ]
    return {
        "period": period,
        "start_date": start_date,
        "end_date": today,
        "kpis": {
            "companies": int(company_count),
            "years": int(active_year_count),
            "periods": int(open_period_count),
            "accounts": int(account_count),
        },
        "financial_summary": {
            "total_income_minor": total_income_minor,
            "total_expenses_minor": total_expenses_minor,
            "net_income_minor": total_income_minor - total_expenses_minor,
        },
        "recent_transactions": recent_transactions,
    }


@app.get("/")
def api_info():
    index_file = FRONTEND_DIST / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)
    return {
        "name": app.title,
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
        "fiscal_years": "/api/fiscal-years",
    }


@app.get("/api/fiscal-years", response_model=list[FiscalYearOut])
def list_fiscal_years(
    company: str | None = Query(default=None, max_length=30),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(FiscalYear).order_by(FiscalYear.start_date.desc(), FiscalYear.code)
    if company:
        statement = statement.where(FiscalYear.company_code == company.strip().upper())
    years = db.scalars(statement).all()
    return [serialize_year(year, include_periods=False) for year in years]


@app.post("/api/fiscal-years", response_model=FiscalYearOut, status_code=201)
def create_fiscal_year(
    payload: FiscalYearCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    duplicate_code = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.company_code == payload.company,
            FiscalYear.code == payload.code,
        ).limit(1)
    )
    if duplicate_code:
        raise HTTPException(status_code=409, detail="A fiscal year with this company and code already exists.")

    overlapping = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.company_code == payload.company,
            FiscalYear.start_date <= payload.end,
            FiscalYear.end_date >= payload.start,
        ).limit(1)
    )
    if overlapping:
        raise HTTPException(status_code=409, detail="This date range overlaps an existing fiscal year for the company.")

    year = FiscalYear(
        company_code=payload.company,
        code=payload.code,
        name=payload.name,
        variant=payload.variant,
        start_date=payload.start,
        end_date=payload.end,
        period_count=payload.period_count,
        description=payload.description,
        status="DRAFT",
        periods=generate_periods(payload.start, payload.end),
    )
    db.add(year)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="A fiscal year with this company and code already exists.") from error
    db.refresh(year)
    return serialize_year(year)


@app.get("/api/fiscal-years/{fiscal_year_id}", response_model=FiscalYearOut)
def get_fiscal_year(
    fiscal_year_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    year = db.scalar(
        select(FiscalYear)
        .options(selectinload(FiscalYear.periods))
        .where(FiscalYear.id == fiscal_year_id)
    )
    if year is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    return serialize_year(year)


@app.post("/api/fiscal-years/{fiscal_year_id}/activate", response_model=FiscalYearOut)
def activate_fiscal_year(
    fiscal_year_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    year = db.scalar(
        select(FiscalYear)
        .options(selectinload(FiscalYear.periods))
        .where(FiscalYear.id == fiscal_year_id)
        .with_for_update()
    )
    if year is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    if year.status == "ACTIVE":
        return serialize_year(year)

    existing_active = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.company_code == year.company_code,
            FiscalYear.status == "ACTIVE",
            FiscalYear.id != year.id,
        ).limit(1)
    )
    if existing_active:
        raise HTTPException(status_code=409, detail="Another fiscal year for this company is already active.")

    year.status = "ACTIVE"
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="The fiscal year could not be activated.") from error
    db.refresh(year)
    return serialize_year(year)


if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend_assets")

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(FRONTEND_DIST / "favicon.svg")

    @app.get("/icons.svg")
    def icons():
        return FileResponse(FRONTEND_DIST / "icons.svg")

    @app.get("/{path:path}")
    def catch_all(path: str):
        frontend_root = FRONTEND_DIST.resolve()
        requested = (frontend_root / path).resolve()
        if requested.is_relative_to(frontend_root) and requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
