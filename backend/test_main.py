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
        response = client.post(
            "/api/auth/register",
            json={
                "email": "tester@example.com",
                "display_name": "Test User",
                "password": "correct-horse-battery",
            },
        )
        assert response.status_code == 201
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


def test_fiscal_year_api_requires_authentication(test_client):
    test_client.post("/api/auth/logout")

    assert test_client.get("/api/fiscal-years").status_code == 401


def test_registration_and_login_use_http_only_session_cookie(test_client):
    test_client.post("/api/auth/logout")
    response = test_client.post(
        "/api/auth/login",
        json={"email": "tester@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "tester@example.com"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert test_client.get("/api/auth/me").json()["display_name"] == "Test User"


def test_registration_rejects_duplicate_email(test_client):
    response = test_client.post(
        "/api/auth/register",
        json={
            "email": "TESTER@example.com",
            "display_name": "Another User",
            "password": "correct-horse-battery",
        },
    )

    assert response.status_code == 409


def test_module_records_are_persistent_and_private_to_the_account(test_client):
    created = test_client.post(
        "/api/modules/company/records",
        json={
            "name": "Northwind",
            "status": "Active",
            "data": {"company_code": "NORTH", "currency": "INR"},
        },
    )
    assert created.status_code == 201
    record = created.json()
    assert record["data"]["company_code"] == "NORTH"
    assert test_client.get("/api/modules/company/records").json()[0]["id"] == record["id"]

    with TestClient(main.app) as other_user:
        registration = other_user.post(
            "/api/auth/register",
            json={
                "email": "other@example.com",
                "display_name": "Other User",
                "password": "another-secure-password",
            },
        )
        assert registration.status_code == 201
        assert other_user.get("/api/modules/company/records").json() == []


def test_module_record_update_and_delete(test_client):
    created = test_client.post(
        "/api/modules/ap/records",
        json={"name": "Invoice 1001", "data": {"amount": 500}},
    )
    record_id = created.json()["id"]

    updated = test_client.patch(
        f"/api/modules/ap/records/{record_id}",
        json={"status": "Approved", "data": {"amount": 750}},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "Approved"
    assert updated.json()["data"]["amount"] == 750

    deleted = test_client.delete(f"/api/modules/ap/records/{record_id}")
    assert deleted.status_code == 204
    assert test_client.get("/api/modules/ap/records").json() == []


def test_module_record_rejects_null_updates(test_client):
    record_id = test_client.post(
        "/api/modules/company/records",
        json={"name": "Northwind"},
    ).json()["id"]

    response = test_client.patch(
        f"/api/modules/company/records/{record_id}",
        json={"name": None},
    )

    assert response.status_code == 422


def test_unknown_module_is_rejected(test_client):
    response = test_client.get("/api/modules/not-a-module/records")

    assert response.status_code == 404


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
