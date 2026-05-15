import json
from datetime import date
from pathlib import Path
from typing import Dict

import pandas as pd

from src.auth import get_user_profile


LEAVE_BALANCES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "leave_balances.csv"
FAISS_METADATA_FILE = Path(__file__).resolve().parent.parent.parent / "vector_store" / "faiss_index" / "metadata.json"


def _load_employee_profile(employee_username: str) -> Dict:
    profile = get_user_profile(employee_username)
    if not profile:
        raise ValueError(f"Employee profile not found for username: {employee_username}")
    return {**profile, "username": employee_username}


def _get_annual_leave_remaining(employee_profile: Dict, year: int) -> int:
    """
    Read annual leave remaining from employee profile when available,
    otherwise fallback to leave_balances.csv.
    """
    profile_value = employee_profile.get("annual_leave_remaining", "")
    if str(profile_value).strip() != "":
        try:
            return int(float(profile_value))
        except (TypeError, ValueError):
            pass

    if not LEAVE_BALANCES_FILE.exists():
        return 0

    employee_id = employee_profile.get("employee_id", "")
    df = pd.read_csv(LEAVE_BALANCES_FILE).fillna("")
    rows = df[
        (df["employee_id"].astype(str) == str(employee_id))
        & (df["calendar_year"].astype(str) == str(year))
        & (df["leave_type"].astype(str).str.lower() == "annual_leave")
    ]
    if rows.empty:
        return 0

    row = rows.iloc[0]
    try:
        return int(float(row.get("remaining_days", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _load_sales_june_policy_sources() -> list[str]:
    """
    Best-effort source discovery from local FAISS metadata.
    Returns unique source titles related to Sales June restrictions.
    """
    if not FAISS_METADATA_FILE.exists():
        return []

    try:
        payload = json.loads(FAISS_METADATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(payload, dict):
        records = payload.get("records", [])
    elif isinstance(payload, list):
        records = payload
    else:
        records = []
    seen = set()
    sources = []
    for item in records:
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        title = str(metadata.get("title", "")).strip()
        lower = title.lower()
        if title and "sales" in lower and "june" in lower and title not in seen:
            seen.add(title)
            sources.append(title)
    return sources


def check_annual_leave_eligibility(
    employee_username: str,
    requested_leave_date: str,
    requested_days: int,
) -> dict:
    """
    Flow 2 annual leave deterministic decision support.
    """
    employee_profile = _load_employee_profile(employee_username)
    requested_days = int(requested_days) if requested_days else 0
    if requested_days < 1:
        requested_days = 1

    request_year = date.fromisoformat(requested_leave_date).year
    request_month = date.fromisoformat(requested_leave_date).month
    annual_leave_remaining = _get_annual_leave_remaining(employee_profile, request_year)
    balance_sufficient = requested_days <= annual_leave_remaining

    manager_approval_required = True
    department = str(employee_profile.get("department", "")).strip().lower()
    sales_june_restriction_applies = department == "sales" and request_month == 6
    head_of_department_approval_required = sales_june_restriction_applies and requested_days > 5

    sales_june_policy_summary = ""
    additional_approval_message = ""
    policy_sources = []
    if sales_june_restriction_applies:
        sales_june_policy_summary = (
            "Temporary Sales June vacation restriction: requests in June for more than 5 consecutive "
            "working days require additional Head of Department approval."
        )
        if head_of_department_approval_required:
            additional_approval_message = (
                "Because you are in Sales and the request is in June for more than 5 consecutive working days, "
                "additional Head of Department approval would also be required."
            )
        else:
            additional_approval_message = (
                "Because you are in Sales and the request is in June for 5 or fewer consecutive working days, "
                "standard manager approval applies."
            )
        policy_sources = _load_sales_june_policy_sources()

    passed_conditions = []
    failed_conditions = []

    if balance_sufficient:
        decision_status = "ELIGIBLE"
        decision_title = "✅ Eligible for Annual Leave"
        passed_conditions.append("Requested days are within annual leave remaining balance")
        explanation = f"You requested {requested_days} annual leave days, and you have {annual_leave_remaining} days remaining."
        if additional_approval_message:
            explanation = f"{explanation} {additional_approval_message}"
        next_action = "Submit annual leave request for manager approval."
        if head_of_department_approval_required:
            next_action = "Submit annual leave request and obtain both manager and Head of Department approval."
    else:
        decision_status = "NOT_ELIGIBLE"
        decision_title = "❌ Not eligible for Annual Leave"
        failed_conditions.append("Requested days exceed annual leave remaining balance")
        explanation = f"You requested {requested_days} annual leave days, but you only have {annual_leave_remaining} days remaining."
        if additional_approval_message:
            explanation = f"{explanation} {additional_approval_message}"
        next_action = "Reduce requested days or choose alternative dates before submitting."

    if sales_june_restriction_applies:
        passed_conditions.append("Sales June vacation restriction is applicable")
    if head_of_department_approval_required:
        passed_conditions.append("Additional Head of Department approval is required")

    return {
        "flow_used": "Decision Support (Annual Leave)",
        "policy_summary": (
            "Annual Leave policy check: requested days are compared against annual leave remaining balance. "
            "Manager approval is required."
        ),
        "employee_username": employee_username,
        "requested_leave_date": requested_leave_date,
        "requested_days": requested_days,
        "annual_leave_remaining": annual_leave_remaining,
        "annual_leave_balance_sufficient": balance_sufficient,
        "manager_approval_required": manager_approval_required,
        "head_of_department_approval_required": head_of_department_approval_required,
        "sales_june_restriction_applies": sales_june_restriction_applies,
        "sales_june_policy_summary": sales_june_policy_summary,
        "additional_approval_message": additional_approval_message,
        "decision_status": decision_status,
        "decision_title": decision_title,
        "explanation": explanation,
        "next_action": next_action,
        "passed_conditions": passed_conditions,
        "failed_conditions": failed_conditions,
        "policy_sources": policy_sources,
        "retrieved_chunks": [],
    }
