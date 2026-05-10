from datetime import date
from pathlib import Path

import pandas as pd


REQUESTS_FILE = Path(__file__).resolve().parent.parent / "data" / "hr_requests.csv"

REQUEST_COLUMNS = [
    "request_id",
    "employee_username",
    "employee_name",
    "manager_username",
    "request_type",
    "request_text",
    "leave_date",
    "leave_year",
    "created_date",
    "status",
]


def load_requests():
    """
    Load HR requests from CSV.
    If file doesn't exist, create empty CSV with expected columns.
    """
    if not REQUESTS_FILE.exists():
        pd.DataFrame(columns=REQUEST_COLUMNS).to_csv(REQUESTS_FILE, index=False)
        return pd.DataFrame(columns=REQUEST_COLUMNS)

    df = pd.read_csv(REQUESTS_FILE).fillna("")

    # Keep all expected columns (adds missing columns for compatibility).
    for column in REQUEST_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    return df[REQUEST_COLUMNS]


def save_requests(df):
    """Save full requests DataFrame to CSV."""
    df.to_csv(REQUESTS_FILE, index=False)


def create_request(employee_profile, request_type, request_text, leave_date="", leave_year=""):
    """
    Create request row and persist it.
    New requests always start with Pending HR approval status.
    """
    df = load_requests()

    if df.empty:
        next_request_id = 1
    else:
        request_ids = pd.to_numeric(df["request_id"], errors="coerce").dropna()
        next_request_id = int(request_ids.max()) + 1 if not request_ids.empty else 1

    new_row = {
        "request_id": next_request_id,
        "employee_username": employee_profile["username"],
        "employee_name": employee_profile["name"],
        "manager_username": employee_profile.get("manager_username", ""),
        "request_type": request_type,
        "request_text": request_text,
        "leave_date": leave_date,
        "leave_year": leave_year,
        "created_date": date.today().isoformat(),
        "status": "Pending HR approval",
    }

    updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_requests(updated_df)
    return new_row


def get_employee_requests(username):
    """Return all requests created by one employee."""
    df = load_requests()
    result = df[df["employee_username"] == username].copy()
    return result.sort_values("request_id", ascending=False)


def get_manager_pending_requests(manager_username):
    """Return pending requests for one manager."""
    df = load_requests()
    result = df[
        (df["manager_username"] == manager_username)
        & (df["status"] == "Pending HR approval")
    ].copy()
    return result.sort_values("request_id", ascending=True)


def update_request_status(request_id, new_status):
    """Update request status by request id."""
    df = load_requests()
    df.loc[df["request_id"].astype(str) == str(request_id), "status"] = new_status
    save_requests(df)


def has_active_birthday_request(username, leave_year):
    """
    True when employee already has Birthday Leave request for year
    with status other than Rejected.
    """
    df = load_requests()
    matches = df[
        (df["employee_username"] == username)
        & (df["request_type"] == "Birthday Leave")
        & (df["leave_year"].astype(str) == str(leave_year))
        & (df["status"] != "Rejected")
    ]
    return not matches.empty
