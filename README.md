# HR AI Assistant (MVP, CSV-Based)

Streamlit HR assistant prototype with employee and manager workflows.  
This project simulates a realistic HRIS/RAG-ready architecture using CSV files as temporary database tables.

## 1) What This Project Does

- Authenticates users from `data/user_accounts.csv`
- Loads employee master data from `data/employees.csv`
- Supports employee and manager roles
- Generates birthday leave draft requests
- Applies policy checks:
  - birthday leave eligibility window (next 30 days)
  - duplicate birthday leave prevention (same year, non-rejected request already exists)
- Persists workflow requests in `data/hr_requests.csv`
- Supports manager approve/reject actions
- Uses `data/leave_balances.csv` and `data/leave_transactions.csv` as HR leave data model layers

## 2) Current Tech Stack

- Python 3.11
- Streamlit
- Pandas
- CSV storage (MVP replacement for future SQL tables)

## 3) Project Structure

```text
hr-ai-assistant/
├── app.py
├── src/
│   ├── auth.py
│   └── requests.py
└── data/
    ├── employees.csv
    ├── user_accounts.csv
    ├── leave_balances.csv
    ├── leave_transactions.csv
    └── hr_requests.csv
```

## 4) Data Tables

### `employees.csv` (Master Employee Directory)

Contains identity and organizational attributes:
- `employee_id` (primary business key)
- `username`, `full_name`, `department`, `role`
- reporting line: `manager_username`
- employment dates and status (`hire_date`, `probation_end_date`, `active_status`)
- profile fields (`birthday`, `employment_type`, `employment_percentage`, `office_location`, `email`)

### `user_accounts.csv` (MVP Authentication Table)

Simple login dataset:
- `user_id`, `employee_id`, `username`, `password`, `account_status`

Notes:
- all current test users are `active`
- MVP plain password is used intentionally (no hashing/JWT/OAuth/MFA)

### `leave_balances.csv` (Current Balance Snapshot)

Per employee / year / leave type:
- `leave_type`: `annual_leave`, `birthday_leave`, `sick_leave`, `unpaid_leave`
- entitlement, used, remaining
- carry-over values and expiry date

### `leave_transactions.csv` (Historical Leave Ledger)

Stores leave movements:
- `transaction_type`: `accrual`, `used`, `carry_over`, `expiry`, `adjustment`
- optional `related_request_id` links request-based usage to `hr_requests.csv`

### `hr_requests.csv` (Workflow Table)

Employee request lifecycle:
- request details, requested leave dates, manager routing
- status, approval metadata, policy check result
- rejection reason and source channel

## 5) Table Relationships

- `employees.employee_id` is the central employee key
- `user_accounts.employee_id` -> `employees.employee_id`
- `leave_balances.employee_id` -> `employees.employee_id`
- `leave_transactions.employee_id` -> `employees.employee_id`
- `hr_requests.employee_id` -> `employees.employee_id`
- `employees.manager_username` is used for manager routing
- `leave_transactions.related_request_id` references `hr_requests.request_id` where applicable

## 6) Policy Logic Implemented in App

### Birthday Leave Date Rule
- Birth year is ignored for leave date calculation
- Leave date is built from employee birthday month/day + current year

### Birthday Leave 30-Day Eligibility
- Request generation allowed only if birthday date is between:
  - today
  - today + 30 days

### Duplicate Birthday Leave Prevention
- New birthday leave request is blocked if employee already has non-rejected birthday leave request in same year

## 7) Role Workflows

### Employee Portal
- profile view
- leave metrics (from balances)
- chat-like mock assistant responses
- birthday leave draft generation
- submit request to HR workflow
- request history table

### Manager Portal
- pending request list filtered by `manager_username`
- approve / reject actions
- status updates written to `hr_requests.csv`

## 8) Demo Data Scenarios Included

The dataset includes policy test scenarios such as:
- birthday leave approved (eligible case)
- birthday leave rejected (probation, no entitlement, invalid timing window)
- annual leave approved (submitted in advance)
- annual leave warning/late submission
- annual leave rejected (insufficient balance)
- Sales June special handling (standard vs HoD approval logic in data)
- carry-over usage before expiry and expiry after March 31

## 9) Run the App

From project root:

```bash
.venv/bin/streamlit run app.py --server.port 8502
```

If `8502` is busy, use another port.

## 10) Test Login Credentials (MVP)

Use the following usernames from `data/user_accounts.csv` with:

- password: `test123`

| Username | Role |
| --- | --- |
| `laura.chen` | Employee |
| `omar.khan` | Employee |
| `nina.petrov` | Employee |
| `victor.lee` | Employee |
| `elena.rossi` | Employee |
| `grace.nowak` | Employee |
| `dmitri.sokolov` | Manager |
| `iryna.koval` | Manager |
| `serhii.bondar` | Manager |
| `oliver.grant` | Manager |
| `kateryna.melnyk` | Manager |

## 11) Known MVP Limits

- CSV is not concurrent-safe like a real database
- no hashing or enterprise auth
- policy checks are intentionally scoped to core course requirements
- no OpenAI/RAG integration yet (prepared for later phase)

## 12) Planned Next Step

Replace CSV data-access modules with SQL repositories while keeping Streamlit UI and workflow logic stable.
