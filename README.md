# HR AI Assistant (MVP, CSV + RAG)

Streamlit HR assistant prototype with:
- CSV-based HRIS data model (MVP)
- role-based portal (employee / manager)
- Notion-powered RAG knowledge base

CSV files are temporary table replacements for a future SQL architecture.

## 1) Current Product Scope

### Employee side
- Login via `data/user_accounts.csv`
- Profile + leave metrics
- **Flow 1: Pure RAG Policy Q&A** in UI
  - answers from HR knowledge base only
  - source list + retrieval debug panel
- My HR requests table (read view)

### Manager side
- Pending request list filtered by `manager_username`
- Approve / Reject actions
- Status updates persisted in `data/hr_requests.csv`

## 2) Tech Stack

- Python 3.11
- Streamlit
- Pandas
- Notion API (`notion-client`)
- LangChain + ChatOpenAI
- OpenAI embeddings
- FAISS
- CSV storage (MVP replacement for SQL)

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
│   ├── test_notion_loader.py
│   ├── test_faiss_retriever.py
│   ├── test_rag_answer.py
│   └── test_dynamic_policy_rules.py
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
        └── dynamic_evaluator.py
```

## 4) Data Model

### `employees.csv`
Master employee table:
- identity, org, manager routing
- probation end, birthday, employment details

### `user_accounts.csv`
MVP auth table:
- `user_id`, `employee_id`, `username`, `password`, `account_status`

### `leave_balances.csv`
Yearly leave snapshot:
- annual, birthday, sick, unpaid leave balances
- carry-over and expiry fields

### `leave_transactions.csv`
Leave ledger:
- accrual / used / carry-over / expiry / adjustment movements
- `related_request_id` links to workflow where applicable

### `hr_requests.csv`
Workflow table:
- request payload + dates + approval status + policy results

## 5) RAG Pipeline Status

Implemented:
- Notion ingestion with `Status = Active` filter
- mixed document support:
  - Notion page text
  - PDF attachments
  - EML attachments
- attachment download to `data/tmp/notion_downloads/`
- text extraction:
  - PDF: full pages
  - EML: headers + body
- chunking
- OpenAI embeddings
- FAISS build + load + retrieval
- grounded LLM answer synthesis

Return structure from `ask_hr_knowledge_base(...)`:
- `answer`
- `sources`
- `retrieved_chunks`

### EML Parsing Update

EML parser now extracts standard headers:
- `Subject`
- `From`
- `To`
- `Date`
- `Message-ID`

Stored metadata fields:
- `email_subject`
- `email_from`
- `email_to`
- `email_date`
- `email_message_id`

For embedding text, EML content is normalized as:

```text
EMAIL SUBJECT: ...
EMAIL FROM: ...
EMAIL TO: ...
EMAIL DATE: ...
EMAIL MESSAGE-ID: ...

<clean email body>
```

## 6) Streamlit RAG UI (Flow 1)

Employee portal includes a single policy assistant flow:
- **Policy Q&A mode**
- helper text clarifies it does not make personal eligibility decisions
- question input + example question buttons
- all answers come from `ask_hr_knowledge_base(question, top_k=5)`

Display order:
1. Answer
2. Sources (deduplicated per page/document in UI)
3. Retrieval details / Debug view

### Debug Panel

`Retrieval details / Debug view` shows raw retrieval ranking (no chunk dedup):
- rank
- distance
- title, category, content type
- attachment name
- email date
- preview text
- nested expander with full chunk text + metadata

## 7) Streamlit Cloud Readiness

### Secrets resolution

`src/config/secrets.py` resolves secrets from:
1. local `.env`
2. `st.secrets` (Streamlit Cloud)

Required keys:
- `OPENAI_API_KEY`
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`

### FAISS bootstrap behavior in cloud

When first query is executed:
- if `vector_store/faiss_index` exists -> load it
- if missing -> auto-build index from Notion, save to `vector_store/faiss_index`, continue query

During auto-build, UI shows:
- `Building HR knowledge base index. This may take a moment.`

## 8) Run Locally

```bash
.venv/bin/streamlit run app.py --server.port 8502
```

If the port is busy, use another one.

## 9) RAG Test Commands

```bash
.venv/bin/python scripts/test_notion_loader.py
.venv/bin/python scripts/build_faiss_index.py
.venv/bin/python scripts/test_faiss_retriever.py
.venv/bin/python scripts/test_rag_answer.py
.venv/bin/python scripts/test_dynamic_policy_rules.py
```

## 10) Streamlit Cloud Secrets Example

In Streamlit Cloud app settings, add:

```toml
OPENAI_API_KEY = "..."
NOTION_TOKEN = "..."
NOTION_DATABASE_ID = "..."
```

## 11) Test Login Credentials (MVP)

Use usernames from `data/user_accounts.csv` with password:
- `test123`

Managers:
- `dmitri.sokolov`
- `iryna.koval`
- `serhii.bondar`
- `oliver.grant`
- `kateryna.melnyk`

Employees:
- `laura.chen`
- `omar.khan`
- `nina.petrov`
- `victor.lee`
- `elena.rossi`
- `grace.nowak`

## 12) Security / Git Ignore

Do not commit:
- `.env`
- `vector_store/`
- `data/tmp/`

## 13) MVP Limits

- CSV is not concurrent-safe (unlike real DB)
- auth is intentionally simple for MVP
- policy decisioning in UI is not using dynamic evaluator yet
- RAG may return only what is present in indexed knowledge base

## 14) Next Planned Step

Connect policy-rule extraction + deterministic evaluator into app flow (Flow 2),
so LLM extracts structured rules and Python makes final eligibility decisions.
