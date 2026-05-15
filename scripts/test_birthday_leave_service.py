from datetime import date
from pathlib import Path
from pprint import pprint
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.birthday_leave_service import check_birthday_leave_eligibility


def print_result(case_name: str, result: dict):
    summarized = dict(result)
    if "retrieved_chunks" in summarized:
        summarized["retrieved_chunks_count"] = len(summarized.get("retrieved_chunks", []))
        summarized.pop("retrieved_chunks", None)

    print(f"\n{'=' * 88}")
    print(f"TEST CASE: {case_name}")
    print("-" * 88)
    pprint(summarized)


def main():
    current_year = date.today().year

    # 1) Omar Khan with 2 requested days on May 17 (outside +/-30 day window for June 25 birthday)
    result_1 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-05-17",
        requested_days=2,
    )
    print_result("Omar Khan request for 2 days on May 17 (outside window)", result_1)
    print(
        "Expected focus: birthday_leave_days_covered = 0, "
        "additional_annual_leave_days_needed = 2, decision_status = NOT_ELIGIBLE."
    )

    # 2) Omar Khan with 2 requested days on birthday date (June 25)
    result_2 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-06-25",
        requested_days=2,
    )
    print_result("Omar Khan request for 2 days on birthday date", result_2)
    print(
        "Expected focus: birthday_leave_days_covered = 1, "
        "additional_annual_leave_days_needed = 1, decision_status = PARTIALLY_ELIGIBLE."
    )

    # 3) Mixed request: 1 birthday day + 7 additional annual leave days (Omar has annual remaining = 7)
    result_3 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-06-20",
        requested_days=8,
        additional_leave_start_date=f"{current_year}-06-21",
    )
    print_result("Omar mixed request: birthday + 7 additional days", result_3)
    print(
        "Expected focus: birthday_leave_days_covered = 1, "
        "additional_annual_leave_days_needed = 7, annual_leave_remaining = 7, "
        "annual_leave_balance_sufficient = True, decision_status = PARTIALLY_ELIGIBLE, "
        "sales_june_restriction_applies = True, head_of_department_approval_required = True."
    )

    # 4) IT employee (non-Sales) in June with 7 additional days: Sales rule must not apply
    result_4 = check_birthday_leave_eligibility(
        employee_username="victor.lee",
        requested_leave_date=f"{current_year}-06-20",
        requested_days=8,
        additional_leave_start_date=f"{current_year}-06-21",
    )
    print_result("IT employee mixed request: Sales June rule should not apply", result_4)
    print(
        "Expected focus: sales_june_restriction_applies = False, "
        "head_of_department_approval_required = False, no Sales June communication in policy_sources."
    )

    # 5) Sales employee in June with 3 additional days: HoD approval not required
    result_5 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-06-20",
        requested_days=4,
        additional_leave_start_date=f"{current_year}-06-21",
    )
    print_result("Sales mixed request: 3 additional days in June", result_5)
    print(
        "Expected focus: sales_june_restriction_applies = True, "
        "head_of_department_approval_required = False."
    )

    # 6) Negative annual balance case: additional annual days exceed remaining balance
    result_6 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-06-20",
        requested_days=10,  # 1 birthday + 9 additional (annual remaining is 7)
        additional_leave_start_date=f"{current_year}-06-21",
    )
    print_result("Omar mixed request: insufficient annual leave balance", result_6)
    print(
        "Expected focus: birthday_leave_days_covered = 1, "
        "additional_annual_leave_days_needed = 9, annual_leave_remaining = 7, "
        "annual_leave_balance_sufficient = False, decision_status = NOT_FULLY_ELIGIBLE."
    )

    # 7) Outside birthday window
    result_7 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-08-20",
        requested_days=1,
    )
    print_result("Outside birthday window", result_7)

    # 8) Probation not completed (Grace Nowak)
    result_8 = check_birthday_leave_eligibility(
        employee_username="grace.nowak",
        requested_leave_date=f"{current_year}-05-25",
        requested_days=1,
    )
    print_result("Probation not completed", result_8)

    # 9) Duplicate birthday leave request (Laura Chen has approved birthday leave in 2026 demo data)
    result_9 = check_birthday_leave_eligibility(
        employee_username="laura.chen",
        requested_leave_date=f"{current_year}-06-18",
        requested_days=1,
    )
    print_result("Duplicate birthday leave request", result_9)


if __name__ == "__main__":
    main()
