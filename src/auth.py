from pathlib import Path

import pandas as pd


EMPLOYEES_FILE = Path(__file__).resolve().parent.parent / "data" / "employees.csv"


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


def authenticate_user(username, password):
    """Check username/password from CSV users."""
    users = load_users()
    return username in users and str(users[username].get("password", "")) == str(password)


def get_user_profile(username):
    """Return one user profile by username."""
    users = load_users()
    return users.get(username)
