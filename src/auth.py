from pathlib import Path

import pandas as pd


EMPLOYEES_FILE = Path(__file__).resolve().parent.parent / "data" / "employees.csv"
USER_ACCOUNTS_FILE = Path(__file__).resolve().parent.parent / "data" / "user_accounts.csv"


def load_users():
    """
    Load users from CSV and return a dict keyed by username.
    This is the data-access layer (easy to replace later with SQL).
    """
    df = pd.read_csv(EMPLOYEES_FILE).fillna("")
    users = {}

    for _, row in df.iterrows():
        profile = row.to_dict()
        username = profile.pop("username")
        users[username] = profile

    return users


def load_user_accounts():
    """
    Load authentication accounts from CSV and return a dict keyed by username.
    This table is a temporary MVP replacement for a real auth service.
    """
    df = pd.read_csv(USER_ACCOUNTS_FILE).fillna("")
    accounts = {}

    for _, row in df.iterrows():
        account = row.to_dict()
        username = account["username"]
        accounts[username] = account

    return accounts


def authenticate_user(username, password):
    """
    Check username/password in user_accounts.csv.
    Only accounts with account_status == active can log in.
    """
    accounts = load_user_accounts()
    if username not in accounts:
        return False

    account = accounts[username]
    is_password_valid = str(account.get("password", "")) == str(password)
    is_active = str(account.get("account_status", "")).lower() == "active"
    return is_password_valid and is_active


def get_user_profile(username):
    """Return one user profile by username."""
    users = load_users()
    return users.get(username)
