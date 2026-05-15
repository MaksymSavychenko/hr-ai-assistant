from datetime import date
from pathlib import Path
from pprint import pprint
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.annual_leave_service import check_annual_leave_eligibility


def print_result(case_name: str, result: dict):
    print(f"\n{'=' * 88}")
    print(f"TEST CASE: {case_name}")
    print("-" * 88)
    pprint(result)


def main():
    current_year = date.today().year

    # A. Omar asks for 12 annual leave days, has 7 remaining.
    result_a = check_annual_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-05-30",
        requested_days=12,
    )
    print_result("Omar asks for 12 annual leave days", result_a)
    print("Expected: decision_status = NOT_ELIGIBLE")

    # B. Omar asks for 5 annual leave days, has 7 remaining.
    result_b = check_annual_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-05-30",
        requested_days=5,
    )
    print_result("Omar asks for 5 annual leave days", result_b)
    print("Expected: decision_status = ELIGIBLE")

    # C. Omar asks for 8 vacation days in June (Sales June rule + insufficient balance).
    result_c = check_annual_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-06-01",
        requested_days=8,
    )
    print_result("Omar asks for 8 vacation days in June", result_c)
    print(
        "Expected: NOT_ELIGIBLE, explanation includes Sales June HoD approval note, "
        "next_action advises reducing days or changing dates."
    )


if __name__ == "__main__":
    main()
