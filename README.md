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
- RAG is backend-only right now (not connected to Streamlit UI yet)

## 12) Planned Next Step

Replace CSV data-access modules with SQL repositories while keeping Streamlit UI and workflow logic stable.

## RAG Module Status

The project now includes an initial RAG backend prototype.

Implemented components:

- Notion integration for HR Knowledge Base
- Loading active records from Notion database
- Support for mixed content types:
  - Notion text pages
  - PDF attachments
  - EML email files
- Attachment detection and downloading
- Text extraction from PDF and EML files
- Document normalization
- Chunking
- OpenAI embeddings
- FAISS vector index creation
- Local FAISS retrieval testing
- LLM answer synthesis from retrieved context (LangChain + ChatOpenAI)
- Source-grounded response packaging (`answer`, `sources`, `retrieved_chunks`)

Current RAG flow:

```text
Notion HR Knowledge Base
        ↓
Notion Loader
        ↓
PDF / EML / Notion Text Extraction
        ↓
Document Normalization
        ↓
Chunking
        ↓
OpenAI Embeddings
        ↓
FAISS Vector Store
        ↓
Retriever Test
        ↓
Grounded Prompt Builder
        ↓
ChatOpenAI (Temperature = 0)
        ↓
Final Answer + Sources
```

Test commands:

```bash
.venv/bin/python scripts/test_notion_loader.py
.venv/bin/python scripts/build_faiss_index.py
.venv/bin/python scripts/test_faiss_retriever.py
.venv/bin/python scripts/test_rag_answer.py
```

Important:

The following files and folders should not be committed to GitHub:

- `.env`
- `vector_store/`
- `data/tmp/`

The `.env` file should contain local secrets:

```env
NOTION_TOKEN=...
NOTION_DATABASE_ID=...
OPENAI_API_KEY=...
```

Current RAG status:

`Notion ingestion + FAISS retrieval + LLM grounded answer synthesis working`

RAG indexing behavior:

- `scripts/build_faiss_index.py` performs a **full rebuild** each run.
- The script overwrites:
  - `vector_store/faiss_index/index.faiss`
  - `vector_store/faiss_index/metadata.json`
- The new index contains only the records currently loaded from Notion.

Notion status filter behavior:

- Only records with `Status = Active` are indexed.
- Records with `Status = Archived` are skipped and do not enter the vector store.

Next step:

Integrate the RAG answer pipeline into Streamlit chat UI with response streaming and source rendering.
