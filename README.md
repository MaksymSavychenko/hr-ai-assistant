# HR AI Assistant (MVP, CSV + RAG + DSS)

Streamlit HR assistant course project with:
- CSV-based HRIS-style data model (temporary replacement for SQL tables)
- role-based employee/manager portal
- Notion-powered RAG knowledge base
- experimental DSS layer (hybrid RAG + deterministic policy evaluation)

## 1) Current Scope

### Employee portal
- Login using `data/user_accounts.csv`
- Profile + annual leave metric
- One chat entry point: **Ask HR Knowledge Base**
  - **Flow 1 (Policy Q&A)** for general HR policy questions
  - **Flow 2 (Decision Support)** for personal leave decision requests
- "My HR Requests" table (read view from `data/hr_requests.csv`)

### Manager portal
- Pending requests filtered by `manager_username`
- Approve / Reject actions
- Status updates persisted to `data/hr_requests.csv`

## 2) Architecture (Current)

```text
User message in Streamlit
        ↓
Intent Router (rule-based first, LLM fallback only when uncertain)
        ↓
 ┌───────────────────────────────┬──────────────────────────────────┐
 │ policy_qa                     │ birthday_leave_decision /        │
 │                               │ annual_leave_decision            │
 │ Flow 1                        │ Flow 2 (experimental DSS)        │
 │ RAG answer from KB            │ deterministic evaluation +       │
 │ (no personal final decision)  │ policy summary from KB           │
 └───────────────────────────────┴──────────────────────────────────┘
```

## 3) Project Structure

```text
hr-ai-assistant/
├── app.py
├── data/
│   ├── employees.csv
│   ├── user_accounts.csv
│   ├── leave_balances.csv
│   ├── leave_transactions.csv
│   └── hr_requests.csv
├── scripts/
│   ├── build_faiss_index.py
│   ├── debug_notion_access.py
│   ├── test_notion_loader.py
│   ├── test_faiss_retriever.py
│   ├── test_rag_answer.py
│   ├── test_dynamic_policy_rules.py
│   ├── test_birthday_leave_service.py
│   ├── test_annual_leave_service.py
│   ├── test_chat_decision_routing.py
│   └── test_intent_router.py
└── src/
    ├── auth.py
    ├── requests.py
    ├── config/
    │   └── secrets.py
    ├── rag/
    │   ├── notion_loader.py
    │   ├── chunking.py
    │   ├── faiss_store.py
    │   ├── prompts.py
    │   ├── rag_pipeline.py
    │   └── policy_rule_extractor.py
    └── rules/
        ├── intent_router.py
        ├── leave_request_parser.py
        ├── dynamic_evaluator.py
        ├── birthday_leave_service.py
        └── annual_leave_service.py
```

## 4) Data Model

### `employees.csv`
Master employee table with org/role fields:
- `employee_id`, `username`, `full_name`, `department`, `role`, `manager_username`
- `hire_date`, `probation_end_date`, `birthday`
- employment metadata (type, percentage, location, status, email)

### `user_accounts.csv`
MVP authentication table:
- `user_id`, `employee_id`, `username`, `password`, `account_status`
- `employee_id` links to `employees.csv`

### `leave_balances.csv`
Yearly leave snapshot per employee:
- entitlement / used / remaining
- carry-over and expiry fields

### `leave_transactions.csv`
Historical leave ledger:
- accrual, used, carry-over, expiry, adjustment
- optional request linkage

### `hr_requests.csv`
Leave request workflow table:
- request payload + dates + statuses + approval fields
- used by employee history and manager approval UI

## 5) RAG Module Status

Implemented components:
- Notion integration for HR Knowledge Base
- Loading only **Active** records
- Mixed content ingestion:
  - Notion page text
  - PDF attachments
  - EML attachments
- Attachment download to `data/tmp/notion_downloads/`
- Extraction:
  - PDF full-page text
  - EML headers + body
- Document normalization
- Chunking (`~900` chars, overlap `~180`)
- OpenAI embeddings
- FAISS index build/load
- Retrieval + grounded LLM synthesis

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
RAG Answer Generation
```

### EML Metadata

For EML docs, parser extracts:
- `Subject`, `From`, `To`, `Date`, `Message-ID`

Stored fields:
- `email_subject`, `email_from`, `email_to`, `email_date`, `email_message_id`

## 6) Flow 1: Pure RAG Policy Q&A

`ask_hr_knowledge_base(question, employee_context=None, top_k=5)`:
1. Ensures FAISS index exists (builds automatically if missing)
2. Retrieves top chunks
3. Applies department-aware chunk filtering (Sales-specific chunks hidden for non-Sales users)
4. Builds grounded prompt from filtered chunks
5. Returns:
   - `answer`
   - `sources`
   - `retrieved_chunks`

Important:
- Flow 1 is for policy explanation, not final personal eligibility decisions.

## 7) Flow 2: Experimental Decision Support

Flow 2 is triggered from chat by intent routing and currently supports:
- `birthday_leave_decision`
- `annual_leave_decision`

### Birthday Leave DSS (`birthday_leave_service.py`)
- Retrieves birthday policy context from FAISS
- Extracts/derives policy constraints
- Applies deterministic checks using employee data + request history:
  - probation completion
  - birthday window (`±30` calendar days around birthday in requested year)
  - request timing (3 working days)
  - once per calendar year
  - balance/day-limit checks
- Handles mixed requests (birthday + additional annual leave)
- Applies Sales June stacking rule for additional annual leave in June

### Annual Leave DSS (`annual_leave_service.py`)
- Compares requested days vs `annual_leave_remaining`
- Applies manager approval requirement
- Applies Sales June additional approval rule for requests over 5 days in June

## 8) Intent Routing (Hybrid)

`intent_router.py` routing strategy:
1. Rule-based detection with confidence
2. LLM fallback only when rule confidence is low

Supported intents:
- `policy_qa`
- `birthday_leave_decision`
- `annual_leave_decision`
- `unknown`

Returned routing metadata:
- `intent`
- `router_used` (`rule_based` or `llm_fallback`)
- `confidence`
- `reason`
- `mixed_intent_detected`

Mixed-intent handling:
- Example: "What is the birthday leave policy? Can I take this leave on June 30?"
- Routed to Flow 2 (`birthday_leave_decision`) so UI can show:
  - policy summary
  - personal deterministic decision

## 9) Streamlit UX Notes

- App banner marks this as **Experimental DSS Version**
- DSS response shows concise decision by default
- Detailed checks are under collapsed expanders:
  - `Evaluation details`
  - `Sources`
  - `Routing details`
  - `Technical debug details`
- For mixed intent, UI shows **Policy summary** above DSS decision card

## 10) Setup

Install dependencies:

```bash
.venv/bin/pip install -r requirements.txt
```

Create `.env` (local dev):

```env
OPENAI_API_KEY=...
NOTION_TOKEN=...
NOTION_DATABASE_ID=...
```

Run app:

```bash
.venv/bin/streamlit run app.py --server.port 8501
```

## 11) Key Commands

RAG / ingestion:

```bash
.venv/bin/python scripts/test_notion_loader.py
.venv/bin/python scripts/build_faiss_index.py
.venv/bin/python scripts/test_faiss_retriever.py
.venv/bin/python scripts/test_rag_answer.py
```

Routing / DSS:

```bash
.venv/bin/python scripts/test_intent_router.py
.venv/bin/python scripts/test_chat_decision_routing.py
.venv/bin/python scripts/test_birthday_leave_service.py
.venv/bin/python scripts/test_annual_leave_service.py
.venv/bin/python scripts/test_dynamic_policy_rules.py
```

## 12) Streamlit Cloud Notes

Secrets are resolved from:
1. local `.env`
2. `st.secrets` (Cloud)

Required secrets:
- `OPENAI_API_KEY`
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`

If `vector_store/faiss_index` is missing at runtime, app auto-builds index from Notion and continues.

## 13) Test Users (MVP Auth)

- Password for all accounts in `data/user_accounts.csv`: `test123`
- Account status: `active`

Use any username from `data/user_accounts.csv` (employees and managers).

## 14) Security / Git Ignore

Do not commit:
- `.env`
- `vector_store/`
- `data/tmp/`

## 15) Current Limitations

- CSV storage is not concurrent-safe (MVP only)
- Auth is intentionally simple (no hashing/OAuth/MFA)
- Flow 2 is experimental and scoped to selected leave scenarios
- RAG quality depends on indexed Notion content quality and coverage

