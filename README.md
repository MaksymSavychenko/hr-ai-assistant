# HR AI Assistant

AI-powered HR self-service portal prototype built with Python and Streamlit.

---

## Project Overview

This project is a prototype of an HR Decision Support System (DSS) designed to help employees interact with HR processes through a modern AI-powered portal.

The system combines:

* employee authentication
* employee profile management
* HR request workflows
* business rule validation
* manager approval process
* future AI / RAG integration

The goal of the project is to demonstrate how Large Language Models (LLMs), Retrieval-Augmented Generation (RAG), and workflow automation can improve HR self-service operations.

---

## Current Features

### Employee Portal

* Login system
* Employee profile sidebar
* HR assistant chat interface
* Birthday leave request generation
* Validation rules for birthday leave eligibility
* My HR Requests section

### Business Rules

* Birthday leave allowed only within 30 days before birthday
* Birthday leave can only be used once per year
* Automatic calculation of birthday leave date using current year
* Duplicate request prevention

### Manager Portal

* Manager login
* Pending requests dashboard
* Approve / Reject workflow
* Request status management

### Data Storage

Currently the system uses CSV-based storage:

* `employees.csv` — employee profiles
* `hr_requests.csv` — HR requests history

The architecture is intentionally designed so that CSV storage can later be replaced with SQL database without changing the UI layer.

---

## Tech Stack

| Component       | Technology |
| --------------- | ---------- |
| Frontend/UI     | Streamlit  |
| Backend         | Python     |
| Data Processing | Pandas     |
| Storage         | CSV files  |
| IDE             | PyCharm    |
| Version Control | GitHub     |

---

## Project Structure

```text
hr-ai-assistant/
│
├── app.py
├── data/
│   ├── employees.csv
│   └── hr_requests.csv
│
├── src/
│   ├── auth.py
│   └── requests.py
│
├── requirements.txt
└── README.md
```

---

## Demo Users

| Username | Role     |
| -------- | -------- |
| anna     | Employee |
| mark     | Employee |
| sofia    | Employee |
| olena    | Manager  |

Demo password for all users:

```text
1234
```

---

## Example Workflow

### Employee Scenario

1. Employee logs into the portal
2. Employee asks for birthday leave
3. System validates eligibility rules
4. System generates formal HR request
5. Employee submits request
6. Request is stored in HR requests database

### Manager Scenario

1. Manager logs into manager dashboard
2. Manager sees pending requests
3. Manager reviews request details
4. Manager approves or rejects request
5. Request status is updated

---

## Future Development

Planned next steps:

* OpenAI API integration
* Retrieval-Augmented Generation (RAG)
* HR policy knowledge base
* SQL database integration
* Decision explanation layer

---

## Educational Goal

This project is developed as a university course project focused on:

* Decision Support Systems
* AI-powered workflows
* Human-centered automation
* Business process digitalization
* LLM and RAG integration

---

## Authors

Project team:

* Maksym Savychenko
* Borys Guliaiev
* Sofiia Lichman

---

## Status

Current status:

```text
Working prototype / MVP
```
