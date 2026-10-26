import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import main


def make_year(code, start, end, variant="APR_MAR"):
    return {
        "company": "STACKLY001",
        "code": code,
        "name": f"Financial Year {code}",
        "variant": variant,
        "start": start,
        "end": end,
    }


@pytest.fixture
def test_client(monkeypatch):
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    test_sessions = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(main, "SessionLocal", test_sessions)

    with TestClient(main.app) as client:
        yield client

    main.Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_create_fiscal_year_generates_twelve_periods(test_client):
    response = test_client.post(
        "/api/fiscal-years",
        json=make_year("FY2027", "2026-04-01", "2027-03-31"),
    )

    assert response.status_code == 201
    year = response.json()
    assert year["period_count"] == 12
    assert len(year["periods"]) == 12
    assert year["periods"][0]["start_date"] == "2026-04-01"
    assert year["periods"][-1]["end_date"] == "2027-03-31"
    assert year["status"] == "DRAFT"


def test_create_rejects_overlapping_fiscal_years(test_client):
    first = make_year("FY2027", "2026-04-01", "2027-03-31")
    test_client.post("/api/fiscal-years", json=first)
    overlapping = make_year("CAL2026", "2026-01-01", "2026-12-31", variant="JAN_DEC")

    response = test_client.post("/api/fiscal-years", json=overlapping)

    assert response.status_code == 409
    assert "overlaps" in response.json()["detail"]


def test_duplicate_company_and_code_is_rejected(test_client):
    year = make_year("FY2027", "2026-04-01", "2027-03-31")
    test_client.post("/api/fiscal-years", json=year)

    response = test_client.post("/api/fiscal-years", json=year)

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_only_one_fiscal_year_per_company_can_be_active(test_client):
    first = test_client.post(
        "/api/fiscal-years",
        json=make_year("FY2027", "2026-04-01", "2027-03-31"),
    ).json()
    second = test_client.post(
        "/api/fiscal-years",
        json=make_year("FY2028", "2027-04-01", "2028-03-31"),
    ).json()

    assert test_client.post(f"/api/fiscal-years/{first['id']}/activate").status_code == 200
    conflict = test_client.post(f"/api/fiscal-years/{second['id']}/activate")
    details = test_client.get(f"/api/fiscal-years/{second['id']}")

    assert conflict.status_code == 409
    assert details.json()["status"] == "DRAFT"


def test_invalid_calendar_is_rejected(test_client):
    response = test_client.post(
        "/api/fiscal-years",
        json=make_year("FY2027", "2026-04-02", "2027-03-31"),
    )

    assert response.status_code == 422
