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


def test_chart_of_accounts_rejects_duplicate_codes_and_locks_used_accounts(test_client):
    first = create_account(test_client, "1000", "Bank", "Asset")
    duplicate = test_client.post(
        "/api/modules/chart-of-accounts/records",
        json={
            "name": "Duplicate bank",
            "status": "Active",
            "data": {"account_code": "1000", "account_type": "Asset"},
        },
    )
    assert duplicate.status_code == 409

    activate_test_year(test_client)
    create_account(test_client, "3000", "Owner equity", "Equity")
    journal = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Opening balance",
            "data": {
                "document_no": "JE-COA-LOCK",
                "posting_date": "2026-04-01",
                "lines": [
                    {"account_code": "1000", "debit": 100, "credit": 0},
                    {"account_code": "3000", "debit": 0, "credit": 100},
                ],
            },
        },
    ).json()
    assert test_client.post(f"/api/modules/journal-entry/records/{journal['id']}/post").status_code == 200
    assert test_client.patch(
        f"/api/modules/chart-of-accounts/records/{first['id']}",
        json={"data": {"account_code": "1001", "account_type": "Asset"}},
    ).status_code == 409
    assert test_client.delete(f"/api/modules/chart-of-accounts/records/{first['id']}").status_code == 409


def test_unknown_module_is_rejected(test_client):
    response = test_client.get("/api/modules/not-a-module/records")

    assert response.status_code == 404


def create_account(client, code, name, account_type):
    response = client.post(
        "/api/modules/chart-of-accounts/records",
        json={
            "name": name,
            "status": "Active",
            "data": {"account_code": code, "account_type": account_type},
        },
    )
    assert response.status_code == 201
    return response.json()


def activate_test_year(client):
    year = client.post(
        "/api/fiscal-years",
        json=make_year("FY2027", "2026-04-01", "2027-03-31"),
    )
    assert year.status_code == 201
    activated = client.post(f"/api/fiscal-years/{year.json()['id']}/activate")
    assert activated.status_code == 200
    return activated.json()


def test_draft_journal_does_not_affect_trial_balance_until_posted(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "1000", "Bank", "Asset")
    created = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Rent payment",
            "data": {
                "document_no": "JE-001",
                "posting_date": "2026-04-10",
                "lines": [
                    {"account_code": "5000", "debit": 125.5, "credit": 0},
                    {"account_code": "1000", "debit": 0, "credit": 125.5},
                ],
            },
        },
    ).json()

    report = test_client.get(
        "/api/accounting/trial-balance?start_date=2026-04-01&end_date=2026-04-30"
    ).json()
    assert all(
        row["period_debit_minor"] == row["period_credit_minor"] == 0
        for row in report["accounts"]
    )

    posted = test_client.post(f"/api/modules/journal-entry/records/{created['id']}/post")
    assert posted.status_code == 200
    assert posted.json()["status"] == "Posted"
    report = test_client.get(
        "/api/accounting/trial-balance?start_date=2026-04-01&end_date=2026-04-30"
    ).json()
    assert report["balanced"] is True
    assert report["total_debit_minor"] == 12550
    assert report["total_credit_minor"] == 12550
    assert {row["account_code"]: row["period_debit_minor"] for row in report["accounts"]} == {
        "1000": 0,
        "5000": 12550,
    }
    assert test_client.post(f"/api/modules/journal-entry/records/{created['id']}/post").status_code == 409
    assert test_client.patch(
        f"/api/modules/journal-entry/records/{created['id']}",
        json={"name": "Changed after posting"},
    ).status_code == 409


def test_unbalanced_journal_is_rejected_without_creating_ledger_entries(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "1000", "Bank", "Asset")
    created = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Unbalanced entry",
            "data": {
                "document_no": "JE-002",
                "posting_date": "2026-04-10",
                "lines": [
                    {"account_code": "5000", "debit": 100, "credit": 0},
                    {"account_code": "1000", "debit": 0, "credit": 90},
                ],
            },
        },
    ).json()

    response = test_client.post(f"/api/modules/journal-entry/records/{created['id']}/post")

    assert response.status_code == 422
    assert test_client.get(
        "/api/accounting/general-ledger?start_date=2026-04-01&end_date=2026-04-30"
    ).json() == []


def test_ap_and_ar_posts_generate_balanced_control_account_lines(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "2100", "Accounts payable", "Liability")
    create_account(test_client, "4000", "Sales", "Income")
    create_account(test_client, "1100", "Accounts receivable", "Asset")
    ap = test_client.post(
        "/api/modules/ap/records",
        json={
            "name": "Supplier bill",
            "data": {
                "invoice_no": "AP-1",
                "invoice_date": "2026-04-11",
                "amount": 1000,
                "account_code": "5000",
                "control_account_code": "2100",
            },
        },
    ).json()
    ar = test_client.post(
        "/api/modules/ar/records",
        json={
            "name": "Customer invoice",
            "data": {
                "invoice_no": "AR-1",
                "invoice_date": "2026-04-12",
                "amount": 1500,
                "account_code": "4000",
                "control_account_code": "1100",
            },
        },
    ).json()

    assert test_client.post(f"/api/modules/ap/records/{ap['id']}/post").status_code == 200
    assert test_client.post(f"/api/modules/ar/records/{ar['id']}/post").status_code == 200
    report = test_client.get(
        "/api/accounting/trial-balance?start_date=2026-04-01&end_date=2026-04-30"
    ).json()
    assert report["balanced"] is True
    assert report["total_debit_minor"] == 250000
    assert report["total_credit_minor"] == 250000


def test_gst_invoice_posting_and_summary_use_configured_tax_lines(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "2100", "Accounts payable", "Liability")
    create_account(test_client, "1400", "Input IGST", "Asset")
    create_account(test_client, "4000", "Sales", "Income")
    create_account(test_client, "1100", "Accounts receivable", "Asset")
    create_account(test_client, "2200", "Output CGST", "Liability")
    create_account(test_client, "2300", "Output SGST", "Liability")
    tax_config = test_client.post(
        "/api/modules/gst/records",
        json={
            "name": "IGST standard",
            "status": "Active",
            "data": {"tax_type": "IGST", "rate": 18, "effective_date": "2026-04-01"},
        },
    )
    assert tax_config.status_code == 201
    ap = test_client.post(
        "/api/modules/ap/records",
        json={
            "name": "Taxable supplier invoice",
            "data": {
                "invoice_no": "AP-GST-1",
                "invoice_date": "2026-04-11",
                "amount": 1000,
                "account_code": "5000",
                "control_account_code": "2100",
                "tax_mode": "IGST",
                "tax_rate": 18,
                "tax_account_code": "1400",
            },
        },
    ).json()
    ar = test_client.post(
        "/api/modules/ar/records",
        json={
            "name": "Taxable customer invoice",
            "data": {
                "invoice_no": "AR-GST-1",
                "invoice_date": "2026-04-12",
                "amount": 1000,
                "account_code": "4000",
                "control_account_code": "1100",
                "tax_mode": "CGST+SGST",
                "tax_rate": 18,
                "cgst_rate": 10,
                "sgst_rate": 8,
                "cgst_account_code": "2200",
                "sgst_account_code": "2300",
            },
        },
    ).json()

    assert test_client.post(f"/api/modules/ap/records/{ap['id']}/post").status_code == 200
    assert test_client.post(f"/api/modules/ar/records/{ar['id']}/post").status_code == 200
    ledger = test_client.get("/api/accounting/general-ledger").json()
    assert sum(entry["debit_minor"] for entry in ledger) == 236000
    assert sum(entry["credit_minor"] for entry in ledger) == 236000
    tax_credits = {
        entry["account_code"]: entry["credit_minor"]
        for entry in ledger
        if entry["account_code"] in {"2200", "2300"}
    }
    assert tax_credits == {"2200": 10000, "2300": 8000}
    summary = test_client.get("/api/accounting/gst-summary").json()
    assert {(row["direction"], row["tax_minor"]) for row in summary} == {
        ("input", 18000),
        ("output", 18000),
    }
    assert all(row["taxable_minor"] == 100000 for row in summary)


def test_ap_payment_and_ar_receipt_post_partial_balanced_ledger_entries(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "2100", "Accounts payable", "Liability")
    create_account(test_client, "4000", "Sales", "Income")
    create_account(test_client, "1100", "Accounts receivable", "Asset")
    create_account(test_client, "1000", "Bank", "Asset")
    ap = test_client.post(
        "/api/modules/ap/records",
        json={
            "name": "Supplier invoice to settle",
            "data": {
                "invoice_no": "AP-SETTLE-1",
                "invoice_date": "2026-04-10",
                "amount": 100,
                "account_code": "5000",
                "control_account_code": "2100",
            },
        },
    ).json()
    ar = test_client.post(
        "/api/modules/ar/records",
        json={
            "name": "Customer invoice to collect",
            "data": {
                "invoice_no": "AR-SETTLE-1",
                "invoice_date": "2026-04-10",
                "amount": 200,
                "account_code": "4000",
                "control_account_code": "1100",
            },
        },
    ).json()
    assert test_client.post(f"/api/modules/ap/records/{ap['id']}/post").status_code == 200
    assert test_client.post(f"/api/modules/ar/records/{ar['id']}/post").status_code == 200

    first_payment = test_client.post(
        f"/api/modules/ap/records/{ap['id']}/payments",
        json={
            "payment_reference": "BANK-OUT-1",
            "posting_date": "2026-04-15",
            "amount": 40,
            "cash_account_code": "1000",
        },
    )
    assert first_payment.status_code == 201
    assert first_payment.json()["settlement_status"] == "Partially Paid"
    assert first_payment.json()["paid_minor"] == 4000
    assert first_payment.json()["outstanding_minor"] == 6000

    second_payment = test_client.post(
        f"/api/modules/ap/records/{ap['id']}/payments",
        json={
            "payment_reference": "BANK-OUT-2",
            "posting_date": "2026-04-16",
            "amount": 60,
            "cash_account_code": "1000",
        },
    )
    assert second_payment.status_code == 201
    assert second_payment.json()["settlement_status"] == "Paid"
    assert second_payment.json()["outstanding_minor"] == 0
    assert test_client.post(
        f"/api/modules/ap/records/{ap['id']}/payments",
        json={
            "payment_reference": "BANK-OUT-OVER",
            "posting_date": "2026-04-16",
            "amount": 1,
            "cash_account_code": "1000",
        },
    ).status_code == 422
    assert test_client.post(
        f"/api/modules/ap/records/{ap['id']}/payments",
        json={
            "payment_reference": "BANK-OUT-1",
            "posting_date": "2026-04-16",
            "amount": 1,
            "cash_account_code": "1000",
        },
    ).status_code == 409

    receipt = test_client.post(
        f"/api/modules/ar/records/{ar['id']}/payments",
        json={
            "payment_reference": "BANK-IN-1",
            "posting_date": "2026-04-17",
            "amount": 75,
            "cash_account_code": "1000",
        },
    )
    assert receipt.status_code == 201
    assert receipt.json()["settlement_status"] == "Partially Paid"
    assert receipt.json()["outstanding_minor"] == 12500
    assert test_client.post(
        f"/api/modules/ar/records/{ar['id']}/payments",
        json={
            "payment_reference": "BANK-IN-SAME-ACCOUNT",
            "posting_date": "2026-04-17",
            "amount": 1,
            "cash_account_code": "1100",
        },
    ).status_code == 422

    with TestClient(main.app) as other_user:
        registration = other_user.post(
            "/api/auth/register",
            json={
                "email": "settlement-other@example.com",
                "display_name": "Other User",
                "password": "another-secure-password",
            },
        )
        assert registration.status_code == 201
        assert other_user.get("/api/modules/ap/settlements").json() == []
        assert other_user.post(
            f"/api/modules/ap/records/{ap['id']}/payments",
            json={
                "payment_reference": "OTHER-USER-PAYMENT",
                "posting_date": "2026-04-18",
                "amount": 1,
                "cash_account_code": "1000",
            },
        ).status_code == 404

    ledger = test_client.get("/api/accounting/general-ledger").json()
    ap_payment = [entry for entry in ledger if entry["source_module"] == "ap-payment"]
    ar_receipt = [entry for entry in ledger if entry["source_module"] == "ar-receipt"]
    assert sum(entry["debit_minor"] for entry in ap_payment) == 10000
    assert sum(entry["credit_minor"] for entry in ap_payment) == 10000
    assert sum(entry["debit_minor"] for entry in ar_receipt) == 7500
    assert sum(entry["credit_minor"] for entry in ar_receipt) == 7500
    tb = test_client.get(
        "/api/accounting/trial-balance?start_date=2026-04-01&end_date=2026-04-30"
    ).json()
    assert tb["balanced"] is True
    assert tb["total_debit_minor"] == 22500
    assert tb["total_credit_minor"] == 22500


def test_invoice_payment_requires_posted_invoice_active_cash_account_and_open_period(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "2100", "Accounts payable", "Liability")
    create_account(test_client, "1000", "Bank", "Asset")
    invoice = test_client.post(
        "/api/modules/ap/records",
        json={
            "name": "Unposted supplier invoice",
            "data": {
                "invoice_no": "AP-UNPOSTED",
                "invoice_date": "2026-04-10",
                "amount": 20,
                "account_code": "5000",
                "control_account_code": "2100",
            },
        },
    ).json()
    payment_payload = {
        "payment_reference": "BANK-UNPOSTED",
        "posting_date": "2026-04-15",
        "amount": 20,
        "cash_account_code": "1000",
    }
    assert test_client.post(
        f"/api/modules/ap/records/{invoice['id']}/payments",
        json=payment_payload,
    ).status_code == 409

    assert test_client.post(f"/api/modules/ap/records/{invoice['id']}/post").status_code == 200
    assert test_client.post(f"/api/modules/ap/records/{invoice['id']}/payments", json={
        **payment_payload,
        "payment_reference": "BANK-WRONG-ACCOUNT",
        "cash_account_code": "5000",
    }).status_code == 422
    periods = test_client.get("/api/fiscal-periods").json()
    april = next(period for period in periods if period["start_date"] == "2026-04-01")
    assert test_client.post(f"/api/fiscal-periods/{april['id']}/close").status_code == 200
    assert test_client.post(f"/api/modules/ap/records/{invoice['id']}/payments", json={
        **payment_payload,
        "payment_reference": "BANK-CLOSED-PERIOD",
    }).status_code == 409


def test_budget_variance_and_financial_statements_use_posted_entries(test_client):
    activate_test_year(test_client)
    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "1000", "Bank", "Asset")
    create_account(test_client, "3000", "Owner equity", "Equity")
    budget = test_client.post(
        "/api/modules/budgeting/records",
        json={
            "name": "Office expense budget",
            "status": "Approved",
            "data": {
                "account_code": "5000",
                "start_date": "2026-04-01",
                "end_date": "2027-03-31",
                "amount": 200,
            },
        },
    )
    assert budget.status_code == 201
    opening = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Opening capital",
            "data": {
                "document_no": "JE-OPENING",
                "posting_date": "2026-04-01",
                "lines": [
                    {"account_code": "1000", "debit": 200, "credit": 0},
                    {"account_code": "3000", "debit": 0, "credit": 200},
                ],
            },
        },
    ).json()
    assert test_client.post(f"/api/modules/journal-entry/records/{opening['id']}/post").status_code == 200
    journal = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "April expense",
            "data": {
                "document_no": "JE-BUDGET",
                "posting_date": "2026-04-10",
                "lines": [
                    {"account_code": "5000", "debit": 125.5, "credit": 0},
                    {"account_code": "1000", "debit": 0, "credit": 125.5},
                ],
            },
        },
    ).json()
    assert test_client.post(f"/api/modules/journal-entry/records/{journal['id']}/post").status_code == 200

    variance = test_client.get("/api/accounting/budget-variance").json()
    assert variance[0]["budget_minor"] == 20000
    assert variance[0]["actual_minor"] == 12550
    assert variance[0]["variance_minor"] == 7450
    income = test_client.get(
        "/api/accounting/financial-report?report_type=income_statement&start_date=2026-04-01&end_date=2026-04-30"
    ).json()
    assert income["total_expenses_minor"] == 12550
    assert income["net_income_minor"] == -12550
    balance_sheet = test_client.get(
        "/api/accounting/financial-report?report_type=balance_sheet&end_date=2026-04-30"
    ).json()
    assert balance_sheet["total_assets_minor"] == 7450
    assert balance_sheet["balanced"] is True


def test_fixed_asset_acquisition_and_sequential_straight_line_depreciation(test_client):
    activate_test_year(test_client)
    create_account(test_client, "1000", "Bank", "Asset")
    create_account(test_client, "1500", "Equipment", "Asset")
    create_account(test_client, "1590", "Accumulated depreciation", "Asset")
    create_account(test_client, "6100", "Depreciation expense", "Expense")
    asset = test_client.post(
        "/api/modules/fixed-assets/records",
        json={
            "name": "Office equipment",
            "status": "Draft",
            "data": {
                "asset_code": "EQ-1",
                "acquisition_date": "2026-04-15",
                "cost": 1200,
                "salvage_value": 0,
                "useful_life_years": 1,
                "asset_account_code": "1500",
                "acquisition_offset_account_code": "1000",
                "accumulated_depreciation_account_code": "1590",
                "depreciation_expense_account_code": "6100",
            },
        },
    ).json()
    acquired = test_client.post(
        f"/api/modules/fixed-assets/records/{asset['id']}/post-acquisition"
    )
    assert acquired.status_code == 200
    assert acquired.json()["status"] == "Active"
    depreciation = test_client.post(
        f"/api/modules/fixed-assets/records/{asset['id']}/depreciate?period_end=2026-05-31"
    )
    assert depreciation.status_code == 200
    duplicate = test_client.post(
        f"/api/modules/fixed-assets/records/{asset['id']}/depreciate?period_end=2026-05-31"
    )
    assert duplicate.status_code == 409
    next_month = test_client.post(
        f"/api/modules/fixed-assets/records/{asset['id']}/depreciate?period_end=2026-06-30"
    )
    assert next_month.status_code == 200
    ledger = test_client.get("/api/accounting/general-ledger").json()
    depreciation_lines = [entry for entry in ledger if entry["document_no"].startswith("DEP-EQ-1")]
    assert sum(entry["debit_minor"] for entry in depreciation_lines) == 20000
    assert sum(entry["credit_minor"] for entry in depreciation_lines) == 20000
    assert test_client.patch(
        f"/api/modules/fixed-assets/records/{asset['id']}",
        json={"data": {"cost": 1}},
    ).status_code == 409


def test_dashboard_counts_and_recent_transactions_come_from_workspace_data(test_client):
    activate_test_year(test_client)
    create_account(test_client, "1000", "Bank", "Asset")
    create_account(test_client, "3000", "Owner equity", "Equity")
    posted = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Posted opening balance",
            "data": {
                "document_no": "JE-DASH-1",
                "posting_date": "2026-04-01",
                "lines": [
                    {"account_code": "1000", "debit": 100, "credit": 0},
                    {"account_code": "3000", "debit": 0, "credit": 100},
                ],
            },
        },
    ).json()
    draft = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Draft must stay hidden",
            "data": {
                "document_no": "JE-DASH-DRAFT",
                "posting_date": "2026-04-02",
                "lines": [
                    {"account_code": "1000", "debit": 10, "credit": 0},
                    {"account_code": "3000", "debit": 0, "credit": 10},
                ],
            },
        },
    ).json()
    assert test_client.post(f"/api/modules/journal-entry/records/{posted['id']}/post").status_code == 200

    dashboard = test_client.get("/api/accounting/dashboard-summary?period=This Year").json()

    assert dashboard["kpis"]["accounts"] == 2
    assert dashboard["kpis"]["years"] == 1
    assert dashboard["kpis"]["periods"] == 12
    assert [row["doc"] for row in dashboard["recent_transactions"]] == ["JE-DASH-1"]
    assert dashboard["recent_transactions"][0]["amount_minor"] == 10000
    assert draft["status"] == "Draft"


def test_closed_fiscal_period_rejects_journal_posting(test_client):
    year = activate_test_year(test_client)
    periods = test_client.get("/api/fiscal-periods")
    assert periods.status_code == 200
    april = periods.json()[0]
    assert april["fiscal_year_code"] == year["code"]
    assert test_client.post(f"/api/fiscal-periods/{april['id']}/close").status_code == 200

    create_account(test_client, "5000", "Office expense", "Expense")
    create_account(test_client, "1000", "Bank", "Asset")
    record = test_client.post(
        "/api/modules/journal-entry/records",
        json={
            "name": "Closed period journal",
            "data": {
                "document_no": "JE-CLOSED",
                "posting_date": "2026-04-10",
                "lines": [
                    {"account_code": "5000", "debit": 100, "credit": 0},
                    {"account_code": "1000", "debit": 0, "credit": 100},
                ],
            },
        },
    ).json()

    response = test_client.post(f"/api/modules/journal-entry/records/{record['id']}/post")
    assert response.status_code == 409


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
