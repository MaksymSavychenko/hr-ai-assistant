from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.rag_pipeline import ask_hr_knowledge_base


def print_result(case_name: str, employee_context: dict, result: dict):
    print(f"\n{'=' * 88}")
    print(f"TEST CASE: {case_name}")
    print("-" * 88)
    print("Employee context:")
    print(employee_context)
    print("\nFinal answer:")
    print(result.get("answer", ""))
    print("\nSources:")
    for source in result.get("sources", []):
        print(
            f"- {source.get('title', '-')}"
            f" | category={source.get('category', '-')}"
            f" | type={source.get('content_type', '-')}"
        )


def main():
    question = "Can I take vacation in June?"

    sales_context = {
        "full_name": "Laura Chen",
        "username": "laura.chen",
        "department": "Sales",
        "manager_username": "dmitri.sokolov",
        "probation_completed": True,
        "employment_type": "full-time",
    }
    sales_result = ask_hr_knowledge_base(
        question=question,
        employee_context=sales_context,
        top_k=5,
    )
    print_result("Sales employee asks about June vacation", sales_context, sales_result)
    sales_answer = sales_result.get("answer", "").lower()
    sales_sources = sales_result.get("sources", [])
    sales_source_present = any("sales" in str(source.get("title", "")).lower() for source in sales_sources)
    sales_answer_signal = (
        "head of department" in sales_answer
        or "5 consecutive working days" in sales_answer
        or "vacation planning restrictions" in sales_answer
    )
    if not sales_source_present:
        print("\n[WARNING] Sales sources do not include Sales communication.")
    if not sales_answer_signal and not sales_source_present:
        print("\n[WARNING] Sales answer may be missing Sales-related context.")

    it_context = {
        "full_name": "Victor Lee",
        "username": "victor.lee",
        "department": "IT",
        "manager_username": "serhii.bondar",
        "probation_completed": True,
        "employment_type": "part-time",
    }
    it_result = ask_hr_knowledge_base(
        question=question,
        employee_context=it_context,
        top_k=5,
    )
    print_result("IT employee asks about June vacation", it_context, it_result)
    it_answer = it_result.get("answer", "").lower()
    it_sources = it_result.get("sources", [])
    if "sales team" in it_answer or "sales department" in it_answer or "head of department" in it_answer:
        print("\n[WARNING] IT answer still appears to mention Sales-specific restriction details.")
    else:
        print("\n[OK] IT answer does not include Sales-specific restriction details.")
    if any("sales" in str(source.get("title", "")).lower() for source in it_sources):
        print("\n[WARNING] IT sources still include Sales communication after filtering.")
    else:
        print("[OK] IT sources exclude Sales communication.")


if __name__ == "__main__":
    main()
