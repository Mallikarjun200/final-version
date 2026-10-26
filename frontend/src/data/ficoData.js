// Sample data for the FICO dashboard. Replace with API calls when endpoints exist.

export const kpis = [
  { id: 'companies', label: 'Total Companies', value: '2', tone: 'blue', icon: 'Building2', target: 'company' },
  { id: 'years', label: 'Active Fiscal Years', value: '2', tone: 'green', icon: 'CalendarDays', target: 'fiscal-year' },
  { id: 'periods', label: 'Open Periods', value: '5', tone: 'purple', icon: 'CalendarClock', target: 'fiscal-period' },
  { id: 'accounts', label: 'Total Accounts', value: '128', tone: 'orange', icon: 'ListTree', target: 'chart-of-accounts' },
]

export const recentTransactions = [
  { date: '10-04-2025', doc: 'JE-000123', module: 'Journal Entry', description: 'Rent Expense', amount: 10000, status: 'Posted' },
  { date: '09-04-2025', doc: 'AP-000456', module: 'Accounts Payable', description: 'Supplier Invoice', amount: 50000, status: 'Approved' },
  { date: '08-04-2025', doc: 'AR-000789', module: 'Accounts Receivable', description: 'Customer Invoice', amount: 75000, status: 'Approved' },
  { date: '07-04-2025', doc: 'FA-000321', module: 'Fixed Assets', description: 'Machine Purchase', amount: 500000, status: 'Posted' },
  { date: '06-04-2025', doc: 'BG-000654', module: 'Budgeting', description: 'Annual Budget', amount: 1000000, status: 'Created' },
  { date: '05-04-2025', doc: 'GL-000987', module: 'General Ledger', description: 'Period Close', amount: 0, status: 'In Progress' },
]

export const quickActions = [
  { label: 'Create Journal Entry', icon: 'PencilLine', tone: 'blue', target: 'journal-entry' },
  { label: 'Create AP Invoice', icon: 'FileText', tone: 'green', target: 'ap' },
  { label: 'Create AR Invoice', icon: 'CreditCard', tone: 'purple', target: 'ar' },
  { label: 'Add Fixed Asset', icon: 'Landmark', tone: 'orange', target: 'fixed-assets' },
  { label: 'Create Budget', icon: 'PiggyBank', tone: 'teal', target: 'budgeting' },
  { label: 'Generate Report', icon: 'FileBarChart', tone: 'indigo', target: 'financial-reports' },
]

export const financialSummary = [
  { label: 'Total Income', amount: 1250000, change: '+12%' },
  { label: 'Total Expenses', amount: 875000, change: '+8%' },
  { label: 'Net Profit', amount: 375000, change: '+15%' },
]

export const ficoModules = [
  { id: 'company', title: 'Company', blurb: 'Manage companies and business units', icon: 'Building2', tone: 'blue' },
  { id: 'chart-of-accounts', title: 'Chart of Accounts', blurb: 'Maintain your COA structure and accounts', icon: 'ListTree', tone: 'green' },
  { id: 'journal-entry', title: 'Journal Entry', blurb: 'Record and manage journal entries', icon: 'PencilLine', tone: 'purple' },
  { id: 'general-ledger', title: 'General Ledger', blurb: 'View ledger and trial balance', icon: 'BookOpen', tone: 'blue' },
  { id: 'trial-balance', title: 'Trial Balance', blurb: 'Review account balances and verify debits equal credits', icon: 'Scale', tone: 'indigo' },
  { id: 'ap', title: 'Accounts Payable', blurb: 'Supplier invoices and payments', icon: 'FileText', tone: 'green' },
  { id: 'ar', title: 'Accounts Receivable', blurb: 'Customer invoices and receipts', icon: 'CreditCard', tone: 'purple' },
  { id: 'fixed-assets', title: 'Fixed Assets', blurb: 'Track assets and depreciation', icon: 'Landmark', tone: 'orange' },
  { id: 'budgeting', title: 'Budgeting', blurb: 'Plan and monitor budgets', icon: 'PiggyBank', tone: 'teal' },
  { id: 'gst', title: 'GST', blurb: 'Tax setup and returns', icon: 'Percent', tone: 'indigo' },
  { id: 'financial-reports', title: 'Financial Reports', blurb: 'Statements and analysis', icon: 'FileBarChart', tone: 'blue' },
]

// Sidebar structure. `label` is what the user sees; `id` is the route key.
export const ficoNav = [
  { id: 'company', label: 'Company', icon: 'Building2' },
  { id: 'fiscal-year', label: 'Fiscal Year', icon: 'CalendarDays' },
  { id: 'fiscal-period', label: 'Fiscal Period', icon: 'CalendarClock' },
  { id: 'chart-of-accounts', label: 'Chart of Accounts', icon: 'ListTree' },
  { id: 'journal-entry', label: 'Journal Entry', icon: 'PencilLine' },
  { id: 'general-ledger', label: 'General Ledger', icon: 'BookOpen' },
  { id: 'trial-balance', label: 'Trial Balance', icon: 'Scale' },
  { id: 'ap', label: 'Accounts Payable (AP)', icon: 'FileText' },
  { id: 'ar', label: 'Accounts Receivable (AR)', icon: 'CreditCard' },
  { id: 'fixed-assets', label: 'Fixed Assets', icon: 'Landmark' },
  { id: 'budgeting', label: 'Budgeting', icon: 'PiggyBank' },
  { id: 'gst', label: 'GST', icon: 'Percent' },
  { id: 'financial-reports', label: 'Financial Reports', icon: 'FileBarChart' },
]

export const inr = (n) =>
  '₹ ' + new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)

export const inrWhole = (n) =>
  '₹ ' + new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n)
