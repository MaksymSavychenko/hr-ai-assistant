from datetime import date
from pathlib import Path
from pprint import pprint
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.policy_rule_extractor import extract_birthday_leave_rules
from src.rules.dynamic_evaluator import evaluate_policy_rules


def print_case_result(case_name: str, employee_profile: dict, request_data: dict, result: dict):
    print(f"\n{'=' * 88}")
    print(f"TEST CASE: {case_name}")
    print("-" * 88)
    print("Employee profile:")
    pprint(employee_profile)
    print("\nRequest data:")
    pprint(request_data)
    print("\nEvaluation result:")
    print(f"eligible: {result['eligible']}")
    print(f"requires_manager_approval: {result['requires_manager_approval']}")
    print(f"explanation: {result['explanation']}")
    print("\nPassed conditions:")
    for item in result["passed_conditions"]:
        print(f"- {item['operator']} | {item['field']} | {item['details']}")
    print("\nFailed conditions:")
    for item in result["failed_conditions"]:
        details = item.get("details") or item.get("reason")
        print(f"- {item.get('operator')} | {item.get('field')} | {details}")


def main():
    today = date.today()
    current_year = today.year

    print("Extracting Birthday Leave policy rules from RAG context...")
    rules = extract_birthday_leave_rules()
    print("\nExtracted policy rules:")
    pprint(rules)

    # Base employee for test scenarios (requested in task: Omar Khan, birthday May 13 for eligible case)
    base_employee = {
        "employee_id": "E002",
        "username": "omar.khan",
        "full_name": "Omar Khan",
        "department": "Sales",
        "manager_username": "dmitri.sokolov",
        "probation_completed": True,
        "birthday": f"{current_year - 36}-05-13",
        "probation_end_date": f"{current_year - 1}-11-20",
    }

    # Test Case 1 — Eligible
    request_case_1 = {
        "employee_username": "omar.khan",
        "request_type": "birthday_leave",
        "requested_leave_date": f"{current_year}-05-13",
        "request_submitted_date": f"{current_year}-05-07",  # Thu -> Fri/Mon/Tue = 3 working days.
    }
    history_case_1 = []
    result_1 = evaluate_policy_rules(base_employee, request_case_1, history_case_1, rules)
    print_case_result("Eligible", base_employee, request_case_1, result_1)

    # Test Case 2 — Not eligible: outside birthday window
    request_case_2 = {
        "employee_username": "omar.khan",
        "request_type": "birthday_leave",
        "requested_leave_date": f"{current_year}-08-20",
        "request_submitted_date": f"{current_year}-08-10",
    }
    history_case_2 = []
    result_2 = evaluate_policy_rules(base_employee, request_case_2, history_case_2, rules)
    print_case_result("Not eligible: outside birthday window", base_employee, request_case_2, result_2)

    # Test Case 3 — Not eligible: probation not completed
    employee_case_3 = dict(base_employee)
    employee_case_3["probation_completed"] = False
    employee_case_3["probation_end_date"] = f"{current_year}-12-31"

    request_case_3 = {
        "employee_username": "omar.khan",
        "request_type": "birthday_leave",
        "requested_leave_date": f"{current_year}-05-13",
        "request_submitted_date": f"{current_year}-05-07",
    }
    history_case_3 = []
    result_3 = evaluate_policy_rules(employee_case_3, request_case_3, history_case_3, rules)
    print_case_result("Not eligible: probation not completed", employee_case_3, request_case_3, result_3)

    # Test Case 4 — Not eligible: duplicate Birthday Leave in same year (non-rejected)
    request_case_4 = {
        "employee_username": "omar.khan",
        "request_type": "birthday_leave",
        "requested_leave_date": f"{current_year}-05-13",
        "request_submitted_date": f"{current_year}-05-07",
    }
    history_case_4 = [
        {
            "employee_username": "omar.khan",
            "request_type": "birthday_leave",
            "leave_start_date": f"{current_year}-05-13",
            "status": "Approved",
        }
    ]
    result_4 = evaluate_policy_rules(base_employee, request_case_4, history_case_4, rules)
    print_case_result("Not eligible: duplicate Birthday Leave", base_employee, request_case_4, result_4)

    # Test Case 5 — Not eligible: insufficient advance notice
    request_case_5 = {
        "employee_username": "omar.khan",
        "request_type": "birthday_leave",
        "requested_leave_date": f"{current_year}-05-13",
        # only 1 working day between these dates in most calendar layouts
        "request_submitted_date": f"{current_year}-05-12",
    }
    history_case_5 = []
    result_5 = evaluate_policy_rules(base_employee, request_case_5, history_case_5, rules)
    print_case_result("Not eligible: insufficient advance notice", base_employee, request_case_5, result_5)


if __name__ == "__main__":
    main()
