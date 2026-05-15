import json
import re
from typing import Dict

from openai import OpenAI

from src.config.secrets import get_secret


VALID_INTENTS = {
    "policy_qa",
    "birthday_leave_decision",
    "annual_leave_decision",
    "unknown",
}


def _contains_personal_reference(text: str) -> bool:
    personal_markers = [
        "can i",
        "i want",
        "i need",
        "i have",
        "for me",
        "my birthday",
        "my leave",
        "i am going to",
        "i'm going to",
        "im going to",
        "planning to",
    ]
    return any(marker in text for marker in personal_markers)


def _contains_annual_leave_signal(text: str) -> bool:
    annual_markers = [
        "annual leave",
        "vacation days",
        "leave days",
        "vacation",
        "take",
    ]
    return any(marker in text for marker in annual_markers)


def _contains_day_count_or_date(text: str) -> bool:
    has_day_count = bool(
        re.search(r"\b\d+\s+(?:additional\s+)?(?:(?:annual\s+leave|vacation|leave)\s+)?days?\b", text)
    )
    has_iso_date = bool(re.search(r"\b\d{4}-\d{2}-\d{2}\b", text))
    has_month_day = bool(
        re.search(
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
            r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2}(?:,\s*\d{4})?\b",
            text,
        )
    )
    has_month_only = bool(
        re.search(
            r"\bin\s+(january|february|march|april|may|june|july|august|september|"
            r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
            text,
        )
    )
    return has_day_count or has_iso_date or has_month_day or has_month_only


def _contains_policy_question_signal(text: str) -> bool:
    patterns = [
        "what is the policy",
        "what is",
        "how does",
        "how do",
        "faq",
        "rules",
        "rule",
        "policy",
        "work",
    ]
    return any(pattern in text for pattern in patterns)


def _rule_based_intent_with_confidence(message: str) -> Dict:
    """
    Rule-first classifier with explicit confidence.
    Returns dict: {"intent", "confidence", "reason", "source"}.
    """
    text = str(message or "").strip().lower()
    if not text:
        return {
            "intent": "policy_qa",
            "confidence": 0.95,
            "reason": "Empty message defaults to policy Q&A.",
            "router_used": "rule_based",
        }

    birthday_markers = ["birthday leave", "birthday", "born"]
    policy_markers = ["policy", "rule", "rules", "faq", "how does", "what is"]

    has_birthday_signal = any(marker in text for marker in birthday_markers)
    has_policy_signal = any(marker in text for marker in policy_markers)
    has_policy_question_signal = _contains_policy_question_signal(text)
    has_personal_signal = _contains_personal_reference(text)
    has_annual_signal = _contains_annual_leave_signal(text)
    has_date_or_days = _contains_day_count_or_date(text)
    has_personal_eligibility_signal = (
        has_personal_signal
        or text.startswith("can i")
        or "can i take" in text
        or "can i use" in text
        or "am i eligible" in text
        or "should i" in text
        or has_date_or_days
    )
    mixed_intent_detected = bool(has_policy_question_signal and has_personal_eligibility_signal)

    # Mixed intent: FAQ + personal request/eligibility.
    # Prefer Flow 2 so policy explanation and personal deterministic evaluation can be shown together.
    if mixed_intent_detected:
        if has_birthday_signal:
            return {
                "intent": "birthday_leave_decision",
                "confidence": 0.94,
                "reason": "Mixed intent detected: policy explanation + personal leave eligibility request.",
                "router_used": "rule_based",
                "mixed_intent_detected": True,
            }
        if has_annual_signal:
            return {
                "intent": "annual_leave_decision",
                "confidence": 0.92,
                "reason": "Mixed intent detected: policy explanation + personal leave eligibility request.",
                "router_used": "rule_based",
                "mixed_intent_detected": True,
            }

    # Birthday intent, including declarative planning statements.
    if has_birthday_signal and has_date_or_days and not has_policy_signal:
        confidence = 0.95 if has_personal_signal else 0.88
        return {
            "intent": "birthday_leave_decision",
            "confidence": confidence,
            "reason": "Birthday leave signal with request details (days/date).",
            "router_used": "rule_based",
            "mixed_intent_detected": False,
        }
    if has_birthday_signal and has_personal_signal and not has_policy_signal:
        return {
            "intent": "birthday_leave_decision",
            "confidence": 0.90,
            "reason": "Personal birthday leave intent without explicit planning details.",
            "router_used": "rule_based",
            "mixed_intent_detected": False,
        }
    if text.startswith("can i") and has_birthday_signal:
        return {
            "intent": "birthday_leave_decision",
            "confidence": 0.92,
            "reason": "Direct personal eligibility question mentioning birthday.",
            "router_used": "rule_based",
            "mixed_intent_detected": False,
        }

    # Annual leave intent.
    if not has_birthday_signal and has_annual_signal and has_date_or_days:
        confidence = 0.92 if has_personal_signal or text.startswith("can i") else 0.82
        return {
            "intent": "annual_leave_decision",
            "confidence": confidence,
            "reason": "Annual/vacation signal with date/day planning details.",
            "router_used": "rule_based",
            "mixed_intent_detected": False,
        }

    # General policy Q&A.
    if has_policy_signal and not has_date_or_days:
        return {
            "intent": "policy_qa",
            "confidence": 0.93,
            "reason": "Policy/rules question without personal planning details.",
            "router_used": "rule_based",
            "mixed_intent_detected": False,
        }

    # Uncertain case -> request LLM fallback.
    return {
        "intent": "unknown",
        "confidence": 0.45,
        "reason": "Rule-based classifier is uncertain for this phrasing.",
        "router_used": "rule_based",
        "mixed_intent_detected": mixed_intent_detected,
    }


def _llm_intent_classification(message: str, mixed_intent_detected: bool = False) -> Dict:
    """
    LLM fallback classifier for uncertain cases.
    Returns only supported intents and safe confidence.
    """
    api_key = get_secret("OPENAI_API_KEY")
    if not api_key:
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reason": "OPENAI_API_KEY is missing for LLM fallback.",
            "router_used": "llm_fallback",
            "mixed_intent_detected": mixed_intent_detected,
        }

    client = OpenAI(api_key=api_key)
    prompt = (
        "You are classifying an HR assistant message into exactly one intent.\n\n"
        "Allowed intents:\n"
        "- policy_qa\n"
        "- birthday_leave_decision\n"
        "- annual_leave_decision\n"
        "- unknown\n\n"
        "Intent definitions:\n"
        "1) policy_qa\n"
        "General HR policy, FAQ, or employee-group questions.\n"
        "Examples:\n"
        "- What is the Birthday Leave policy?\n"
        "- Can employees on probation use Birthday Leave?\n"
        "- Are employees eligible for Birthday Leave during probation?\n"
        "- What are the vacation rules?\n"
        "- Can Sales employees take vacation in June?\n\n"
        "2) birthday_leave_decision\n"
        "Personal employee Birthday Leave eligibility or planning requests.\n"
        "Examples:\n"
        "- Can I take Birthday Leave on June 20?\n"
        "- Am I eligible for Birthday Leave on June 30?\n"
        "- I want Birthday Leave next week.\n"
        "- I want to take Birthday Leave and 7 additional vacation days.\n\n"
        "3) annual_leave_decision\n"
        "Personal annual leave balance or vacation planning requests.\n"
        "Examples:\n"
        "- Can I take 10 vacation days?\n"
        "- I want 8 vacation days in June.\n"
        "- Do I have enough annual leave balance?\n"
        "- Can I take 12 annual leave days on May 30?\n\n"
        "4) unknown\n"
        "Unclear or unsupported request.\n\n"
        "Important classification rule:\n"
        "- Generic employee-group questions (for employees in general) must be policy_qa.\n"
        "- Personal requests about the logged-in user (for example 'Can I...', 'I want...') should be DSS decision intents.\n\n"
        "Return JSON only with keys: intent, confidence, reason.\n"
        "confidence must be a float between 0 and 1.\n"
        "reason must be short.\n\n"
        f"Message: {message}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an intent classifier. Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        parsed = json.loads(content)
    except Exception as exc:
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "reason": f"LLM fallback failed: {exc}",
            "router_used": "llm_fallback",
            "mixed_intent_detected": mixed_intent_detected,
        }

    intent = str(parsed.get("intent", "unknown")).strip()
    if intent not in VALID_INTENTS:
        intent = "unknown"

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reason = str(parsed.get("reason", "")).strip() or "LLM fallback classification."
    return {
        "intent": intent,
        "confidence": confidence,
        "reason": reason,
        "router_used": "llm_fallback",
        "mixed_intent_detected": mixed_intent_detected,
    }


def detect_chat_intent_with_meta(message: str) -> Dict:
    """
    Hybrid intent routing:
    1) Rule-based result with confidence
    2) LLM fallback only when confidence is low
    """
    rule_result = _rule_based_intent_with_confidence(message)
    if rule_result["confidence"] >= 0.80 and rule_result["intent"] != "unknown":
        return rule_result

    llm_result = _llm_intent_classification(
        message,
        mixed_intent_detected=bool(rule_result.get("mixed_intent_detected", False)),
    )
    if llm_result["intent"] != "unknown" and llm_result["confidence"] >= 0.55:
        return llm_result

    # Safe fallback if LLM is unavailable or still uncertain.
    if rule_result["intent"] == "unknown":
        return {
            "intent": "policy_qa",
            "confidence": 0.40,
            "reason": "Fallback to policy_qa because both rule and LLM were uncertain.",
            "router_used": "llm_fallback",
            "mixed_intent_detected": bool(rule_result.get("mixed_intent_detected", False)),
        }
    return rule_result


def detect_chat_intent(message: str) -> str:
    """
    Backward-compatible intent helper used by app routing.
    """
    return detect_chat_intent_with_meta(message).get("intent", "policy_qa")
