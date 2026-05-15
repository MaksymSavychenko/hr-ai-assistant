from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.auth import get_user_profile
from src.rag.faiss_store import FaissStoreBuilder
from src.rag.policy_rule_extractor import extract_birthday_leave_rules
from src.rag.rag_pipeline import ensure_faiss_index_ready
from src.requests import get_employee_requests
from src.rules.dynamic_evaluator import evaluate_policy_rules


LEAVE_BALANCES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "leave_balances.csv"
INDEX_DIR = "vector_store/faiss_index"
BIRTHDAY_POLICY_RETRIEVAL_QUERY = (
    "Birthday Leave policy paid day per calendar year probation period "
    "30 calendar days before or after birthday 3 working days advance manager approval"
)


def _load_employee_profile(employee_username: str) -> Dict:
    profile = get_user_profile(employee_username)
    if not profile:
        raise ValueError(f"Employee profile not found for username: {employee_username}")
    return {**profile, "username": employee_username}


def _load_employee_request_history(employee_profile: Dict) -> List[Dict]:
    employee_id = employee_profile.get("employee_id", "")
    requests_df = get_employee_requests(employee_id)
    if requests_df.empty:
        return []

    history = requests_df.to_dict("records")
    for item in history:
        item["employee_username"] = employee_profile.get("username", "")
    return history


def _load_birthday_leave_balance(employee_id: str, year: int) -> Dict:
    if not LEAVE_BALANCES_FILE.exists():
        return {"entitlement_days": 0, "used_days": 0, "remaining_days": 0}

    df = pd.read_csv(LEAVE_BALANCES_FILE).fillna("")
    rows = df[
        (df["employee_id"].astype(str) == str(employee_id))
        & (df["calendar_year"].astype(str) == str(year))
        & (df["leave_type"].astype(str).str.lower() == "birthday_leave")
    ]
    if rows.empty:
        return {"entitlement_days": 0, "used_days": 0, "remaining_days": 0}

    row = rows.iloc[0]
    return {
        "entitlement_days": int(float(row.get("entitlement_days", 0) or 0)),
        "used_days": int(float(row.get("used_days", 0) or 0)),
        "remaining_days": int(float(row.get("remaining_days", 0) or 0)),
    }


def _load_annual_leave_remaining(employee_profile: Dict, year: int) -> int:
    """
    Get annual leave remaining value.
    Priority:
    1) employee_profile['annual_leave_remaining'] when provided
    2) leave_balances.csv annual_leave row for current employee and year
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


def _retrieve_birthday_policy_chunks(top_k: int = 5) -> List[Dict]:
    ensure_faiss_index_ready(INDEX_DIR)
    retriever = FaissStoreBuilder()
    index, records = retriever.load_index(INDEX_DIR)
    return retriever.search(BIRTHDAY_POLICY_RETRIEVAL_QUERY, index, records, top_k=top_k)


def _retrieve_sales_june_policy_chunks(top_k: int = 5) -> List[Dict]:
    """
    Retrieve chunks for temporary Sales June vacation restriction communication.
    """
    query = (
        "Sales department June vacation restriction "
        "more than 5 consecutive working days Head of Department approval"
    )
    ensure_faiss_index_ready(INDEX_DIR)
    retriever = FaissStoreBuilder()
    index, records = retriever.load_index(INDEX_DIR)
    return retriever.search(query, index, records, top_k=top_k)


def _extract_max_birthday_days_from_chunks(chunks: List[Dict], default_days: int = 1) -> int:
    """
    Derive max Birthday Leave paid days per year from retrieved policy text.
    Conservative strategy: if multiple numbers appear, use the minimum.
    """
    import re

    values = []
    pattern = re.compile(r"eligible\s+for\s+(\d+)\s+paid\s+birthday\s+leave\s+day", re.IGNORECASE)

    for chunk in chunks:
        text = str(chunk.get("text", "") or "")
        for match in pattern.finditer(text):
            try:
                values.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue

    if not values:
        return default_days
    return max(1, min(values))


def _build_policy_summary(max_days_per_year: int) -> str:
    return (
        f"Birthday Leave policy summary: employees are eligible for up to {max_days_per_year} "
        f"paid Birthday Leave day(s) per calendar year, available after probation completion, "
        f"within +/-30 calendar days from birthday, with request submitted at least 3 working "
        f"days in advance, and manager approval required."
    )


def _build_policy_sources(chunks: List[Dict]) -> List[str]:
    sources = []
    seen = set()
    for item in chunks:
        title = item.get("metadata", {}).get("title", "")
        if title and title not in seen:
            seen.add(title)
            sources.append(title)
    return sources


def _looks_like_sales_june_source(source_title: str) -> bool:
    lower = str(source_title or "").lower()
    return "sales" in lower and "june" in lower


def _has_passed_condition(result_items: List[Dict], operator: str) -> bool:
    return any(str(item.get("operator", "")) == operator for item in result_items)


def _format_human_date(date_obj: date) -> str:
    return date_obj.strftime("%B %d, %Y")


def _build_birthday_window_dates(employee_birthday: str, requested_leave_date: str) -> Dict:
    """
    Build birthday date for requested leave year and allowed +/- 30 day window.
    """
    requested_date_obj = date.fromisoformat(requested_leave_date)
    birthday_obj = datetime.strptime(employee_birthday, "%Y-%m-%d").date()

    try:
        birthday_in_requested_year = date(
            requested_date_obj.year,
            birthday_obj.month,
            birthday_obj.day,
        )
    except ValueError:
        # Handle Feb 29 in non-leap year.
        birthday_in_requested_year = date(requested_date_obj.year, 2, 28)

    window_start = birthday_in_requested_year - timedelta(days=30)
    window_end = birthday_in_requested_year + timedelta(days=30)

    return {
        "requested_date": requested_date_obj,
        "birthday_date_for_evaluation": birthday_in_requested_year,
        "window_start": window_start,
        "window_end": window_end,
    }


def _to_user_condition_label(item: Dict, is_failed: bool = False) -> str:
    """
    Convert technical deterministic check to short user-facing line.
    """
    operator = str(item.get("operator", ""))
    if operator == "is_true":
        return "Probation period not completed" if is_failed else "Probation period completed"
    if operator == "within_days_before_or_after":
        return (
            "Requested date is outside the allowed Birthday Leave window"
            if is_failed
            else "Requested date is within the allowed Birthday Leave window"
        )
    if operator == "at_least_working_days_before":
        return (
            "Request was not submitted at least 3 working days in advance"
            if is_failed
            else "Request submitted at least 3 working days in advance"
        )
    if operator == "once_per_calendar_year":
        return (
            "Birthday Leave already submitted or used in this calendar year"
            if is_failed
            else "No previous active Birthday Leave request in this calendar year"
        )
    if operator == "requires_manager_approval":
        return "Manager approval is required and must be obtained separately"
    if operator == "max_birthday_days_per_year":
        return (
            "Requested days exceed the maximum Birthday Leave allowance"
            if is_failed
            else "Requested days are within the maximum Birthday Leave allowance"
        )
    if operator == "within_remaining_birthday_balance":
        return (
            "Requested days exceed remaining Birthday Leave balance"
            if is_failed
            else "Requested days are within remaining Birthday Leave balance"
        )
    if operator == "annual_leave_balance_for_additional_days":
        return (
            "Annual leave balance is insufficient for additional requested days"
            if is_failed
            else "Annual leave balance is sufficient for additional requested days"
        )
    if operator == "requires_head_of_department_approval":
        return "Additional Head of Department approval is required under Sales June restriction"
    if operator == "sales_june_standard_manager_approval":
        return "Sales June restriction checked; standard manager approval applies"
    return str(item.get("description", "") or item.get("details", "") or "Policy condition check")


def check_birthday_leave_eligibility(
    employee_username: str,
    requested_leave_date: str,
    requested_days: int = 1,
    additional_leave_start_date: str | None = None,
) -> Dict:
    """
    Flow 2 hybrid service:
    1) Retrieve Birthday Leave policy context chunks
    2) Extract/derive structured rules
    3) Evaluate deterministically against employee + history
    """
    employee_profile = _load_employee_profile(employee_username)
    request_history = _load_employee_request_history(employee_profile)
    retrieved_chunks = _retrieve_birthday_policy_chunks(top_k=5)
    rules = extract_birthday_leave_rules()

    requested_days = int(requested_days) if requested_days else 1
    if requested_days < 1:
        requested_days = 1

    request_data = {
        "employee_username": employee_username,
        "request_type": "birthday_leave",
        "requested_leave_date": requested_leave_date,
        "requested_days": requested_days,
        "request_submitted_date": date.today().isoformat(),
    }

    evaluation = evaluate_policy_rules(
        employee_profile=employee_profile,
        request_data=request_data,
        request_history=request_history,
        rules=rules,
    )
    window_dates = _build_birthday_window_dates(employee_profile.get("birthday", ""), requested_leave_date)

    target_year = date.fromisoformat(requested_leave_date).year
    balance = _load_birthday_leave_balance(employee_profile.get("employee_id", ""), target_year)
    annual_leave_remaining = _load_annual_leave_remaining(employee_profile, target_year)
    employee_profile["annual_leave_remaining"] = annual_leave_remaining

    # Use policy-derived max (from retrieved policy chunks) for DSS calculation.
    policy_max_days_per_year = _extract_max_birthday_days_from_chunks(retrieved_chunks, default_days=1)
    remaining_days = int(balance.get("remaining_days", 0))

    passed_conditions_detailed = list(evaluation.get("passed_conditions", []))
    failed_conditions_detailed = list(evaluation.get("failed_conditions", []))

    # Deterministic checks we care about for coverage decision.
    window_passed = _has_passed_condition(passed_conditions_detailed, "within_days_before_or_after")
    probation_passed = _has_passed_condition(passed_conditions_detailed, "is_true")
    duplicate_passed = _has_passed_condition(passed_conditions_detailed, "once_per_calendar_year")

    # Add explicit day-limit checks.
    if requested_days <= policy_max_days_per_year:
        passed_conditions_detailed.append(
            {
                "field": "requested_days",
                "operator": "max_birthday_days_per_year",
                "value": policy_max_days_per_year,
                "description": "Requested days are within Birthday Leave yearly policy limit.",
                "details": f"Requested {requested_days} day(s), policy max is {policy_max_days_per_year}.",
            }
        )
    else:
        failed_conditions_detailed.append(
            {
                "field": "requested_days",
                "operator": "max_birthday_days_per_year",
                "value": policy_max_days_per_year,
                "description": "Requested days exceed Birthday Leave yearly policy limit.",
                "details": f"Requested {requested_days} day(s), policy max is {policy_max_days_per_year}.",
            }
        )

    if requested_days <= remaining_days:
        passed_conditions_detailed.append(
            {
                "field": "remaining_days",
                "operator": "within_remaining_birthday_balance",
                "value": remaining_days,
                "description": "Requested days are within remaining Birthday Leave balance.",
                "details": f"Requested {requested_days} day(s), remaining balance is {remaining_days}.",
            }
        )
    else:
        failed_conditions_detailed.append(
            {
                "field": "remaining_days",
                "operator": "within_remaining_birthday_balance",
                "value": remaining_days,
                "description": "Requested days exceed remaining Birthday Leave balance.",
                "details": f"Requested {requested_days} day(s), remaining balance is {remaining_days}.",
            }
        )

    # Coverage decision:
    # Birthday leave coverage is allowed only when deterministic core checks pass,
    # including strict +/- 30 day window around birthday in requested leave year.
    can_cover_with_birthday_leave = (
        probation_passed and window_passed and duplicate_passed and remaining_days > 0
    )
    if can_cover_with_birthday_leave:
        birthday_leave_days_covered = min(requested_days, policy_max_days_per_year, remaining_days)
    else:
        birthday_leave_days_covered = 0

    additional_annual_leave_days_needed = max(0, requested_days - birthday_leave_days_covered)
    annual_leave_balance_sufficient = additional_annual_leave_days_needed <= annual_leave_remaining

    # Sales June restriction check (multi-policy stacking).
    department = str(employee_profile.get("department", "")).strip().lower()
    is_sales_employee = department == "sales"

    additional_start_date_obj = None
    if additional_leave_start_date:
        try:
            additional_start_date_obj = date.fromisoformat(additional_leave_start_date)
        except ValueError:
            additional_start_date_obj = None
    if additional_start_date_obj is None and additional_annual_leave_days_needed > 0:
        additional_start_date_obj = date.fromisoformat(requested_leave_date) + timedelta(days=1)

    additional_end_date_obj = None
    if additional_start_date_obj is not None and additional_annual_leave_days_needed > 0:
        additional_end_date_obj = additional_start_date_obj + timedelta(days=additional_annual_leave_days_needed - 1)

    overlaps_june = False
    if additional_start_date_obj is not None and additional_end_date_obj is not None:
        june_start = date(additional_start_date_obj.year, 6, 1)
        june_end = date(additional_start_date_obj.year, 6, 30)
        overlaps_june = not (additional_end_date_obj < june_start or additional_start_date_obj > june_end)

    sales_june_restriction_applies = (
        is_sales_employee and additional_annual_leave_days_needed > 0 and overlaps_june
    )
    head_of_department_approval_required = (
        sales_june_restriction_applies and additional_annual_leave_days_needed > 5
    )

    sales_policy_chunks = []
    sales_june_policy_summary = ""
    additional_approval_message = ""

    if sales_june_restriction_applies:
        sales_policy_chunks = _retrieve_sales_june_policy_chunks(top_k=5)
        sales_june_policy_summary = (
            "Temporary Sales June vacation restriction: requests in June for more than 5 "
            "consecutive annual leave days require additional Head of Department approval."
        )
        if head_of_department_approval_required:
            additional_approval_message = (
                "Because you are in Sales and your additional annual leave request is in June "
                "for more than 5 consecutive working days, additional Head of Department approval "
                "is required under the temporary Sales June vacation restriction."
            )
        else:
            additional_approval_message = (
                "Because you are in Sales and your additional annual leave request is in June for "
                "5 or fewer consecutive working days, standard manager approval applies."
            )

    if additional_annual_leave_days_needed == 0:
        annual_leave_balance_message = "No additional annual leave days are required."
    elif annual_leave_balance_sufficient:
        annual_leave_balance_message = (
            "You have enough annual leave balance for the additional days, "
            "subject to manager approval."
        )
    else:
        annual_leave_balance_message = (
            "You do not have enough annual leave balance for the additional days."
        )

    if additional_annual_leave_days_needed > 0:
        if annual_leave_balance_sufficient:
            passed_conditions_detailed.append(
                {
                    "field": "annual_leave_remaining",
                    "operator": "annual_leave_balance_for_additional_days",
                    "value": annual_leave_remaining,
                    "description": "Annual leave balance is sufficient for additional requested days.",
                    "details": (
                        f"Additional annual leave needed: {additional_annual_leave_days_needed}, "
                        f"annual leave remaining: {annual_leave_remaining}."
                    ),
                }
            )
        else:
            failed_conditions_detailed.append(
                {
                    "field": "annual_leave_remaining",
                    "operator": "annual_leave_balance_for_additional_days",
                    "value": annual_leave_remaining,
                    "description": "Annual leave balance is insufficient for additional requested days.",
                    "details": (
                        f"Additional annual leave needed: {additional_annual_leave_days_needed}, "
                        f"annual leave remaining: {annual_leave_remaining}."
                    ),
                }
            )

    if sales_june_restriction_applies:
        if head_of_department_approval_required:
            passed_conditions_detailed.append(
                {
                    "field": "sales_june_restriction",
                    "operator": "requires_head_of_department_approval",
                    "value": True,
                    "description": "Sales June restriction applies; Head of Department approval is required.",
                    "details": additional_approval_message,
                }
            )
        else:
            passed_conditions_detailed.append(
                {
                    "field": "sales_june_restriction",
                    "operator": "sales_june_standard_manager_approval",
                    "value": False,
                    "description": "Sales June restriction checked; standard manager approval applies.",
                    "details": additional_approval_message,
                }
            )

    if birthday_leave_days_covered == requested_days and requested_days > 0:
        decision_status = "ELIGIBLE"
        decision_title = "✅ Eligible for Birthday Leave"
    elif birthday_leave_days_covered > 0:
        if annual_leave_balance_sufficient:
            decision_status = "PARTIALLY_ELIGIBLE"
            decision_title = "🟨 Partially eligible"
        else:
            decision_status = "NOT_FULLY_ELIGIBLE"
            decision_title = "⚠️ Not fully eligible"
    else:
        decision_status = "NOT_ELIGIBLE"
        decision_title = "❌ Not eligible for Birthday Leave"
    eligible_for_requested_birthday_leave = decision_status == "ELIGIBLE"

    # Ensure explicit window-failure signal is present in failed conditions.
    if not window_passed:
        required_message = "Requested date is outside the allowed Birthday Leave window."
        contains_required_message = any(
            required_message in str(item.get("details", "")) or required_message in str(item.get("description", ""))
            for item in failed_conditions_detailed
        )
        if not contains_required_message:
            failed_conditions_detailed.append(
                {
                    "field": "birthday_date",
                    "operator": "within_days_before_or_after",
                    "value": 30,
                    "description": required_message,
                    "details": required_message,
                }
            )

    requested_human = _format_human_date(window_dates["requested_date"])
    birthday_human = _format_human_date(window_dates["birthday_date_for_evaluation"])
    window_start_human = _format_human_date(window_dates["window_start"])
    window_end_human = _format_human_date(window_dates["window_end"])

    if decision_status == "NOT_ELIGIBLE" and not window_passed:
        explanation = (
            f"Your requested leave date, {requested_human}, is outside the allowed Birthday Leave window. "
            f"Based on your birthday on {birthday_human}, Birthday Leave may be used from "
            f"{window_start_human} to {window_end_human}. "
            "These days may be requested as standard annual leave, subject to available balance and manager approval."
        )
    elif decision_status == "NOT_ELIGIBLE":
        explanation = (
            "Birthday Leave cannot cover the requested days under current policy conditions. "
            "These days may be requested as standard annual leave, subject to available balance and manager approval."
        )
    elif decision_status == "PARTIALLY_ELIGIBLE":
        explanation = (
            f"{birthday_leave_days_covered} day(s) can be covered by Birthday Leave. "
            f"The remaining {additional_annual_leave_days_needed} day(s) should be requested as standard annual leave, "
            f"subject to available balance and manager approval. {annual_leave_balance_message}"
        )
    elif decision_status == "NOT_FULLY_ELIGIBLE":
        explanation = (
            f"{birthday_leave_days_covered} day(s) can be covered by Birthday Leave, "
            f"but the remaining {additional_annual_leave_days_needed} day(s) cannot be fully covered as standard annual leave. "
            f"{annual_leave_balance_message}"
        )
    else:
        explanation = (
            "Your requested days can be covered by Birthday Leave under current policy conditions. "
            "Manager approval is still required."
        )

    if additional_approval_message:
        explanation = f"{explanation} {additional_approval_message}"

    passed_conditions = []
    for item in passed_conditions_detailed:
        label = _to_user_condition_label(item, is_failed=False)
        if label and label not in passed_conditions:
            passed_conditions.append(label)

    failed_conditions = []
    for item in failed_conditions_detailed:
        label = _to_user_condition_label(item, is_failed=True)
        if label and label not in failed_conditions:
            failed_conditions.append(label)

    if not window_passed:
        required_failed_label = "Requested date is outside the allowed Birthday Leave window"
        if required_failed_label not in failed_conditions:
            failed_conditions.append(required_failed_label)

    if requested_days > policy_max_days_per_year:
        required_failed_label = "Requested days exceed the maximum Birthday Leave allowance"
        if required_failed_label not in failed_conditions:
            failed_conditions.append(required_failed_label)

    if decision_status == "NOT_ELIGIBLE" and birthday_leave_days_covered == 0:
        required_failed_label = "No requested days can be covered by Birthday Leave"
        if required_failed_label not in failed_conditions:
            failed_conditions.append(required_failed_label)
    if additional_annual_leave_days_needed > 0 and not annual_leave_balance_sufficient:
        required_failed_label = "Annual leave balance is insufficient for additional requested days"
        if required_failed_label not in failed_conditions:
            failed_conditions.append(required_failed_label)

    deterministic_checks = {
        "passed_conditions": passed_conditions_detailed,
        "failed_conditions": failed_conditions_detailed,
    }
    combined_retrieved_chunks = list(retrieved_chunks)
    if sales_june_restriction_applies:
        combined_retrieved_chunks.extend(sales_policy_chunks)

    policy_sources = _build_policy_sources(retrieved_chunks) or rules.get("source_titles", [])
    if not sales_june_restriction_applies:
        policy_sources = [src for src in policy_sources if not _looks_like_sales_june_source(src)]
    if sales_june_restriction_applies:
        for src in _build_policy_sources(sales_policy_chunks):
            if src not in policy_sources:
                policy_sources.append(src)

    return {
        "flow_used": "Decision Support (Deterministic + RAG)",
        "policy_summary": _build_policy_summary(policy_max_days_per_year),
        "employee_username": employee_username,
        "requested_days": requested_days,
        "requested_leave_date": requested_leave_date,
        "birthday_leave_days_covered": birthday_leave_days_covered,
        "additional_annual_leave_days_needed": additional_annual_leave_days_needed,
        "annual_leave_remaining": annual_leave_remaining,
        "annual_leave_balance_sufficient": annual_leave_balance_sufficient,
        "annual_leave_balance_message": annual_leave_balance_message,
        "sales_june_restriction_applies": sales_june_restriction_applies,
        "head_of_department_approval_required": head_of_department_approval_required,
        "sales_june_policy_summary": sales_june_policy_summary,
        "additional_approval_message": additional_approval_message,
        "additional_leave_start_date": additional_start_date_obj.isoformat() if additional_start_date_obj else "",
        "additional_leave_end_date": additional_end_date_obj.isoformat() if additional_end_date_obj else "",
        "eligible_for_requested_birthday_leave": eligible_for_requested_birthday_leave,
        "decision_status": decision_status,
        "decision_title": decision_title,
        "user_friendly_status": decision_title,
        "manager_approval_required": evaluation.get("requires_manager_approval", False),
        "passed_conditions": passed_conditions,
        "failed_conditions": failed_conditions,
        "explanation": explanation,
        "birthday_date_for_evaluation": window_dates["birthday_date_for_evaluation"].isoformat(),
        "allowed_window_start": window_dates["window_start"].isoformat(),
        "allowed_window_end": window_dates["window_end"].isoformat(),
        "deterministic_checks": deterministic_checks,
        "policy_sources": policy_sources,
        "retrieved_chunks": combined_retrieved_chunks,
    }
