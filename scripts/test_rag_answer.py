from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.rag_pipeline import ask_hr_knowledge_base


TEST_QUESTIONS = [
    "Can an employee on probation use birthday leave?",
    "What are the Sales department June vacation restrictions?",
    "How many birthday leave days are allowed and what is the request window?",
    "Can I carry over annual leave and when does it expire?",
    "What is the official company gym reimbursement policy?",
]


def main():
    for idx, question in enumerate(TEST_QUESTIONS, start=1):
        print(f"\n================ QUESTION #{idx} ================")
        print(f"Q: {question}\n")

        result = ask_hr_knowledge_base(question)

        print("Final answer:")
        print(result["answer"])
        print()

        print("Sources:")
        if not result["sources"]:
            print(" - none")
        else:
            for source in result["sources"]:
                print(
                    " - "
                    f"title={source.get('title', '')}, "
                    f"category={source.get('category', '')}, "
                    f"content_type={source.get('content_type', '')}, "
                    f"page_id={source.get('page_id', '')}, "
                    f"attachment_name={source.get('attachment_name', '')}"
                )
        print()

        print("Retrieved document titles:")
        if not result["retrieved_chunks"]:
            print(" - none")
        else:
            for chunk in result["retrieved_chunks"]:
                meta = chunk.get("metadata", {})
                print(
                    " - "
                    f"{meta.get('title', '')} "
                    f"(page_id={meta.get('page_id', '')}, "
                    f"attachment_name={meta.get('attachment_name', '')})"
                )


if __name__ == "__main__":
    main()
