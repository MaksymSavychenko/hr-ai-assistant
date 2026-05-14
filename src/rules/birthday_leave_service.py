from datetime import date
from typing import Dict, List

from src.auth import get_user_profile
from src.rag.policy_rule_extractor import extract_birthday_leave_rules
from src.requests import get_employee_requests
from src.rules.dynamic_evaluator import evaluate_policy_rules


def _load_employee_profile(employee_username: str) -> Dict:
    """
    Load employee profile from existing auth/profile data source.
    Keeps the same profile shape used by app.py and adds username.
    """
    profile = get_user_profile(employee_username)
    if not profile:
        raise ValueError(f"Employee profile not found for username: {employee_username}")

    return {**profile, "username": employee_username}


def _load_employee_request_history(employee_profile: Dict) -> List[Dict]:
    """
    Load request history from existing requests data source.
    Converts DataFrame rows into list[dict] for evaluator.
    """
    employee_id = employee_profile.get("employee_id", "")
    requests_df = get_employee_requests(employee_id)
    if requests_df.empty:
        return []

    history = requests_df.to_dict("records")
    for item in history:
        # Add username for evaluator user-scoping logic.
        item["employee_username"] = employee_profile.get("username", "")
    return history


def check_birthday_leave_eligibility(employee_username: str, requested_leave_date: str) -> Dict:
    """
    Flow 2 service:
    1) Load employee profile
    2) Load employee request history
    3) Extract latest Birthday Leave rules from RAG
    4) Apply deterministic evaluator
    5) Return eligibility response payload
    """
    employee_profile = _load_employee_profile(employee_username)
    request_history = _load_employee_request_history(employee_profile)
    rules = extract_birthday_leave_rules()

    request_data = {
        "employee_username": employee_username,
        "request_type": "birthday_leave",
        "requested_leave_date": requested_leave_date,
        # Service call time is treated as submission date.
        "request_submitted_date": date.today().isoformat(),
    }

    evaluation = evaluate_policy_rules(
        employee_profile=employee_profile,
        request_data=request_data,
        request_history=request_history,
        rules=rules,
    )

    return {
        "employee_username": employee_username,
        "requested_leave_date": requested_leave_date,
        "eligible": evaluation.get("eligible", False),
        "requires_manager_approval": evaluation.get("requires_manager_approval", False),
        "passed_conditions": evaluation.get("passed_conditions", []),
        "failed_conditions": evaluation.get("failed_conditions", []),
        "explanation": evaluation.get("explanation", ""),
        "policy_sources": rules.get("source_titles", []),
    }
