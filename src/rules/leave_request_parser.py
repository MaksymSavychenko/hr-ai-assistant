import re
from datetime import date, datetime


MONTH_PATTERN = (
    r"(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
)


def _parse_requested_days(text: str):
    # Examples:
    # - "2 additional vacation days"
    # - "2 leave days"
    # - "1 day"
    match = re.search(
        r"\b(\d+)\s+(?:additional\s+)?(?:vacation\s+|leave\s+)?days?\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    return None


def _parse_additional_days(text: str):
    """
    Parse additional-day phrasing, for example:
    - "7 additional days"
    - "7 days additional"
    """
    patterns = [
        r"\b(\d+)\s+additional\s+(?:vacation\s+|leave\s+)?days?\b",
        r"\b(\d+)\s+(?:vacation\s+|leave\s+)?days?\s+additional\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _parse_requested_date(text: str, default_year: int | None = None):
    if default_year is None:
        default_year = date.today().year

    # ISO date: YYYY-MM-DD
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_match:
        return iso_match.group(1)

    # Month name + day (+ optional year), e.g. "May 17" or "May 17, 2026"
    month_day_match = re.search(
        rf"\b{MONTH_PATTERN}\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?\b",
        text,
        flags=re.IGNORECASE,
    )
    if month_day_match:
        month_text = month_day_match.group(1)
        day_text = month_day_match.group(2)
        year_text = month_day_match.group(3)
        year_value = int(year_text) if year_text else int(default_year)

        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                parsed = datetime.strptime(f"{month_text} {day_text} {year_value}", fmt).date()
                return parsed.isoformat()
            except ValueError:
                continue

    return None


def _parse_date_mentions(text: str, default_year: int | None = None):
    """
    Return all date mentions in message in left-to-right order as ISO dates.
    """
    if default_year is None:
        default_year = date.today().year

    mentions = []

    for match in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        mentions.append((match.start(), match.group(1)))

    for match in re.finditer(
        rf"\b{MONTH_PATTERN}\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?\b",
        text,
        flags=re.IGNORECASE,
    ):
        month_text = match.group(1)
        day_text = match.group(2)
        year_text = match.group(3)
        year_value = int(year_text) if year_text else int(default_year)

        parsed_iso = None
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                parsed_iso = datetime.strptime(f"{month_text} {day_text} {year_value}", fmt).date().isoformat()
                break
            except ValueError:
                continue

        if parsed_iso:
            mentions.append((match.start(), parsed_iso))

    mentions.sort(key=lambda item: item[0])
    return [item[1] for item in mentions]


def _parse_additional_start_date(text: str, date_mentions: list[str]):
    """
    Parse explicit additional leave start date.
    Priority:
    1) second date mention in message
    2) date after phrase "starting from"
    """
    if len(date_mentions) >= 2:
        return date_mentions[1]

    marker = re.search(r"starting\s+from\s+(.+)$", text, flags=re.IGNORECASE)
    if marker:
        tail = marker.group(1).strip()
        return _parse_requested_date(tail)
    return None


def parse_leave_request_message(message: str) -> dict:
    """
    Rule-based parser for conversational leave request text (MVP).
    """
    text = str(message or "").strip()
    lowered = text.lower()

    birthday_mentioned = "birthday" in lowered
    leave_type_candidate = "Birthday Leave" if birthday_mentioned else "Unknown"

    requested_days = _parse_requested_days(text)
    additional_days = _parse_additional_days(text)

    # For birthday-style mixed requests:
    # base Birthday Leave = 1 day, plus parsed additional days if present.
    if birthday_mentioned and additional_days is not None:
        requested_days = 1 + int(additional_days)
    elif requested_days is None and birthday_mentioned:
        requested_days = 1

    date_mentions = _parse_date_mentions(text)
    requested_date = date_mentions[0] if date_mentions else _parse_requested_date(text)
    additional_start_date = _parse_additional_start_date(text, date_mentions)

    missing_fields = []
    if birthday_mentioned and not requested_date:
        missing_fields.append("requested_leave_date")

    return {
        "requested_date": requested_date,
        "additional_start_date": additional_start_date,
        "requested_days": requested_days,
        "additional_days": additional_days,
        "leave_type_candidate": leave_type_candidate,
        "birthday_mentioned": birthday_mentioned,
        "missing_fields": missing_fields,
    }
