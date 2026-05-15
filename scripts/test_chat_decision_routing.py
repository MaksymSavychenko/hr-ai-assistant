from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.birthday_leave_service import check_birthday_leave_eligibility
from src.rules.annual_leave_service import check_annual_leave_eligibility
from src.rules.intent_router import detect_chat_intent, detect_chat_intent_with_meta
from src.rules.leave_request_parser import parse_leave_request_message


def print_case(title: str):
    print(f"\n{'=' * 88}")
    print(title)
    print("-" * 88)


def main():
    # A. General policy question
    msg_a = "What is the Birthday Leave policy?"
    route_a = detect_chat_intent(msg_a)
    route_a_meta = detect_chat_intent_with_meta(msg_a)
    print_case("CASE A: General policy question")
    print(f"Message: {msg_a}")
    print(f"Detected route: {route_a}")
    print(f"Route meta: {route_a_meta}")

    # A1. Generic employee-group question should be policy_qa
    msg_a1 = "Can employees on probation use birthday leave?"
    route_a1 = detect_chat_intent(msg_a1)
    route_a1_meta = detect_chat_intent_with_meta(msg_a1)
    print_case("CASE A1: Generic employee-group policy question")
    print(f"Message: {msg_a1}")
    print(f"Detected route: {route_a1}")
    print(f"Route meta: {route_a1_meta}")
    print("- expected route: policy_qa")

    # A1b. Generic employee-group eligibility wording should be policy_qa
    msg_a1b = "Are employees eligible for Birthday Leave during probation?"
    route_a1b = detect_chat_intent(msg_a1b)
    route_a1b_meta = detect_chat_intent_with_meta(msg_a1b)
    print_case("CASE A1b: Generic employee-group eligibility wording")
    print(f"Message: {msg_a1b}")
    print(f"Detected route: {route_a1b}")
    print(f"Route meta: {route_a1b_meta}")
    print("- expected route: policy_qa")

    # A1c. Personal birthday leave request should be birthday_leave_decision
    msg_a1c = "Can I take Birthday Leave on June 30?"
    route_a1c = detect_chat_intent(msg_a1c)
    route_a1c_meta = detect_chat_intent_with_meta(msg_a1c)
    print_case("CASE A1c: Personal birthday leave request")
    print(f"Message: {msg_a1c}")
    print(f"Detected route: {route_a1c}")
    print(f"Route meta: {route_a1c_meta}")
    print("- expected route: birthday_leave_decision")

    # A2. Mixed intent question should prefer DSS
    msg_a2 = "What is the birthday leave policy? Can I take this leave on June 30?"
    route_a2 = detect_chat_intent(msg_a2)
    route_a2_meta = detect_chat_intent_with_meta(msg_a2)
    parsed_a2 = parse_leave_request_message(msg_a2)
    print_case("CASE A2: Mixed intent question (policy + personal eligibility)")
    print(f"Message: {msg_a2}")
    print(f"Detected route: {route_a2}")
    print(f"Route meta: {route_a2_meta}")
    print(f"Parsed request: {parsed_a2}")
    print("- expected route: birthday_leave_decision")
    print("- expected mixed_intent_detected: True")
    if route_a2 == "birthday_leave_decision" and parsed_a2.get("requested_date"):
        result_a2 = check_birthday_leave_eligibility(
            employee_username="omar.khan",
            requested_leave_date=parsed_a2["requested_date"],
            requested_days=parsed_a2.get("requested_days") or 1,
            additional_leave_start_date=parsed_a2.get("additional_start_date"),
        )
        print(f"- policy_summary: {result_a2.get('policy_summary')}")
        print(f"- decision_title: {result_a2.get('decision_title')}")
        print(f"- explanation: {result_a2.get('explanation')}")

    # B. Sales employee request in June with 7 additional days
    msg_b = "I want to take birthday vacation on June 20. And 7 days additional starting from June 21."
    route_b = detect_chat_intent(msg_b)
    route_b_meta = detect_chat_intent_with_meta(msg_b)
    parsed_b = parse_leave_request_message(msg_b)
    print_case("CASE B: Personal birthday leave request")
    print(f"Message: {msg_b}")
    print(f"Detected route: {route_b}")
    print(f"Route meta: {route_b_meta}")
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
    route_it_meta = detect_chat_intent_with_meta(msg_it)
    parsed_it = parse_leave_request_message(msg_it)
    print_case("CASE C: IT employee request in June with 7 additional days")
    print(f"Message: {msg_it}")
    print(f"Detected route: {route_it}")
    print(f"Route meta: {route_it_meta}")
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
    route_sales_short_meta = detect_chat_intent_with_meta(msg_sales_short)
    parsed_sales_short = parse_leave_request_message(msg_sales_short)
    print_case("CASE D: Sales employee request in June with 3 additional days")
    print(f"Message: {msg_sales_short}")
    print(f"Detected route: {route_sales_short}")
    print(f"Route meta: {route_sales_short_meta}")
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
    route_c_meta = detect_chat_intent_with_meta(msg_c)
    parsed_c = parse_leave_request_message(msg_c)
    print_case("CASE E: Personal request with missing data")
    print(f"Message: {msg_c}")
    print(f"Detected route: {route_c}")
    print(f"Route meta: {route_c_meta}")
    print(f"Parsed request: {parsed_c}")
    if "requested_leave_date" in parsed_c.get("missing_fields", []):
        print("Expected behavior: ask employee to provide requested leave date.")

    # F. Annual leave personal decision route
    msg_annual = "Can I take 12 annual leave days on May 30?"
    route_annual = detect_chat_intent(msg_annual)
    route_annual_meta = detect_chat_intent_with_meta(msg_annual)
    parsed_annual = parse_leave_request_message(msg_annual)
    print_case("CASE F: Annual leave decision route")
    print(f"Message: {msg_annual}")
    print(f"Detected route: {route_annual}")
    print(f"Route meta: {route_annual_meta}")
    print(f"Parsed request: {parsed_annual}")
    if route_annual == "annual_leave_decision":
        annual_result = check_annual_leave_eligibility(
            employee_username="omar.khan",
            requested_leave_date=parsed_annual.get("requested_start_date"),
            requested_days=parsed_annual.get("requested_days") or 1,
        )
        print(f"- decision_status: {annual_result.get('decision_status')}")
        print(f"- annual_leave_remaining: {annual_result.get('annual_leave_remaining')}")
        print(f"- annual_leave_balance_sufficient: {annual_result.get('annual_leave_balance_sufficient')}")
        print("- expected route: annual_leave_decision")

    # G. Annual leave message with month-only date.
    msg_annual_june = "I want 8 vacation days in June"
    route_annual_june = detect_chat_intent(msg_annual_june)
    route_annual_june_meta = detect_chat_intent_with_meta(msg_annual_june)
    parsed_annual_june = parse_leave_request_message(msg_annual_june)
    print_case("CASE G: Annual leave decision with month-only date")
    print(f"Message: {msg_annual_june}")
    print(f"Detected route: {route_annual_june}")
    print(f"Route meta: {route_annual_june_meta}")
    print(f"Parsed request: {parsed_annual_june}")
    if route_annual_june == "annual_leave_decision":
        annual_result_june = check_annual_leave_eligibility(
            employee_username="omar.khan",
            requested_leave_date=parsed_annual_june.get("requested_start_date"),
            requested_days=parsed_annual_june.get("requested_days") or 1,
        )
        print(f"- decision_status: {annual_result_june.get('decision_status')}")
        print(f"- decision_title: {annual_result_june.get('decision_title')}")
        print(f"- explanation: {annual_result_june.get('explanation')}")
        print(f"- next_action: {annual_result_june.get('next_action')}")
        print(f"- policy_sources: {annual_result_june.get('policy_sources')}")
        print("- expected route: annual_leave_decision")

    # H. Declarative planning statement for birthday leave
    msg_decl = "I am going to take birthday leave on June 16, and additional 10 days from June 17"
    route_decl = detect_chat_intent(msg_decl)
    route_decl_meta = detect_chat_intent_with_meta(msg_decl)
    parsed_decl = parse_leave_request_message(msg_decl)
    print_case("CASE H: Declarative planning birthday request")
    print(f"Message: {msg_decl}")
    print(f"Detected route: {route_decl}")
    print(f"Route meta: {route_decl_meta}")
    print(f"Parsed request: {parsed_decl}")
    print("- expected route: birthday_leave_decision")


if __name__ == "__main__":
    main()
