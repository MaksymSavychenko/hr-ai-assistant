from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.intent_router import detect_chat_intent, detect_chat_intent_with_meta


def print_case(title: str, message: str):
    result = detect_chat_intent_with_meta(message)
    intent = detect_chat_intent(message)
    print(f"\n{'=' * 88}")
    print(title)
    print("-" * 88)
    print(f"Message: {message}")
    print(f"Intent: {intent}")
    print(f"Meta: {result}")


def main():
    # 1) pure policy question
    print_case(
        "CASE 1: Policy question",
        "What is the Birthday Leave policy?",
    )

    # 2) birthday leave personal request
    print_case(
        "CASE 2: Birthday leave personal request",
        "Can I take birthday leave on June 16?",
    )

    # 3) annual leave personal request
    print_case(
        "CASE 3: Annual leave personal request",
        "Can I take 12 annual leave days on May 30?",
    )

    # 4) declarative planning request
    print_case(
        "CASE 4: Declarative planning request",
        "I am going to take birthday leave on June 16, and additional 10 days from June 17",
    )

    # 5) mixed intent (policy + personal eligibility)
    print_case(
        "CASE 5: Mixed intent birthday question",
        "What is the birthday leave policy? Can I take this leave on June 30?",
    )


if __name__ == "__main__":
    main()
