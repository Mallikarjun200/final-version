import calendar
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import ssl
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
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
    inspect,
    select,
    text,
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
logger = logging.getLogger(__name__)


class FiscalYear(Base):
    __tablename__ = "fiscal_years"
    __table_args__ = (
        UniqueConstraint("owner_id", "company_code", "code", name="uq_fiscal_year_company_code"),
        UniqueConstraint("owner_id", "active_company_code", name="uq_fiscal_year_active_company"),
        CheckConstraint("start_date < end_date", name="ck_fiscal_year_dates"),
        CheckConstraint("variant IN ('APR_MAR', 'JAN_DEC')", name="ck_fiscal_year_variant"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE')", name="ck_fiscal_year_status"),
        CheckConstraint("period_count = 12", name="ck_fiscal_year_period_count"),
        Index("ix_fiscal_year_company_dates", "company_code", "start_date", "end_date"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
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


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_user_created", "user_id", "created_at"),)

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "member_user_id", name="uq_workspace_member"),
        CheckConstraint("role IN ('admin', 'requester', 'approver')", name="ck_workspace_member_role"),
    )

    id = Column(Integer, primary_key=True)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    member_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


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


class InvoiceSettlement(Base):
    __tablename__ = "invoice_settlements"
    __table_args__ = (
        UniqueConstraint("owner_id", "module_id", "payment_reference", name="uq_settlement_payment_reference"),
        Index("ix_settlement_owner_invoice", "owner_id", "invoice_record_id"),
        CheckConstraint("module_id IN ('ap', 'ar')", name="ck_settlement_module"),
        CheckConstraint("amount_minor > 0", name="ck_settlement_amount"),
    )

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invoice_record_id = Column(Integer, ForeignKey("module_records.id", ondelete="RESTRICT"), nullable=False)
    module_id = Column(String(40), nullable=False)
    payment_reference = Column(String(100), nullable=False)
    posting_date = Column(Date, nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    cash_account_code = Column(String(40), nullable=False)
    cash_account_name = Column(String(160), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class ApprovalEvent(Base):
    __tablename__ = "approval_events"
    __table_args__ = (
        Index("ix_approval_record_history", "workspace_owner_id", "module_id", "record_id", "id"),
    )

    id = Column(Integer, primary_key=True)
    workspace_owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(String(40), nullable=False)
    record_id = Column(Integer, ForeignKey("module_records.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(20), nullable=False)
    comment = Column(String(500), nullable=True)
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


class FiscalPeriodUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    start_date: date
    end_date: date

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Period end date must be on or after its start date.")
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


class ForgotPasswordIn(BaseModel):
    email: str = Field(min_length=5, max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=20, max_length=128)
    password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str


class WorkspaceOut(BaseModel):
    id: int
    name: str
    role: Literal["admin", "requester", "approver"]


class WorkspaceMemberCreate(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    role: Literal["requester", "approver", "admin"]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class WorkspaceMemberOut(BaseModel):
    user_id: int
    email: str
    display_name: str
    role: Literal["admin", "requester", "approver"]


class ApprovalActionIn(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, value):
        return value.strip() if isinstance(value, str) else value


class ApprovalEventOut(BaseModel):
    id: int
    action: str
    comment: str | None
    created_at: datetime
    actor_email: str
    actor_name: str


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


class InvoicePaymentCreate(BaseModel):
    payment_reference: str = Field(min_length=1, max_length=100)
    posting_date: date
    amount: Decimal = Field(gt=0)
    cash_account_code: str = Field(min_length=1, max_length=40)

    @field_validator("payment_reference", "cash_account_code", mode="before")
    @classmethod
    def strip_fields(cls, value):
        return value.strip() if isinstance(value, str) else value


class InvoicePaymentOut(BaseModel):
    id: int
    payment_reference: str
    posting_date: date
    amount_minor: int
    cash_account_code: str
    cash_account_name: str


class InvoiceSettlementOut(BaseModel):
    invoice_record_id: int
    module_id: str
    invoice_total_minor: int
    paid_minor: int
    outstanding_minor: int
    settlement_status: Literal["Unpaid", "Partially Paid", "Paid"]
    payments: list[InvoicePaymentOut]


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


class FixedAssetDepreciationPeriodOut(BaseModel):
    period_end: date
    document_no: str
    amount_minor: int


class FixedAssetScheduleOut(BaseModel):
    record_id: int
    asset_name: str
    acquisition_date: date
    cost_minor: int
    salvage_minor: int
    useful_life_months: int
    monthly_depreciation_minor: int
    accumulated_depreciation_minor: int
    net_book_value_minor: int
    next_period_end: date | None
    posted_periods: list[FixedAssetDepreciationPeriodOut]


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


@dataclass(frozen=True)
class WorkspaceUser:
    id: int
    actor_id: int
    email: str
    display_name: str
    role: str


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
APPROVAL_MODULES = {"journal-entry", "ap", "ar", "fixed-assets", "budgeting"}


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


def utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def password_reset_mail_config() -> dict[str, str | int]:
    provider = os.getenv("SMTP_PROVIDER", "gmail").strip().lower()
    if provider not in {"custom", "gmail"}:
        raise HTTPException(status_code=503, detail="Password reset email provider is not supported.")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com" if provider == "gmail" else "").strip()
    default_port = "587"
    sender = os.getenv("SMTP_FROM_EMAIL", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if provider == "gmail":
        sender = sender or username
        if not username or not password:
            raise HTTPException(
                status_code=503,
                detail="Gmail password reset is not configured. Add SMTP_USERNAME and an SMTP_PASSWORD Google app password in Render.",
            )
    if not host or not sender:
        raise HTTPException(
            status_code=503,
            detail="Password reset email is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL.",
        )
    if bool(username) != bool(password):
        raise HTTPException(
            status_code=503,
            detail="Password reset email is misconfigured. Set both SMTP_USERNAME and SMTP_PASSWORD.",
        )
    try:
        port = int(os.getenv("SMTP_PORT", default_port))
    except ValueError as error:
        raise HTTPException(status_code=503, detail="SMTP_PORT must be a valid port number.") from error
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=503, detail="SMTP_PORT must be a valid port number.")
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "sender": sender,
        "app_base_url": os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
    }


def send_password_reset_email(
    recipient: str,
    reset_url: str,
    mail_config: dict[str, str | int],
) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your Stackly OneERP password"
    message["From"] = str(mail_config["sender"])
    message["To"] = recipient
    message.set_content(
        "We received a request to reset your Stackly OneERP password.\n\n"
        f"Use this link within 30 minutes to choose a new password:\n{reset_url}\n\n"
        "If you did not request a reset, you can ignore this email."
    )
    host = str(mail_config["host"])
    port = int(mail_config["port"])
    username = str(mail_config["username"])
    password = str(mail_config["password"])
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context()) as server:
            if username:
                server.login(username, password)
            server.send_message(message)
        return
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(message)


def deliver_password_reset_email(
    recipient: str,
    reset_url: str,
    mail_config: dict[str, str | int],
    reset_token_id: int,
) -> None:
    try:
        send_password_reset_email(recipient, reset_url, mail_config)
    except (OSError, smtplib.SMTPException):
        logger.exception("Failed to send a password reset email.")
        db = SessionLocal()
        try:
            reset_record = db.get(PasswordResetToken, reset_token_id)
            if reset_record:
                db.delete(reset_record)
                db.commit()
        finally:
            db.close()


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


def get_authenticated_user(
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


def get_current_user(
    user: User = Depends(get_authenticated_user),
    workspace_id: int | None = Header(default=None, alias="X-Workspace-ID"),
    db: Session = Depends(get_db),
) -> WorkspaceUser:
    memberships = db.scalars(
        select(WorkspaceMember).where(WorkspaceMember.member_user_id == user.id)
    ).all()
    if not memberships:
        membership = WorkspaceMember(
            owner_user_id=user.id,
            member_user_id=user.id,
            role="admin",
        )
        db.add(membership)
        db.commit()
        memberships = [membership]

    if workspace_id is None:
        if len(memberships) != 1:
            raise HTTPException(status_code=409, detail="Select a workspace before continuing.")
        membership = memberships[0]
    else:
        membership = next((item for item in memberships if item.owner_user_id == workspace_id), None)
        if membership is None:
            raise HTTPException(status_code=403, detail="You do not have access to this workspace.")

    return WorkspaceUser(
        id=membership.owner_user_id,
        actor_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
    )


def require_workspace_role(user: WorkspaceUser, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Your workspace role does not allow this action.")


def has_approval_event(db: Session, owner_id: int, module_id: str, record_id: int) -> bool:
    return db.scalar(
        select(ApprovalEvent.id)
        .where(
            ApprovalEvent.workspace_owner_id == owner_id,
            ApprovalEvent.module_id == module_id,
            ApprovalEvent.record_id == record_id,
            ApprovalEvent.action == "approve",
        )
        .limit(1)
    ) is not None


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


def invoice_total_minor(record: ModuleRecord) -> int:
    amount_minor = amount_to_minor(record.data.get("amount"))
    tax_minor = record.data.get("tax_amount_minor")
    if not isinstance(tax_minor, int) or tax_minor < 0:
        tax_minor, _ = calculate_invoice_tax(record.data, amount_minor)
    return amount_minor + tax_minor


def serialize_invoice_settlements(
    db: Session,
    owner_id: int,
    module_id: str,
    invoices: list[ModuleRecord],
) -> list[InvoiceSettlementOut]:
    if not invoices:
        return []
    invoice_ids = [invoice.id for invoice in invoices]
    payments = db.scalars(
        select(InvoiceSettlement)
        .where(
            InvoiceSettlement.owner_id == owner_id,
            InvoiceSettlement.module_id == module_id,
            InvoiceSettlement.invoice_record_id.in_(invoice_ids),
        )
        .order_by(InvoiceSettlement.posting_date, InvoiceSettlement.id)
    ).all()
    by_invoice: dict[int, list[InvoiceSettlement]] = {invoice_id: [] for invoice_id in invoice_ids}
    for payment in payments:
        by_invoice[payment.invoice_record_id].append(payment)

    output = []
    for invoice in invoices:
        invoice_payments = by_invoice[invoice.id]
        invoice_total = invoice_total_minor(invoice)
        paid = sum(payment.amount_minor for payment in invoice_payments)
        output.append(
            InvoiceSettlementOut(
                invoice_record_id=invoice.id,
                module_id=module_id,
                invoice_total_minor=invoice_total,
                paid_minor=paid,
                outstanding_minor=max(invoice_total - paid, 0),
                settlement_status=(
                    "Paid" if paid >= invoice_total else "Partially Paid" if paid else "Unpaid"
                ),
                payments=[
                    InvoicePaymentOut(
                        id=payment.id,
                        payment_reference=payment.payment_reference,
                        posting_date=payment.posting_date,
                        amount_minor=payment.amount_minor,
                        cash_account_code=payment.cash_account_code,
                        cash_account_name=payment.cash_account_name,
                    )
                    for payment in invoice_payments
                ],
            )
        )
    return output


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


def require_open_period(db: Session, owner_id: int, posting_date: date) -> None:
    period = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(
            FiscalYear.owner_id == owner_id,
            FiscalPeriod.start_date <= posting_date,
            FiscalPeriod.end_date >= posting_date,
        )
    ).first()
    if period is None:
        raise HTTPException(status_code=422, detail="Posting date is outside a configured fiscal period.")
    fiscal_period, fiscal_year = period
    if fiscal_year.status != "ACTIVE":
        raise HTTPException(status_code=422, detail="The fiscal year for this posting date is not active.")
    if fiscal_period.status != "OPEN":
        raise HTTPException(status_code=409, detail="The fiscal period for this posting date is closed.")


def migrate_fiscal_year_workspace_constraints() -> None:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            with connection.begin():
                connection.exec_driver_sql(
                    """
                    CREATE TABLE fiscal_years_new (
                        id INTEGER PRIMARY KEY,
                        owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        company_code VARCHAR(30) NOT NULL,
                        code VARCHAR(20) NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        variant VARCHAR(20) NOT NULL,
                        start_date DATE NOT NULL,
                        end_date DATE NOT NULL,
                        period_count INTEGER NOT NULL DEFAULT 12,
                        description VARCHAR(500),
                        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
                        active_company_code VARCHAR(30)
                            GENERATED ALWAYS AS (CASE WHEN status = 'ACTIVE' THEN company_code ELSE NULL END) STORED,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        CONSTRAINT uq_fiscal_year_company_code UNIQUE (owner_id, company_code, code),
                        CONSTRAINT uq_fiscal_year_active_company UNIQUE (owner_id, active_company_code),
                        CONSTRAINT ck_fiscal_year_dates CHECK (start_date < end_date),
                        CONSTRAINT ck_fiscal_year_variant CHECK (variant IN ('APR_MAR', 'JAN_DEC')),
                        CONSTRAINT ck_fiscal_year_status CHECK (status IN ('DRAFT', 'ACTIVE')),
                        CONSTRAINT ck_fiscal_year_period_count CHECK (period_count = 12)
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO fiscal_years_new (
                        id, owner_id, company_code, code, name, variant, start_date, end_date,
                        period_count, description, status, created_at, updated_at
                    )
                    SELECT
                        id, owner_id, company_code, code, name, variant, start_date, end_date,
                        period_count, description, status, created_at, updated_at
                    FROM fiscal_years
                    """
                )
                connection.exec_driver_sql("DROP TABLE fiscal_years")
                connection.exec_driver_sql("ALTER TABLE fiscal_years_new RENAME TO fiscal_years")
                connection.exec_driver_sql(
                    "CREATE INDEX ix_fiscal_year_company_dates ON fiscal_years (owner_id, company_code, start_date, end_date)"
                )
                connection.exec_driver_sql("CREATE INDEX ix_fiscal_years_owner_id ON fiscal_years (owner_id)")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
        return

    if dialect == "postgresql":
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE fiscal_years DROP CONSTRAINT IF EXISTS uq_fiscal_year_company_code")
            connection.exec_driver_sql("ALTER TABLE fiscal_years DROP CONSTRAINT IF EXISTS uq_fiscal_year_active_company")
            connection.exec_driver_sql("ALTER TABLE fiscal_years ADD CONSTRAINT uq_fiscal_year_company_code UNIQUE (owner_id, company_code, code)")
            connection.exec_driver_sql("ALTER TABLE fiscal_years ADD CONSTRAINT uq_fiscal_year_active_company UNIQUE (owner_id, active_company_code)")
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_fiscal_year_company_dates")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_fiscal_year_company_dates ON fiscal_years (owner_id, company_code, start_date, end_date)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_fiscal_years_owner_id ON fiscal_years (owner_id)")
        return

    if dialect == "mysql":
        with engine.begin() as connection:
            existing_indexes = {
                index["name"] for index in inspect(engine).get_indexes("fiscal_years")
            } | {
                constraint["name"] for constraint in inspect(engine).get_unique_constraints("fiscal_years")
            }
            for index_name in (
                "uq_fiscal_year_company_code",
                "uq_fiscal_year_active_company",
                "ix_fiscal_year_company_dates",
                "ix_fiscal_years_owner_id",
            ):
                if index_name in existing_indexes:
                    connection.exec_driver_sql(f"ALTER TABLE fiscal_years DROP INDEX {index_name}")
            connection.exec_driver_sql("ALTER TABLE fiscal_years ADD CONSTRAINT uq_fiscal_year_company_code UNIQUE (owner_id, company_code, code)")
            connection.exec_driver_sql("ALTER TABLE fiscal_years ADD CONSTRAINT uq_fiscal_year_active_company UNIQUE (owner_id, active_company_code)")
            connection.exec_driver_sql("CREATE INDEX ix_fiscal_year_company_dates ON fiscal_years (owner_id, company_code, start_date, end_date)")
            connection.exec_driver_sql("CREATE INDEX ix_fiscal_years_owner_id ON fiscal_years (owner_id)")
        return

    raise RuntimeError(f"Fiscal-year workspace migration is not supported for database dialect {dialect}.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    fiscal_year_columns = {column["name"] for column in inspector.get_columns("fiscal_years")}
    needs_workspace_migration = "owner_id" not in fiscal_year_columns
    legacy_constraints = any(
        tuple(constraint["column_names"]) in {
            ("company_code", "code"),
            ("active_company_code",),
        }
        for constraint in inspector.get_unique_constraints("fiscal_years")
    )
    needs_workspace_migration = needs_workspace_migration or legacy_constraints
    if "owner_id" not in fiscal_year_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE fiscal_years ADD COLUMN owner_id INTEGER"))
    with SessionLocal() as db:
        users = db.scalars(select(User).order_by(User.id)).all()
        company_owners: dict[str, set[int]] = {}
        companies = db.scalars(
            select(ModuleRecord).where(ModuleRecord.module_id == "company")
        ).all()
        for company in companies:
            company_code = company.data.get("company_code")
            if isinstance(company_code, str) and company_code.strip():
                company_owners.setdefault(company_code.strip().upper(), set()).add(company.owner_id)
        years_without_owner = db.scalars(select(FiscalYear).where(FiscalYear.owner_id.is_(None))).all()
        for year in years_without_owner:
            matching_owners = company_owners.get(year.company_code.upper(), set())
            if len(matching_owners) == 1:
                year.owner_id = next(iter(matching_owners))
            elif len(users) == 1:
                year.owner_id = users[0].id
            elif matching_owners:
                raise RuntimeError(
                    f"Cannot safely assign legacy fiscal year {year.code}: multiple workspaces use company {year.company_code}."
                )
            else:
                raise RuntimeError(
                    f"Cannot safely assign legacy fiscal year {year.code}; contact support to map it to a workspace."
                )
        for user in users:
            has_membership = db.scalar(
                select(WorkspaceMember.id)
                .where(WorkspaceMember.member_user_id == user.id)
                .limit(1)
            )
            if not has_membership:
                db.add(WorkspaceMember(owner_user_id=user.id, member_user_id=user.id, role="admin"))
        unreviewed_documents = db.scalars(
            select(ModuleRecord).where(
                ModuleRecord.module_id.in_(APPROVAL_MODULES),
                ModuleRecord.status.in_(("Approved", "In Progress")),
            )
        ).all()
        for record in unreviewed_documents:
            if not has_approval_event(db, record.owner_id, record.module_id, record.id):
                record.status = "Draft"
        db.commit()
    if needs_workspace_migration:
        migrate_fiscal_year_workspace_constraints()
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
    db.add(WorkspaceMember(owner_user_id=user.id, member_user_id=user.id, role="admin"))
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


@app.post("/api/auth/forgot-password")
def forgot_password(
    payload: ForgotPasswordIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    mail_config = password_reset_mail_config()
    user = db.scalar(select(User).where(User.email == payload.email))
    generic_message = "If an account exists for that email, reset instructions will be sent."
    if user is None:
        return {"message": generic_message}

    now = utc_naive_now()
    recent_request = db.scalar(
        select(PasswordResetToken.id).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= now - timedelta(minutes=1),
        )
    )
    if recent_request:
        return {"message": generic_message}

    token = secrets.token_urlsafe(32)
    reset_record = PasswordResetToken(
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    for previous_token in db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    ):
        previous_token.used_at = now
    db.add(reset_record)
    db.commit()

    reset_url = f"{mail_config['app_base_url']}/?reset_token={quote(token, safe='')}"
    background_tasks.add_task(
        deliver_password_reset_email,
        user.email,
        reset_url,
        mail_config,
        reset_record.id,
    )
    return {"message": generic_message}


@app.post("/api/auth/reset-password")
def reset_password(
    payload: ResetPasswordIn,
    response: Response,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    reset_record = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    now = utc_naive_now()
    if (
        reset_record is None
        or reset_record.used_at is not None
        or reset_record.expires_at <= now
    ):
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired.")

    user = db.get(User, reset_record.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="This password reset link is invalid or has expired.")
    user.password_hash = hash_password(payload.password)
    for active_token in db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    ):
        active_token.used_at = now
    for auth_session in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)):
        db.delete(auth_session)
    db.commit()
    response.delete_cookie("stackly_session", path="/", httponly=True, samesite="lax")
    return {"message": "Your password has been reset. Please sign in with your new password."}


@app.get("/api/auth/me", response_model=UserOut)
def current_user(user: User = Depends(get_authenticated_user)):
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


@app.get("/api/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(
    actor: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    memberships = db.scalars(
        select(WorkspaceMember)
        .where(WorkspaceMember.member_user_id == actor.id)
        .order_by(WorkspaceMember.owner_user_id)
    ).all()
    owners = {
        owner.id: owner
        for owner in db.scalars(
            select(User).where(User.id.in_([membership.owner_user_id for membership in memberships]))
        ).all()
    }
    return [
        WorkspaceOut(
            id=membership.owner_user_id,
            name=f"{owners[membership.owner_user_id].display_name}'s workspace",
            role=membership.role,
        )
        for membership in memberships
        if membership.owner_user_id in owners
    ]


@app.get("/api/workspaces/members", response_model=list[WorkspaceMemberOut])
def list_workspace_members(
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.member_user_id)
        .where(WorkspaceMember.owner_user_id == user.id)
        .order_by(User.display_name, User.email)
    ).all()
    return [
        WorkspaceMemberOut(
            user_id=membership.member_user_id,
            email=member.email,
            display_name=member.display_name,
            role=membership.role,
        )
        for membership, member in rows
    ]


@app.put("/api/workspaces/members", response_model=WorkspaceMemberOut)
def upsert_workspace_member(
    payload: WorkspaceMemberCreate,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    member = db.scalar(select(User).where(User.email == payload.email))
    if member is None:
        raise HTTPException(status_code=404, detail="Register this user before adding them to the workspace.")
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.owner_user_id == user.id,
            WorkspaceMember.member_user_id == member.id,
        )
    )
    if membership is None:
        membership = WorkspaceMember(
            owner_user_id=user.id,
            member_user_id=member.id,
            role=payload.role,
        )
        db.add(membership)
    elif membership.member_user_id != user.id:
        membership.role = payload.role
    elif payload.role != "admin":
        raise HTTPException(status_code=409, detail="The workspace owner must remain an administrator.")
    db.commit()
    return WorkspaceMemberOut(
        user_id=member.id,
        email=member.email,
        display_name=member.display_name,
        role=membership.role,
    )


@app.delete("/api/workspaces/members/{member_id}", status_code=204)
def remove_workspace_member(
    member_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.owner_user_id == user.id,
            WorkspaceMember.member_user_id == member_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace member not found.")
    if member_id == user.id:
        raise HTTPException(status_code=409, detail="The workspace owner cannot remove themselves.")
    db.delete(membership)
    db.commit()
    return None


@app.get("/api/modules/{module_id}/records", response_model=list[ModuleRecordOut])
def list_module_records(
    module_id: str,
    user: WorkspaceUser = Depends(get_current_user),
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
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in MODULE_IDS:
        raise HTTPException(status_code=404, detail="Module not found.")
    if module_id in APPROVAL_MODULES:
        require_workspace_role(user, "admin", "requester", "approver")
        if payload.status != "Draft":
            raise HTTPException(status_code=422, detail="Approval documents must be created as drafts.")
    else:
        require_workspace_role(user, "admin")
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
    user: WorkspaceUser = Depends(get_current_user),
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
    updates = payload.model_dump(exclude_unset=True)
    if module_id in APPROVAL_MODULES:
        require_workspace_role(user, "admin", "requester", "approver")
        if "status" in updates:
            raise HTTPException(status_code=422, detail="Use the approval workflow to change document status.")
        if record.status in {"Pending Approval", "Approved", "Posted", "Active"}:
            raise HTTPException(status_code=409, detail="This document is locked in its current approval state.")
    else:
        require_workspace_role(user, "admin")
        if record.status == "Posted":
            raise HTTPException(status_code=409, detail="Posted records are locked against changes.")
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
    user: WorkspaceUser = Depends(get_current_user),
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
    if module_id in APPROVAL_MODULES:
        require_workspace_role(user, "admin", "requester", "approver")
        if record.status not in {"Draft", "Rejected"}:
            raise HTTPException(status_code=409, detail="Only drafts and rejected documents can be deleted.")
    else:
        require_workspace_role(user, "admin")
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
    user: WorkspaceUser = Depends(get_current_user),
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
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalYear.owner_id == user.id)
        .order_by(FiscalYear.start_date.desc(), FiscalPeriod.period_number)
    ).all()
    return [serialize_fiscal_period_detail(period, year) for period, year in rows]


@app.patch("/api/fiscal-periods/{period_id}", response_model=FiscalPeriodDetailOut)
def update_fiscal_period(
    period_id: int,
    payload: FiscalPeriodUpdate,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalYear.owner_id == user.id)
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fiscal period not found.")
    period, year = row
    if payload.start_date < year.start_date or payload.end_date > year.end_date:
        raise HTTPException(status_code=422, detail="Period dates must stay within the fiscal year.")
    if period.period_number == 1 and payload.start_date != year.start_date:
        raise HTTPException(status_code=422, detail="The first period must begin on the fiscal-year start date.")
    if period.period_number == year.period_count and payload.end_date != year.end_date:
        raise HTTPException(status_code=422, detail="The final period must end on the fiscal-year end date.")

    previous = None
    following = None
    if period.period_number > 1:
        previous = db.scalar(
            select(FiscalPeriod)
            .where(
                FiscalPeriod.fiscal_year_id == year.id,
                FiscalPeriod.period_number == period.period_number - 1,
            )
            .with_for_update()
        )
    if period.period_number < year.period_count:
        following = db.scalar(
            select(FiscalPeriod)
            .where(
                FiscalPeriod.fiscal_year_id == year.id,
                FiscalPeriod.period_number == period.period_number + 1,
            )
            .with_for_update()
        )

    new_previous_end = payload.start_date - timedelta(days=1) if previous else None
    new_following_start = payload.end_date + timedelta(days=1) if following else None
    if previous and new_previous_end != previous.end_date and (
        new_previous_end < previous.start_date or previous.status != "OPEN"
    ):
        raise HTTPException(status_code=409, detail="The preceding period must be open and retain at least one day.")
    if following and new_following_start != following.start_date and (
        new_following_start > following.end_date or following.status != "OPEN"
    ):
        raise HTTPException(status_code=409, detail="The following period must be open and retain at least one day.")
    if period.status != "OPEN" and (
        payload.start_date != period.start_date or payload.end_date != period.end_date
    ):
        raise HTTPException(status_code=409, detail="Reopen the period before changing its dates.")

    shifted_boundaries = []
    if previous and new_previous_end != previous.end_date:
        shifted_boundaries.append((previous.end_date, new_previous_end))
    if following and new_following_start != following.start_date:
        shifted_boundaries.append((following.start_date - timedelta(days=1), payload.end_date))
    for old_boundary, new_boundary in shifted_boundaries:
        first_date = min(old_boundary, new_boundary) + timedelta(days=1)
        last_date = max(old_boundary, new_boundary)
        if db.scalar(
            select(LedgerEntry.id)
            .where(
                LedgerEntry.owner_id == user.id,
                LedgerEntry.posting_date.between(first_date, last_date),
            )
            .limit(1)
        ):
            raise HTTPException(
                status_code=409,
                detail="Period dates cannot move across dates that already contain posted ledger entries.",
            )

    period.name = payload.name
    period.start_date = payload.start_date
    period.end_date = payload.end_date
    if previous and new_previous_end is not None:
        previous.end_date = new_previous_end
    if following and new_following_start is not None:
        following.start_date = new_following_start

    db.commit()
    return serialize_fiscal_period_detail(period, year)


@app.get("/api/approvals/pending", response_model=list[ModuleRecordOut])
def pending_approvals(
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(ModuleRecord)
        .where(
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id.in_(APPROVAL_MODULES),
            ModuleRecord.status == "Pending Approval",
        )
        .order_by(ModuleRecord.updated_at, ModuleRecord.id)
    ).all()


@app.get(
    "/api/modules/{module_id}/records/{record_id}/approvals",
    response_model=list[ApprovalEventOut],
)
def approval_history(
    module_id: str,
    record_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in APPROVAL_MODULES:
        raise HTTPException(status_code=404, detail="This module does not use approvals.")
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    rows = db.execute(
        select(ApprovalEvent, User)
        .join(User, User.id == ApprovalEvent.actor_id)
        .where(
            ApprovalEvent.workspace_owner_id == user.id,
            ApprovalEvent.module_id == module_id,
            ApprovalEvent.record_id == record_id,
        )
        .order_by(ApprovalEvent.id)
    ).all()
    return [
        ApprovalEventOut(
            id=event.id,
            action=event.action,
            comment=event.comment,
            created_at=event.created_at,
            actor_email=actor.email,
            actor_name=actor.display_name,
        )
        for event, actor in rows
    ]


@app.post("/api/modules/{module_id}/records/{record_id}/submit", response_model=ModuleRecordOut)
def submit_for_approval(
    module_id: str,
    record_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in APPROVAL_MODULES:
        raise HTTPException(status_code=404, detail="This module does not use approvals.")
    require_workspace_role(user, "admin", "requester", "approver")
    record = db.scalar(
        select(ModuleRecord)
        .where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record.status not in {"Draft", "Rejected"}:
        raise HTTPException(status_code=409, detail="Only drafts and rejected documents can be submitted.")
    record.status = "Pending Approval"
    db.add(
        ApprovalEvent(
            workspace_owner_id=user.id,
            module_id=module_id,
            record_id=record.id,
            actor_id=user.actor_id,
            action="submitted",
        )
    )
    db.commit()
    db.refresh(record)
    return record


@app.post(
    "/api/modules/{module_id}/records/{record_id}/review",
    response_model=ModuleRecordOut,
)
def review_document(
    module_id: str,
    record_id: int,
    payload: ApprovalActionIn,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in APPROVAL_MODULES:
        raise HTTPException(status_code=404, detail="This module does not use approvals.")
    require_workspace_role(user, "admin", "approver")
    if payload.action == "reject" and not payload.comment:
        raise HTTPException(status_code=422, detail="Add a reason when rejecting a document.")
    record = db.scalar(
        select(ModuleRecord)
        .where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    if record.status != "Pending Approval":
        raise HTTPException(status_code=409, detail="Only documents awaiting approval can be reviewed.")
    record.status = "Approved" if payload.action == "approve" else "Rejected"
    db.add(
        ApprovalEvent(
            workspace_owner_id=user.id,
            module_id=module_id,
            record_id=record.id,
            actor_id=user.actor_id,
            action=payload.action,
            comment=payload.comment,
        )
    )
    db.commit()
    db.refresh(record)
    return record


@app.post("/api/fiscal-periods/{period_id}/close", response_model=FiscalPeriodDetailOut)
def close_fiscal_period(
    period_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalYear.owner_id == user.id)
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fiscal period not found.")
    period, _year = row
    period.status = "CLOSED"
    db.commit()
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalYear.owner_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    return serialize_fiscal_period_detail(*row)


@app.post("/api/fiscal-periods/{period_id}/reopen", response_model=FiscalPeriodDetailOut)
def reopen_fiscal_period(
    period_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalYear.owner_id == user.id)
        .with_for_update()
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Fiscal period not found.")
    period, _year = row
    period.status = "OPEN"
    db.commit()
    row = db.execute(
        select(FiscalPeriod, FiscalYear)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalYear.owner_id == user.id)
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
    user: WorkspaceUser = Depends(get_current_user),
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
    require_workspace_role(user, "admin", "requester", "approver")
    if record.status != "Approved":
        raise HTTPException(status_code=409, detail="Approve this document before posting it.")
    if not has_approval_event(db, user.id, module_id, record.id):
        raise HTTPException(status_code=409, detail="This document has no recorded approval; submit it for review.")
    posting_date, document_no, lines = make_posting_lines(
        module_id,
        record,
        get_accounts_by_code(db, user.id),
    )
    require_open_period(db, user.id, posting_date)
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


@app.get("/api/modules/{module_id}/settlements", response_model=list[InvoiceSettlementOut])
def list_invoice_settlements(
    module_id: str,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if module_id not in {"ap", "ar"}:
        raise HTTPException(status_code=404, detail="Settlement summaries are available for AP and AR invoices.")
    invoices = db.scalars(
        select(ModuleRecord)
        .where(
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
            ModuleRecord.status == "Posted",
        )
        .order_by(ModuleRecord.updated_at.desc(), ModuleRecord.id.desc())
    ).all()
    return serialize_invoice_settlements(db, user.id, module_id, invoices)


@app.post(
    "/api/modules/{module_id}/records/{record_id}/payments",
    response_model=InvoiceSettlementOut,
    status_code=status.HTTP_201_CREATED,
)
def record_invoice_payment(
    module_id: str,
    record_id: int,
    payload: InvoicePaymentCreate,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin", "requester", "approver")
    if module_id not in {"ap", "ar"}:
        raise HTTPException(status_code=404, detail="Payments and receipts are available for AP and AR invoices.")
    invoice = db.scalar(
        select(ModuleRecord)
        .where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == module_id,
        )
        .with_for_update()
    )
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status != "Posted":
        raise HTTPException(status_code=409, detail="Post the invoice before recording a payment or receipt.")
    if not payload.payment_reference:
        raise HTTPException(status_code=422, detail="A payment or receipt reference is required.")
    existing_reference = db.scalar(
        select(InvoiceSettlement.id).where(
            InvoiceSettlement.owner_id == user.id,
            InvoiceSettlement.module_id == module_id,
            InvoiceSettlement.payment_reference == payload.payment_reference,
        ).limit(1)
    )
    if existing_reference:
        raise HTTPException(status_code=409, detail="This payment reference has already been used.")

    invoice_date = parse_posting_date(invoice.data.get("invoice_date"))
    if payload.posting_date < invoice_date:
        raise HTTPException(status_code=422, detail="Payment date cannot be before the invoice date.")
    amount_minor = amount_to_minor(payload.amount)
    if amount_minor <= 0:
        raise HTTPException(status_code=422, detail="Payment or receipt amount must be greater than zero.")
    invoice_total = invoice_total_minor(invoice)
    paid_minor = int(
        db.scalar(
            select(func.coalesce(func.sum(InvoiceSettlement.amount_minor), 0)).where(
                InvoiceSettlement.owner_id == user.id,
                InvoiceSettlement.module_id == module_id,
                InvoiceSettlement.invoice_record_id == invoice.id,
            )
        )
        or 0
    )
    outstanding_minor = invoice_total - paid_minor
    if amount_minor > outstanding_minor:
        raise HTTPException(
            status_code=422,
            detail=f"Amount exceeds the outstanding balance of {outstanding_minor} paise.",
        )

    account_type = "Liability" if module_id == "ap" else "Asset"
    control_account = require_account(
        get_accounts_by_code(db, user.id),
        invoice.data.get("control_account_code"),
        {account_type},
    )
    cash_account = require_account(
        get_accounts_by_code(db, user.id),
        payload.cash_account_code,
        {"Asset"},
    )
    if cash_account.id == control_account.id:
        raise HTTPException(status_code=422, detail="Select a cash or bank account different from the invoice control account.")
    require_open_period(db, user.id, payload.posting_date)

    payment = InvoiceSettlement(
        owner_id=user.id,
        invoice_record_id=invoice.id,
        module_id=module_id,
        payment_reference=payload.payment_reference,
        posting_date=payload.posting_date,
        amount_minor=amount_minor,
        cash_account_code=str(cash_account.data["account_code"]).upper(),
        cash_account_name=cash_account.name,
    )
    db.add(payment)
    try:
        db.flush()
        if module_id == "ap":
            ledger_lines = [
                (control_account, amount_minor, 0, f"Payment for {invoice.name}"),
                (cash_account, 0, amount_minor, f"Payment {payload.payment_reference}"),
            ]
            source_module = "ap-payment"
        else:
            ledger_lines = [
                (cash_account, amount_minor, 0, f"Receipt {payload.payment_reference}"),
                (control_account, 0, amount_minor, f"Receipt for {invoice.name}"),
            ]
            source_module = "ar-receipt"
        for line_number, (account, debit_minor, credit_minor, description) in enumerate(ledger_lines, start=1):
            db.add(
                LedgerEntry(
                    owner_id=user.id,
                    source_module=source_module,
                    source_record_id=payment.id,
                    line_number=line_number,
                    account_code=str(account.data["account_code"]).upper(),
                    account_name=account.name,
                    account_type=str(account.data["account_type"]),
                    posting_date=payload.posting_date,
                    document_no=payload.payment_reference,
                    description=description,
                    debit_minor=debit_minor,
                    credit_minor=credit_minor,
                )
            )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="This payment reference was already recorded.") from error
    db.refresh(invoice)
    return serialize_invoice_settlements(db, user.id, module_id, [invoice])[0]


@app.post("/api/modules/fixed-assets/records/{record_id}/post-acquisition", response_model=ModuleRecordOut)
def post_fixed_asset_acquisition(
    record_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin", "requester", "approver")
    record = db.scalar(
        select(ModuleRecord).where(
            ModuleRecord.id == record_id,
            ModuleRecord.owner_id == user.id,
            ModuleRecord.module_id == "fixed-assets",
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Fixed asset not found.")
    if record.status != "Approved":
        raise HTTPException(status_code=409, detail="Approve this asset before posting its acquisition.")
    if not has_approval_event(db, user.id, "fixed-assets", record.id):
        raise HTTPException(status_code=409, detail="This asset has no recorded approval; submit it for review.")
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
    require_open_period(db, user.id, posting_date)
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
    user: WorkspaceUser = Depends(get_current_user),
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
    require_workspace_role(user, "admin", "requester", "approver")
    require_open_period(db, user.id, period_end)
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


@app.get(
    "/api/modules/fixed-assets/records/{record_id}/depreciation-schedule",
    response_model=FixedAssetScheduleOut,
)
def fixed_asset_depreciation_schedule(
    record_id: int,
    user: WorkspaceUser = Depends(get_current_user),
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
        raise HTTPException(status_code=409, detail="Post the asset acquisition before viewing its depreciation schedule.")

    acquisition_date = parse_posting_date(record.data.get("acquisition_date"))
    cost_minor = amount_to_minor(record.data.get("cost"))
    salvage_minor = amount_to_minor(record.data.get("salvage_value", 0))
    try:
        useful_life = Decimal(str(record.data.get("useful_life_years")))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=422, detail="Useful life must be a positive whole number of years.")
    if not useful_life.is_finite() or useful_life <= 0 or useful_life != useful_life.to_integral_value():
        raise HTTPException(status_code=422, detail="Useful life must be a positive whole number of years.")
    if salvage_minor > cost_minor:
        raise HTTPException(status_code=422, detail="Salvage value cannot exceed asset cost.")
    useful_life_months = int(useful_life) * 12
    depreciable_minor = cost_minor - salvage_minor
    monthly_base, extra_minor = divmod(depreciable_minor, useful_life_months)

    ledger_entries = db.scalars(
        select(LedgerEntry)
        .where(
            LedgerEntry.owner_id == user.id,
            LedgerEntry.source_module == "fixed-assets",
            LedgerEntry.source_record_id == record.id,
            LedgerEntry.line_number >= 3,
        )
        .order_by(LedgerEntry.line_number)
    ).all()
    if len(ledger_entries) % 2:
        raise HTTPException(status_code=409, detail="Existing depreciation entries are incomplete; contact an administrator.")

    posted_periods: list[FixedAssetDepreciationPeriodOut] = []
    for index in range(0, len(ledger_entries), 2):
        expense_line, accumulated_line = ledger_entries[index:index + 2]
        if (
            expense_line.posting_date != accumulated_line.posting_date
            or expense_line.debit_minor != accumulated_line.credit_minor
        ):
            raise HTTPException(status_code=409, detail="Existing depreciation entries are inconsistent; contact an administrator.")
        posted_periods.append(
            FixedAssetDepreciationPeriodOut(
                period_end=expense_line.posting_date,
                document_no=expense_line.document_no,
                amount_minor=expense_line.debit_minor,
            )
        )

    accumulated_minor = sum(period.amount_minor for period in posted_periods)
    net_book_value_minor = max(cost_minor - accumulated_minor, salvage_minor)
    next_period_end = None
    if len(posted_periods) < useful_life_months and net_book_value_minor > salvage_minor:
        next_month_index = acquisition_date.year * 12 + acquisition_date.month - 1 + len(posted_periods) + 1
        next_year, zero_based_month = divmod(next_month_index, 12)
        next_month = zero_based_month + 1
        next_period_end = date(
            next_year,
            next_month,
            calendar.monthrange(next_year, next_month)[1],
        )

    return FixedAssetScheduleOut(
        record_id=record.id,
        asset_name=record.name,
        acquisition_date=acquisition_date,
        cost_minor=cost_minor,
        salvage_minor=salvage_minor,
        useful_life_months=useful_life_months,
        monthly_depreciation_minor=monthly_base + (1 if extra_minor else 0),
        accumulated_depreciation_minor=accumulated_minor,
        net_book_value_minor=net_book_value_minor,
        next_period_end=next_period_end,
        posted_periods=posted_periods,
    )


@app.get("/api/accounting/trial-balance", response_model=TrialBalanceOut)
def trial_balance(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: WorkspaceUser = Depends(get_current_user),
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
    user: WorkspaceUser = Depends(get_current_user),
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
    user: WorkspaceUser = Depends(get_current_user),
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
    approved_ids = set(
        db.scalars(
            select(ApprovalEvent.record_id).where(
                ApprovalEvent.workspace_owner_id == user.id,
                ApprovalEvent.module_id == "budgeting",
                ApprovalEvent.action == "approve",
            )
        ).all()
    )
    accounts = get_accounts_by_code(db, user.id)
    output: list[BudgetVarianceOut] = []
    for budget in budgets:
        if budget.id not in approved_ids:
            continue
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
    user: WorkspaceUser = Depends(get_current_user),
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
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date.")
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
        if start_date or end_date:
            invoice_date = parse_posting_date(data.get("invoice_date"))
            if start_date and invoice_date < start_date:
                continue
            if end_date and invoice_date > end_date:
                continue
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
    user: WorkspaceUser = Depends(get_current_user),
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
        select(func.count(FiscalYear.id)).where(
            FiscalYear.owner_id == user.id,
            FiscalYear.status == "ACTIVE",
        )
    ) or 0
    open_period_count = db.scalar(
        select(func.count(FiscalPeriod.id))
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(
            FiscalYear.owner_id == user.id,
            FiscalPeriod.status == "OPEN",
            FiscalYear.status == "ACTIVE",
        )
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
        "ap-payment": "Supplier Payment",
        "ar-receipt": "Customer Receipt",
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
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    statement = select(FiscalYear).where(FiscalYear.owner_id == user.id).order_by(FiscalYear.start_date.desc(), FiscalYear.code)
    if company:
        statement = statement.where(FiscalYear.company_code == company.strip().upper())
    years = db.scalars(statement).all()
    return [serialize_year(year, include_periods=False) for year in years]


@app.post("/api/fiscal-years", response_model=FiscalYearOut, status_code=201)
def create_fiscal_year(
    payload: FiscalYearCreate,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    duplicate_code = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.owner_id == user.id,
            FiscalYear.company_code == payload.company,
            FiscalYear.code == payload.code,
        ).limit(1)
    )
    if duplicate_code:
        raise HTTPException(status_code=409, detail="A fiscal year with this company and code already exists.")

    overlapping = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.owner_id == user.id,
            FiscalYear.company_code == payload.company,
            FiscalYear.start_date <= payload.end,
            FiscalYear.end_date >= payload.start,
        ).limit(1)
    )
    if overlapping:
        raise HTTPException(status_code=409, detail="This date range overlaps an existing fiscal year for the company.")

    year = FiscalYear(
        owner_id=user.id,
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
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    year = db.scalar(
        select(FiscalYear)
        .options(selectinload(FiscalYear.periods))
        .where(FiscalYear.id == fiscal_year_id, FiscalYear.owner_id == user.id)
    )
    if year is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    return serialize_year(year)


@app.post("/api/fiscal-years/{fiscal_year_id}/activate", response_model=FiscalYearOut)
def activate_fiscal_year(
    fiscal_year_id: int,
    user: WorkspaceUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_workspace_role(user, "admin")
    year = db.scalar(
        select(FiscalYear)
        .options(selectinload(FiscalYear.periods))
        .where(FiscalYear.id == fiscal_year_id, FiscalYear.owner_id == user.id)
        .with_for_update()
    )
    if year is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    if year.status == "ACTIVE":
        return serialize_year(year)

    existing_active = db.scalar(
        select(FiscalYear.id).where(
            FiscalYear.owner_id == user.id,
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
