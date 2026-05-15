from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.birthday_leave_service import check_birthday_leave_eligibility
from src.rules.intent_router import detect_chat_intent
from src.rules.leave_request_parser import parse_leave_request_message


def print_case(title: str):
    print(f"\n{'=' * 88}")
    print(title)
    print("-" * 88)


def main():
    # A. General policy question
    msg_a = "What is the Birthday Leave policy?"
    route_a = detect_chat_intent(msg_a)
    print_case("CASE A: General policy question")
    print(f"Message: {msg_a}")
    print(f"Detected route: {route_a}")

    # B. Sales employee request in June with 7 additional days
    msg_b = "I want to take birthday vacation on June 20. And 7 days additional starting from June 21."
    route_b = detect_chat_intent(msg_b)
    parsed_b = parse_leave_request_message(msg_b)
    print_case("CASE B: Personal birthday leave request")
    print(f"Message: {msg_b}")
    print(f"Detected route: {route_b}")
    print(f"Parsed request: {parsed_b}")

    if route_b == "birthday_leave_decision" and parsed_b.get("requested_date"):
        result_b = check_birthday_leave_eligibility(
            employee_username="omar.khan",
            requested_leave_date=parsed_b["requested_date"],
            requested_days=parsed_b.get("requested_days") or 1,
            additional_leave_start_date=parsed_b.get("additional_start_date"),
        )
        print("Decision support result:")
        print(f"- flow_used: {result_b.get('flow_used')}")
        print(f"- requested_days: {result_b.get('requested_days')}")
        print(f"- birthday_leave_days_covered: {result_b.get('birthday_leave_days_covered')}")
        print(
            f"- additional_annual_leave_days_needed: {result_b.get('additional_annual_leave_days_needed')}"
        )
        print(f"- annual_leave_remaining: {result_b.get('annual_leave_remaining')}")
        print(f"- annual_leave_balance_sufficient: {result_b.get('annual_leave_balance_sufficient')}")
        print(f"- annual_leave_balance_message: {result_b.get('annual_leave_balance_message')}")
        print(f"- sales_june_restriction_applies: {result_b.get('sales_june_restriction_applies')}")
        print(
            f"- head_of_department_approval_required: "
            f"{result_b.get('head_of_department_approval_required')}"
        )
        print(f"- sales_june_policy_summary: {result_b.get('sales_june_policy_summary')}")
        print(f"- additional_approval_message: {result_b.get('additional_approval_message')}")
        print(
            f"- eligible_for_requested_birthday_leave: "
            f"{result_b.get('eligible_for_requested_birthday_leave')}"
        )
        print(f"- decision_status: {result_b.get('decision_status')}")
        print(f"- decision_title: {result_b.get('decision_title')}")
        print(f"- manager_approval_required: {result_b.get('manager_approval_required')}")
        print(f"- policy_summary: {result_b.get('policy_summary')}")
        print(f"- explanation: {result_b.get('explanation')}")
        if result_b.get("requested_days") == 8:
            print("- expected check: 1 day Birthday Leave + 7 days annual leave.")
            print(
                f"- expected values: covered={result_b.get('birthday_leave_days_covered')}, "
                f"additional={result_b.get('additional_annual_leave_days_needed')}"
            )
            print(
                f"- expected sales rule: applies={result_b.get('sales_june_restriction_applies')}, "
                f"hod={result_b.get('head_of_department_approval_required')}"
            )

    # C. IT employee request in June with 7 additional days (Sales rule must not apply)
    msg_it = "I want to take birthday vacation on June 20. And 7 days additional starting from June 21."
    route_it = detect_chat_intent(msg_it)
    parsed_it = parse_leave_request_message(msg_it)
    print_case("CASE C: IT employee request in June with 7 additional days")
    print(f"Message: {msg_it}")
    print(f"Detected route: {route_it}")
    print(f"Parsed request: {parsed_it}")
    if route_it == "birthday_leave_decision" and parsed_it.get("requested_date"):
        result_it = check_birthday_leave_eligibility(
            employee_username="victor.lee",
            requested_leave_date=parsed_it["requested_date"],
            requested_days=parsed_it.get("requested_days") or 1,
            additional_leave_start_date=parsed_it.get("additional_start_date"),
        )
        print(f"- sales_june_restriction_applies: {result_it.get('sales_june_restriction_applies')}")
        print(
            f"- head_of_department_approval_required: "
            f"{result_it.get('head_of_department_approval_required')}"
        )
        has_sales_source = any(
            "sales" in str(src).lower() and "june" in str(src).lower()
            for src in result_it.get("policy_sources", [])
        )
        print(f"- sales_june_source_present: {has_sales_source}")
        print("- expected: sales_june_restriction_applies=False, sales_june_source_present=False")

    # D. Sales employee in June with 3 additional days (<=5, no HoD approval)
    msg_sales_short = "I want to take birthday vacation on June 20. And 3 days additional starting from June 21."
    route_sales_short = detect_chat_intent(msg_sales_short)
    parsed_sales_short = parse_leave_request_message(msg_sales_short)
    print_case("CASE D: Sales employee request in June with 3 additional days")
    print(f"Message: {msg_sales_short}")
    print(f"Detected route: {route_sales_short}")
    print(f"Parsed request: {parsed_sales_short}")
    if route_sales_short == "birthday_leave_decision" and parsed_sales_short.get("requested_date"):
        result_sales_short = check_birthday_leave_eligibility(
            employee_username="omar.khan",
            requested_leave_date=parsed_sales_short["requested_date"],
            requested_days=parsed_sales_short.get("requested_days") or 1,
            additional_leave_start_date=parsed_sales_short.get("additional_start_date"),
        )
        print(
            f"- sales_june_restriction_applies: {result_sales_short.get('sales_june_restriction_applies')}"
        )
        print(
            f"- head_of_department_approval_required: "
            f"{result_sales_short.get('head_of_department_approval_required')}"
        )
        print("- expected: sales_june_restriction_applies=True, head_of_department_approval_required=False")

    # E. Personal request without enough data
    msg_c = "Can I take birthday leave?"
    route_c = detect_chat_intent(msg_c)
    parsed_c = parse_leave_request_message(msg_c)
    print_case("CASE E: Personal request with missing data")
    print(f"Message: {msg_c}")
    print(f"Detected route: {route_c}")
    print(f"Parsed request: {parsed_c}")
    if "requested_leave_date" in parsed_c.get("missing_fields", []):
        print("Expected behavior: ask employee to provide requested leave date.")


if __name__ == "__main__":
    main()
