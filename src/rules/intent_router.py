def _contains_personal_reference(text: str) -> bool:
    personal_markers = [
        "can i",
        "i want",
        "i need",
        "i have",
        "for me",
        "my birthday",
        "my leave",
    ]
    return any(marker in text for marker in personal_markers)


def detect_chat_intent(message: str) -> str:
    """
    Lightweight intent router for Flow 1 vs Flow 2.

    Returns:
    - "policy_qa"
    - "birthday_leave_decision"
    """
    text = str(message or "").strip().lower()
    if not text:
        return "policy_qa"

    birthday_markers = ["birthday leave", "birthday", "born"]
    policy_markers = ["policy", "rule", "rules", "faq", "how does", "what is"]

    has_birthday_signal = any(marker in text for marker in birthday_markers)
    has_policy_signal = any(marker in text for marker in policy_markers)
    has_personal_signal = _contains_personal_reference(text)

    # Personal birthday-leave requests/questions route to experimental Flow 2.
    if has_birthday_signal and has_personal_signal and not has_policy_signal:
        return "birthday_leave_decision"

    # If message asks a personal "Can I..." question and mentions birthday, route to Flow 2.
    if text.startswith("can i") and has_birthday_signal:
        return "birthday_leave_decision"

    return "policy_qa"
