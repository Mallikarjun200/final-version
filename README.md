# Stackly OneERP — Fiscal Year

Stackly OneERP includes a React/Vite frontend and a Python FastAPI API for FICO management. Fiscal years automatically create twelve accounting periods and begin in `DRAFT` status. Users can register and sign in; module records are saved in the database and scoped to the signed-in account.

## Open the complete app in one browser tab

```bash
cd frontend
npm install
npm run build
cd ..
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` to use the React app and Python API from one URL. The browser app sends API requests to the same host. Interactive API docs are at `/docs`; the readiness check is at `/health`.

## Frontend development mode

```bash
npm run dev
```

Run this command from the project root. Vite proxies `/api` and `/health` requests to FastAPI at `127.0.0.1:8000`; start the API separately in another terminal with `npm run api` (or the `uvicorn` command above).

The API defaults to a local SQLite database (`stackly_oneerp.db`) and creates its tables on startup. To use MySQL, set `DATABASE_URL` to a SQLAlchemy URL such as `mysql+pymysql://user:password@localhost:3306/stackly_oneerp` and initialize the schema with `database/schema.sql`.

## Sign-in and modules

Open the app and choose **Create an account** on the login page. Passwords are stored as salted PBKDF2 hashes; sign-in uses a seven-day, HTTP-only session cookie. Sign out revokes the stored session. Set `COOKIE_SECURE=true` when serving over HTTPS.

Company, Fiscal Period, Chart of Accounts, Journal Entry, Accounts Payable, Accounts Receivable, Fixed Assets, Budgeting, GST, and Financial Reports are connected to the signed-in workspace. The dashboard counts, posted transactions, and income/expense summaries are loaded from workspace data rather than sample figures. Only posted documents affect the live Trial Balance and General Ledger; drafts remain outside the ledger. Journal entries must balance, and posting is restricted to an active fiscal year and an open period.

The current India/INR accounting MVP supports AP/AR invoice posting with configured IGST or CGST+SGST rates, partial or full supplier payments and customer receipts against posted invoices, fixed-asset acquisition and sequential monthly straight-line depreciation, approved expense budgets versus posted actuals, a posted-GST summary, and generated income-statement and balance-sheet views. Payments and receipts require an active Asset cash/bank account, a unique reference, and an open fiscal period; they create balanced ledger entries and cannot exceed the invoice balance. GST amounts are rounded to paise; configured CGST and SGST component rates are calculated separately. Asset depreciation starts in the month after acquisition and requires month-end posting in sequence. The balance sheet presents current earnings as unclosed equity.

This is a management MVP, not production-grade accounting or tax software. It does not provide bank reconciliation, tax returns/filing, cess, cash-flow statements, multi-currency accounting, automated period-end closing, partial-month depreciation, or formal accounting approval controls. It does not validate Indian tax law or replace review by a qualified accountant. Verify configurations and reports before relying on them.

## Deploy to Render

The root `render.yaml` defines the combined web service and a persistent PostgreSQL database. The web service uses Render's free plan and may sleep when idle; the database uses Render's paid `basic-256mb` plan and requires billing approval.

1. Push this repository to GitHub and open the [Render Blueprint deployment page](https://render.com/deploy).
2. Connect `Mallikarjun200/final-version` and select the Blueprint in the repository root.
3. Review the PostgreSQL plan and any charges, then approve deployment.
4. Wait for the `stackly-oneerp` service health check to pass. Render will show its shareable `https://stackly-oneerp.onrender.com` URL in the service dashboard.
5. Create your account from that URL. Do not use the local SQLite database for hosted production data.

## Fiscal-year workflow

1. Create a fiscal year for a company code using either the April–March or January–December calendar.
2. The API stores the year and its twelve accounting periods in one database transaction.
3. Activate the year when approved. A company can have only one active fiscal year; overlapping date ranges and duplicate company/year codes are rejected.

## Validate

```bash
cd frontend && npm run lint && npm run build
cd .. && pytest backend/test_main.py
```

The one-URL setup is for local use. Public deployment requires hosting the built app and API on an internet-accessible server.
