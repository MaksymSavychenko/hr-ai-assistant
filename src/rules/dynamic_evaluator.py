from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


SUPPORTED_OPERATORS = {
    "equals",
    "is_true",
    "within_days_before_or_after",
    "at_least_working_days_before",
    "once_per_calendar_year",
    "requires_manager_approval",
}


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    if isinstance(value, str):
        text = value.strip()
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                continue
    return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized in {"true", "yes", "1", "required", "active"}
    return False


def _normalize_leave_type(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _working_days_between(submitted_date: date, requested_date: date) -> int:
    """
    Count working days strictly between submitted_date and requested_date.
    Example:
    - submitted Monday, requested Friday -> Tue/Wed/Thu = 3
    """
    if requested_date <= submitted_date:
        return 0

    count = 0
    cursor = submitted_date + timedelta(days=1)
    while cursor < requested_date:
        if cursor.weekday() < 5:
            count += 1
        cursor += timedelta(days=1)
    return count


def _resolve_field_value(employee_profile: Dict, request_data: Dict, field_name: str) -> Any:
    if field_name in request_data:
        return request_data.get(field_name)
    if field_name in employee_profile:
        return employee_profile.get(field_name)

    if field_name == "probation_completed":
        explicit = employee_profile.get("probation_completed")
        if explicit is not None:
            return _to_bool(explicit)
        probation_end = _parse_date(employee_profile.get("probation_end_date"))
        requested_leave = _parse_date(request_data.get("requested_leave_date"))
        if probation_end and requested_leave:
            return requested_leave >= probation_end
        return None

    if field_name == "birthday_date":
        return employee_profile.get("birthday")

    if field_name == "request_submitted_date":
        return request_data.get("request_submitted_date")

    if field_name == "requested_leave_date":
        return request_data.get("requested_leave_date")

    return None


def _evaluate_within_days_before_or_after(employee_profile: Dict, request_data: Dict, max_days: int) -> Tuple[bool, str]:
    birthday_raw = employee_profile.get("birthday")
    requested_raw = request_data.get("requested_leave_date")

    birthday = _parse_date(birthday_raw)
    requested_leave = _parse_date(requested_raw)
    if not birthday or not requested_leave:
        return False, "Missing or invalid birthday/requested_leave_date."

    birthday_in_request_year = date(requested_leave.year, birthday.month, birthday.day)
    days_diff = abs((requested_leave - birthday_in_request_year).days)
    if days_diff <= int(max_days):
        return True, f"Requested date is within +/-{max_days} days of birthday ({days_diff} day difference)."
    return False, f"Requested date is outside +/-{max_days} days of birthday ({days_diff} day difference)."


def _evaluate_at_least_working_days_before(request_data: Dict, required_days: int) -> Tuple[bool, str]:
    submitted = _parse_date(request_data.get("request_submitted_date"))
    requested_leave = _parse_date(request_data.get("requested_leave_date"))
    if not submitted or not requested_leave:
        return False, "Missing or invalid request_submitted_date/requested_leave_date."

    working_days_gap = _working_days_between(submitted, requested_leave)
    if working_days_gap >= int(required_days):
        return True, f"Request submitted {working_days_gap} working days in advance (required: {required_days})."
    return False, f"Request submitted only {working_days_gap} working days in advance (required: {required_days})."


def _evaluate_once_per_calendar_year(request_data: Dict, request_history: List[Dict]) -> Tuple[bool, str]:
    requested_leave = _parse_date(request_data.get("requested_leave_date"))
    employee_username = request_data.get("employee_username") or request_data.get("username")
    if not requested_leave:
        return False, "Missing or invalid requested_leave_date."

    target_year = requested_leave.year
    normalized_target_type = _normalize_leave_type(request_data.get("request_type", "birthday_leave"))

    for item in request_history:
        history_type = _normalize_leave_type(item.get("request_type", ""))
        history_status = str(item.get("status", "")).strip().lower()
        history_date = _parse_date(item.get("leave_start_date")) or _parse_date(item.get("requested_leave_date"))
        history_user = item.get("employee_username") or item.get("username")

        # If username is provided in request_data, compare user scope.
        if employee_username and history_user and employee_username != history_user:
            continue
        if history_type != normalized_target_type:
            continue
        if not history_date or history_date.year != target_year:
            continue
        if history_status != "rejected":
            return False, "A non-rejected Birthday Leave request already exists for this calendar year."

    return True, "No non-rejected Birthday Leave request found in this calendar year."


def evaluate_policy_rules(
    employee_profile: Dict,
    request_data: Dict,
    request_history: List[Dict],
    rules: Dict,
) -> Dict:
    """
    Deterministic policy evaluation in Python.
    LLM-extracted rules are inputs; final eligibility is decided here.
    """
    conditions = rules.get("conditions", [])

    passed_conditions: List[Dict] = []
    failed_conditions: List[Dict] = []
    requires_manager_approval = False
    manual_review_required = False

    for condition in conditions:
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")
        description = condition.get("description", "")

        if operator not in SUPPORTED_OPERATORS:
            failed_conditions.append(
                {
                    "condition": condition,
                    "reason": f"Unsupported operator: {operator}",
                    "manual_review": True,
                }
            )
            manual_review_required = True
            continue

        if operator == "equals":
            actual_value = _resolve_field_value(employee_profile, request_data, str(field))
            matched = str(actual_value) == str(value)
            details = f"Expected '{value}', got '{actual_value}'."

        elif operator == "is_true":
            actual_value = _resolve_field_value(employee_profile, request_data, str(field))
            if actual_value is None:
                matched = False
                details = f"Field '{field}' is missing."
            else:
                matched = _to_bool(actual_value) is True
                details = f"Field '{field}' evaluates to {matched}."

        elif operator == "within_days_before_or_after":
            matched, details = _evaluate_within_days_before_or_after(employee_profile, request_data, int(value))

        elif operator == "at_least_working_days_before":
            matched, details = _evaluate_at_least_working_days_before(request_data, int(value))

        elif operator == "once_per_calendar_year":
            matched, details = _evaluate_once_per_calendar_year(request_data, request_history)

        elif operator == "requires_manager_approval":
            requires_manager_approval = _to_bool(value) if value is not None else True
            matched = True
            details = "Manager approval is required for this request."

        else:
            # Defensive fallback; should not happen due SUPPORTED_OPERATORS check.
            matched = False
            details = f"Operator not implemented: {operator}"
            manual_review_required = True

        result_item = {
            "field": field,
            "operator": operator,
            "value": value,
            "description": description,
            "details": details,
        }

        if matched:
            passed_conditions.append(result_item)
        else:
            failed_conditions.append(result_item)

    eligible = len(failed_conditions) == 0 and not manual_review_required

    if manual_review_required:
        explanation = "Manual review required: one or more rule conditions are unsupported."
    elif eligible:
        explanation = "All Birthday Leave policy conditions are satisfied."
    else:
        explanation = "One or more Birthday Leave policy conditions failed."

    return {
        "eligible": eligible,
        "passed_conditions": passed_conditions,
        "failed_conditions": failed_conditions,
        "requires_manager_approval": requires_manager_approval,
        "explanation": explanation,
    }
