import json
import re
from typing import Any, Dict, List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from src.rag.faiss_store import FaissStoreBuilder


INDEX_DIR = "vector_store/faiss_index"
SUPPORTED_OPERATORS = {
    "equals",
    "is_true",
    "within_days_before_or_after",
    "at_least_working_days_before",
    "once_per_calendar_year",
    "requires_manager_approval",
}

FIELD_ALIASES = {
    "probation_status": "probation_completed",
    "probation": "probation_completed",
    "birthday": "birthday_date",
    "birth_date": "birthday_date",
    "request_submitted": "request_submitted_date",
    "request_submitted_at": "request_submitted_date",
    "request_date": "request_submitted_date",
    "submission_date": "request_submitted_date",
    "request_history_records": "request_history",
    "previous_requests": "request_history",
    "manager_approval_required": "manager_approval",
}


def _format_context(chunks: List[Dict]) -> str:
    blocks = []
    for idx, item in enumerate(chunks, start=1):
        meta = item.get("metadata", {})
        blocks.append(
            "\n".join(
                [
                    f"[S{idx}]",
                    f"title: {meta.get('title', '')}",
                    f"category: {meta.get('category', '')}",
                    f"content_type: {meta.get('content_type', '')}",
                    f"page_id: {meta.get('page_id', '')}",
                    f"attachment_name: {meta.get('attachment_name', '')}",
                    f"content: {item.get('text', '')}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _safe_parse_json(text: str) -> Dict:
    """
    Parse JSON from raw model output.
    Accepts plain JSON or ```json fenced output.
    """
    cleaned = text.strip()

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    return json.loads(cleaned)


def _unique_source_titles(chunks: List[Dict]) -> List[str]:
    titles = []
    seen = set()
    for item in chunks:
        title = item.get("metadata", {}).get("title", "")
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "required"}:
            return True
        if normalized in {"false", "no", "0", "not_required"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _extract_integer(value: Any, fallback: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return fallback


def _normalize_condition(condition: Dict[str, Any]) -> Dict[str, Any]:
    field = str(condition.get("field", "")).strip()
    operator = str(condition.get("operator", "")).strip()
    value = condition.get("value", "")
    description = str(condition.get("description", "")).strip()

    if field in FIELD_ALIASES:
        field = FIELD_ALIASES[field]

    operator_aliases = {
        "within_days": "within_days_before_or_after",
        "within_x_days_before_or_after": "within_days_before_or_after",
        "at_least_days_before": "at_least_working_days_before",
        "at_least_business_days_before": "at_least_working_days_before",
        "once_per_year": "once_per_calendar_year",
        "requires_approval": "requires_manager_approval",
    }
    if operator in operator_aliases:
        operator = operator_aliases[operator]

    if operator == "within_days_before_or_after":
        value = _extract_integer(value, fallback=30)
    elif operator == "at_least_working_days_before":
        value = _extract_integer(value, fallback=3)
    elif operator == "is_true":
        value = _parse_bool(value, default=True)
    elif operator == "requires_manager_approval":
        value = _parse_bool(value, default=True)

    # Many model outputs encode manager approval as is_true.
    # Normalize it to a dedicated operator so evaluator treats it as workflow requirement.
    if field == "manager_approval" and operator == "is_true":
        operator = "requires_manager_approval"
        value = True

    return {
        "field": field,
        "operator": operator,
        "value": value,
        "description": description,
        "effect": "deny_if_not_matched",
    }


def _default_birthday_rules() -> Dict[str, Any]:
    """
    Fallback schema for MVP when model output is not parseable.
    """
    return {
        "leave_type": "Birthday Leave",
        "conditions": [
            {
                "field": "probation_completed",
                "operator": "is_true",
                "value": True,
                "description": "Employee must complete probation before birthday leave is available.",
                "effect": "deny_if_not_matched",
            },
            {
                "field": "birthday_date",
                "operator": "within_days_before_or_after",
                "value": 30,
                "description": "Requested leave date must be within +/-30 calendar days of the birthday date.",
                "effect": "deny_if_not_matched",
            },
            {
                "field": "request_submitted_date",
                "operator": "at_least_working_days_before",
                "value": 3,
                "description": "Birthday leave request must be submitted at least 3 working days in advance.",
                "effect": "deny_if_not_matched",
            },
            {
                "field": "request_history",
                "operator": "once_per_calendar_year",
                "value": "non-rejected birthday leave request must not already exist in the same calendar year",
                "description": "Birthday leave may be used once per calendar year.",
                "effect": "deny_if_not_matched",
            },
            {
                "field": "manager_approval",
                "operator": "requires_manager_approval",
                "value": True,
                "description": "Birthday leave requires manager approval.",
                "effect": "deny_if_not_matched",
            },
        ],
        "confidence": "medium",
        "source_titles": [],
    }


def extract_birthday_leave_rules(model_name: str = "gpt-4o-mini", top_k: int = 8) -> Dict:
    """
    Extract structured Birthday Leave policy rules using retrieved HR context.
    This function does NOT decide eligibility; it only extracts rules.
    """
    retriever = FaissStoreBuilder()
    index, records = retriever.load_index(INDEX_DIR)

    retrieval_query = (
        "Birthday Leave policy rules probation completion 30 days window "
        "3 working days advance manager approval once per calendar year"
    )
    retrieved_chunks = retriever.search(retrieval_query, index, records, top_k=top_k)
    if not retrieved_chunks:
        return {
            "leave_type": "Birthday Leave",
            "conditions": [],
            "source_titles": [],
            "confidence": "low",
        }

    context = _format_context(retrieved_chunks)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are extracting structured policy rules from HR policy context.\n"
                    "Return JSON only. Do not add explanations.\n"
                    "Do not invent rules that are not present in context.\n"
                    "Focus only on Birthday Leave rules.\n"
                    "Use this JSON schema exactly:\n"
                    "{{\n"
                    '  "leave_type": "Birthday Leave",\n'
                    '  "conditions": [\n'
                    "    {{\n"
                    '      "field": "...",\n'
                    '      "operator": "...",\n'
                    '      "value": "...",\n'
                    '      "description": "...",\n'
                    '      "effect": "deny_if_not_matched"\n'
                    "    }}\n"
                    "  ],\n"
                    '  "confidence": "high"\n'
                    "}}\n"
                    "Allowed operators for this extraction:\n"
                    "- equals\n"
                    "- is_true\n"
                    "- within_days_before_or_after\n"
                    "- at_least_working_days_before\n"
                    "- once_per_calendar_year\n"
                    "- requires_manager_approval\n"
                    "Use these field names where applicable:\n"
                    "- probation_completed\n"
                    "- birthday_date\n"
                    "- request_submitted_date\n"
                    "- request_history\n"
                    "- manager_approval\n"
                    "For within_days_before_or_after, set value as number of days.\n"
                    "For at_least_working_days_before, set value as required working days.\n"
                    "For once_per_calendar_year, value should indicate non-rejected duplicate rule.\n"
                ),
            ),
            (
                "human",
                "Extract Birthday Leave rules from this context:\n\n{context}\n",
            ),
        ]
    )

    llm = ChatOpenAI(model=model_name, temperature=0)
    chain = (
        {"context": RunnableLambda(lambda x: x["context"])}
        | prompt
        | llm
        | StrOutputParser()
    )
    raw_output = chain.invoke({"context": context})
    try:
        extracted = _safe_parse_json(raw_output)
    except (json.JSONDecodeError, TypeError):
        fallback = _default_birthday_rules()
        fallback["source_titles"] = _unique_source_titles(retrieved_chunks)
        fallback["confidence"] = "low"
        return fallback

    raw_conditions = extracted.get("conditions", [])
    normalized_conditions = []
    for item in raw_conditions:
        if not isinstance(item, dict):
            continue
        normalized_item = _normalize_condition(item)
        if normalized_item["operator"] in SUPPORTED_OPERATORS:
            normalized_conditions.append(normalized_item)

    if not normalized_conditions:
        fallback = _default_birthday_rules()
        fallback["source_titles"] = _unique_source_titles(retrieved_chunks)
        fallback["confidence"] = "low"
        return fallback

    return {
        "leave_type": "Birthday Leave",
        "conditions": normalized_conditions,
        "confidence": extracted.get("confidence", "medium"),
        "source_titles": _unique_source_titles(retrieved_chunks),
    }
