from datetime import date
from pathlib import Path
from pprint import pprint
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.birthday_leave_service import check_birthday_leave_eligibility


def print_result(case_name: str, result: dict):
    print(f"\n{'=' * 88}")
    print(f"TEST CASE: {case_name}")
    print("-" * 88)
    pprint(result)


def main():
    current_year = date.today().year

    # 1) Omar Khan with birthday leave on May 13 (requested case from task)
    result_1 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-05-13",
    )
    print_result("Omar Khan request on May 13", result_1)

    # 2) Outside birthday window
    result_2 = check_birthday_leave_eligibility(
        employee_username="omar.khan",
        requested_leave_date=f"{current_year}-08-20",
    )
    print_result("Outside birthday window", result_2)

    # 3) Probation not completed (Grace Nowak)
    result_3 = check_birthday_leave_eligibility(
        employee_username="grace.nowak",
        requested_leave_date=f"{current_year}-05-25",
    )
    print_result("Probation not completed", result_3)

    # 4) Duplicate birthday leave request (Laura Chen has approved birthday leave in 2026 demo data)
    result_4 = check_birthday_leave_eligibility(
        employee_username="laura.chen",
        requested_leave_date=f"{current_year}-06-18",
    )
    print_result("Duplicate birthday leave request", result_4)


if __name__ == "__main__":
    main()
