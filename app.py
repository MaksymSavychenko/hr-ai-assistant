from datetime import date, datetime

import streamlit as st

from src.auth import authenticate_user, get_user_profile
from src.requests import (
    create_request,
    get_employee_requests,
    get_manager_pending_requests,
    has_active_birthday_request,
    update_request_status,
)


st.set_page_config(
    page_title="HR AI Assistant Portal",
    page_icon="🤖",
    layout="wide",
)


# -----------------------------
# SESSION STATE
# -----------------------------

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "birthday_request_draft" not in st.session_state:
    st.session_state.birthday_request_draft = None

if "last_message" not in st.session_state:
    st.session_state.last_message = None


# -----------------------------
# HELPERS
# -----------------------------

def get_birthday_leave_date_this_year(birthday_str):
    """
    Build leave date from birthday month/day plus current year.
    Example: 1991-05-23 -> 2026-05-23
    """
    today = date.today()
    birthday = datetime.strptime(birthday_str, "%Y-%m-%d").date()

    try:
        return date(today.year, birthday.month, birthday.day)
    except ValueError:
        # For Feb 29 birthdays in non-leap years.
        return date(today.year, 2, 28)


def is_birthday_leave_eligible(birthday_str):
    """
    Eligible only when birthday in current year is between:
    today and today + 30 days (inclusive).
    """
    today = date.today()
    leave_date = get_birthday_leave_date_this_year(birthday_str)
    days_until_birthday = (leave_date - today).days
    return 0 <= days_until_birthday <= 30, leave_date


def build_birthday_request_text(user):
    """Generate formal birthday leave request draft."""
    eligible, leave_date = is_birthday_leave_eligible(user["birthday"])
    if not eligible:
        return None, None

    request_text = (
        "Subject: Birthday Leave Request\n\n"
        "Dear HR Team,\n\n"
        f"My name is {user['name']} from the {user['department']} department. "
        f"I kindly request one day of birthday leave on {leave_date.isoformat()}.\n\n"
        f"My manager is {user['manager_username']}.\n\n"
        "Please review and approve this request.\n\n"
        "Best regards,\n"
        f"{user['name']}"
    )
    return request_text, leave_date


def is_birthday_request_prompt(question):
    """Check whether user asks to generate birthday leave request."""
    q = question.lower()
    triggers = [
        "generate birthday leave request",
        "i want birthday leave",
        "create birthday leave application",
        "birthday leave request",
        "birthday leave application",
    ]
    return any(trigger in q for trigger in triggers)


# -----------------------------
# LOGIN PAGE
# -----------------------------

def login_screen():
    st.title("🔐 HR AI Assistant Login")
    st.write("Please log in to access your portal.")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Log in"):
        if authenticate_user(username, password):
            st.session_state.logged_in = True
            st.session_state.current_user = username
            st.rerun()
        else:
            st.error("Invalid username or password.")


# -----------------------------
# EMPLOYEE PORTAL
# -----------------------------

def employee_portal(user):
    st.title("HR AI Assistant Portal")
    st.write(f"Welcome, **{user['name']}**.")

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Vacation Days", str(user["vacation_days"]))
    metric_col2.metric("Department", user["department"])
    metric_col3.metric("Manager", user["manager_username"] or "-")

    st.subheader("Chat with HR Assistant")
    st.markdown("**Example questions**")

    example_col1, example_col2, example_col3 = st.columns(3)
    question = None

    if example_col1.button("Birthday leave policy", use_container_width=True):
        question = "Can I take birthday leave?"
    if example_col2.button("How many vacation days do I have?", use_container_width=True):
        question = "How many vacation days do I have?"
    if example_col3.button("Sick leave process", use_container_width=True):
        question = "What is the sick leave process?"

    if example_col1.button("Remote work policy", use_container_width=True):
        question = "What is the remote work policy?"
    if example_col2.button("Generate birthday leave request", use_container_width=True):
        question = "Generate birthday leave request."
    if example_col3.button("Create birthday leave application", use_container_width=True):
        question = "Create birthday leave application."

    chat_question = st.chat_input("Ask your HR question...")
    if chat_question:
        question = chat_question

    if question:
        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            q = question.lower()

            if is_birthday_request_prompt(question):
                draft_text, leave_date = build_birthday_request_text(user)
                if not draft_text:
                    st.write("Birthday leave can be requested only within 30 days before your birthday.")
                else:
                    st.write("I generated a formal birthday leave request draft for you below.")
                    st.session_state.birthday_request_draft = draft_text

            elif "birthday leave" in q:
                eligible, leave_date = is_birthday_leave_eligible(user["birthday"])
                if eligible:
                    st.write(
                        f"Your birthday leave date for this year is {leave_date.isoformat()}. "
                        "You can generate and submit your request now."
                    )
                else:
                    st.write("Birthday leave can be requested only within 30 days before your birthday.")

            elif "vacation" in q:
                st.write(f"You currently have {user['vacation_days']} vacation days available.")

            elif "sick" in q:
                st.write("Please notify your manager and submit a medical certificate through the HR portal.")

            elif "remote work" in q or "work from home" in q or "remote" in q:
                st.write("Remote work is available based on manager approval and team schedule.")

            else:
                st.write("This request will be processed by the AI assistant in the next version.")

    if st.session_state.birthday_request_draft:
        st.subheader("Birthday Leave Request")
        st.session_state.birthday_request_draft = st.text_area(
            "Request draft",
            value=st.session_state.birthday_request_draft,
            height=220,
        )

        submit_col, clear_col = st.columns(2)

        if submit_col.button("Submit to HR", use_container_width=True):
            eligible, leave_date = is_birthday_leave_eligible(user["birthday"])

            if not eligible:
                st.warning("Birthday leave can be requested only within 30 days before your birthday.")
            elif has_active_birthday_request(user["username"], leave_date.year):
                st.warning("You have already submitted or used birthday leave for this year.")
            else:
                create_request(
                    employee_profile=user,
                    request_type="Birthday Leave",
                    request_text=st.session_state.birthday_request_draft,
                    leave_date=leave_date.isoformat(),
                    leave_year=str(leave_date.year),
                )
                st.session_state.birthday_request_draft = None
                st.session_state.last_message = "Your birthday leave request has been submitted to HR."
                st.rerun()

        if clear_col.button("Clear request", use_container_width=True):
            st.session_state.birthday_request_draft = None
            st.rerun()

    if st.session_state.last_message:
        st.success(st.session_state.last_message)
        st.session_state.last_message = None

    st.subheader("My HR Requests")
    employee_requests = get_employee_requests(user["username"])

    if employee_requests.empty:
        st.info("No HR requests yet.")
    else:
        st.table(
            employee_requests[
                ["request_type", "leave_date", "created_date", "status"]
            ].rename(
                columns={
                    "request_type": "Request Type",
                    "leave_date": "Leave Date",
                    "created_date": "Created Date",
                    "status": "Status",
                }
            )
        )


# -----------------------------
# MANAGER PORTAL
# -----------------------------

def manager_portal(user):
    st.title("Manager Approval Portal")
    st.write(f"Welcome, **{user['name']}**.")

    pending_requests = get_manager_pending_requests(user["username"])
    st.metric("Pending Requests", int(len(pending_requests)))

    if pending_requests.empty:
        st.info("No pending requests.")
        return

    st.subheader("Pending Requests")

    for _, request_row in pending_requests.iterrows():
        request_id = request_row["request_id"]

        with st.container(border=True):
            st.write(f"**Employee:** {request_row['employee_name']}")
            st.write(f"**Request type:** {request_row['request_type']}")
            st.write(f"**Leave date:** {request_row['leave_date'] or '-'}")
            st.write(f"**Created date:** {request_row['created_date']}")
            st.write(f"**Status:** {request_row['status']}")
            st.write("**Request text:**")
            st.write(request_row["request_text"])

            approve_col, reject_col = st.columns(2)

            if approve_col.button("Approve", key=f"approve_{request_id}", use_container_width=True):
                update_request_status(request_id=request_id, new_status="Approved")
                st.rerun()

            if reject_col.button("Reject", key=f"reject_{request_id}", use_container_width=True):
                update_request_status(request_id=request_id, new_status="Rejected")
                st.rerun()


# -----------------------------
# MAIN APP ROUTER
# -----------------------------

def main_app():
    username = st.session_state.current_user
    profile = get_user_profile(username)

    if not profile:
        st.error("User profile not found. Please log in again.")
        st.session_state.logged_in = False
        st.session_state.current_user = None
        st.rerun()

    # Include username in profile for request creation.
    user = {**profile, "username": username}

    st.sidebar.header("Employee Profile")
    st.sidebar.write(f"Name: {user['name']}")
    st.sidebar.write(f"Role: {user['role']}")
    st.sidebar.write(f"Department: {user['department']}")
    st.sidebar.write(f"Hire date: {user['hire_date']}")
    st.sidebar.write(f"Birthday: {user['birthday']}")
    st.sidebar.write(f"Vacation days: {user['vacation_days']}")
    st.sidebar.write(f"Manager username: {user['manager_username'] or '-'}")
    st.sidebar.write(f"Email: {user['email']}")

    if st.sidebar.button("Log out"):
        st.session_state.logged_in = False
        st.session_state.current_user = None
        st.session_state.birthday_request_draft = None
        st.session_state.last_message = None
        st.rerun()

    if user["role"] == "manager":
        manager_portal(user)
    else:
        employee_portal(user)


if st.session_state.logged_in:
    main_app()
else:
    login_screen()
