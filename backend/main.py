import calendar
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, relationship, selectinload, sessionmaker
from starlette.staticfiles import StaticFiles


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stackly_oneerp.db")
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


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
    db: Session = Depends(get_db),
):
    statement = select(FiscalYear).order_by(FiscalYear.start_date.desc(), FiscalYear.code)
    if company:
        statement = statement.where(FiscalYear.company_code == company.strip().upper())
    years = db.scalars(statement).all()
    return [serialize_year(year, include_periods=False) for year in years]


@app.post("/api/fiscal-years", response_model=FiscalYearOut, status_code=201)
def create_fiscal_year(payload: FiscalYearCreate, db: Session = Depends(get_db)):
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
def get_fiscal_year(fiscal_year_id: int, db: Session = Depends(get_db)):
    year = db.scalar(
        select(FiscalYear)
        .options(selectinload(FiscalYear.periods))
        .where(FiscalYear.id == fiscal_year_id)
    )
    if year is None:
        raise HTTPException(status_code=404, detail="Fiscal year not found.")
    return serialize_year(year)


@app.post("/api/fiscal-years/{fiscal_year_id}/activate", response_model=FiscalYearOut)
def activate_fiscal_year(fiscal_year_id: int, db: Session = Depends(get_db)):
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
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend_assets")

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(FRONTEND_DIST / "favicon.svg")

    @app.get("/icons.svg")
    def icons():
        return FileResponse(FRONTEND_DIST / "icons.svg")

    @app.get("/{path:path}")
    def catch_all(path: str):
        requested = FRONTEND_DIST / path
        if requested.is_file():
            return FileResponse(requested)
        return FileResponse(FRONTEND_DIST / "index.html")
