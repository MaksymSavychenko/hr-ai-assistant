from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.auth import authenticate_user, get_user_profile, load_users
from src.rag.rag_pipeline import ask_hr_knowledge_base, is_faiss_index_ready
from src.requests import (
    get_employee_requests,
    get_manager_pending_requests,
    update_request_status,
)
from src.rules.birthday_leave_service import check_birthday_leave_eligibility
from src.rules.intent_router import detect_chat_intent
from src.rules.leave_request_parser import parse_leave_request_message


LEAVE_BALANCES_FILE = Path(__file__).resolve().parent / "data" / "leave_balances.csv"


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

if "policy_qa_result" not in st.session_state:
    st.session_state.policy_qa_result = None

if "policy_qa_question" not in st.session_state:
    st.session_state.policy_qa_question = ""


# -----------------------------
# HELPERS
# -----------------------------

def load_leave_balances():
    """Load leave balances snapshot from CSV."""
    if not LEAVE_BALANCES_FILE.exists():
        return pd.DataFrame()
    return pd.read_csv(LEAVE_BALANCES_FILE).fillna("")


def get_leave_balance_value(employee_id, leave_type, field_name, default_value=0):
    """
    Return one leave balance value for the current year and employee.
    Example fields: entitlement_days, used_days, remaining_days.
    """
    balances = load_leave_balances()
    if balances.empty:
        return default_value

    current_year = date.today().year
    row = balances[
        (balances["employee_id"].astype(str) == str(employee_id))
        & (balances["calendar_year"].astype(str) == str(current_year))
        & (balances["leave_type"].astype(str) == str(leave_type))
    ]

    if row.empty:
        return default_value

    return row.iloc[0].get(field_name, default_value)


def get_birthday_leave_date_this_year(birthday_str):
    """
    Build leave date from birthday month/day plus current year.
    Example: 1991-05-23 -> 2026-05-23
    """
    # MVP deterministic business logic.
    # In Flow 2, these hardcoded policy parameters will be replaced
    # by policy-driven rules extracted from the RAG knowledge base.
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
        f"My name is {user['full_name']} from the {user['department']} department. "
        f"I kindly request one day of birthday leave on {leave_date.isoformat()}.\n\n"
        f"My manager is {user['manager_username']}.\n\n"
        "Please review and approve this request.\n\n"
        "Best regards,\n"
        f"{user['full_name']}"
    )
    return request_text, leave_date


def _build_flow1_employee_context(user: dict) -> dict:
    """Build context payload used by Flow 1 retrieval filtering."""
    probation_completed = None
    probation_end = str(user.get("probation_end_date", "")).strip()
    if probation_end:
        try:
            probation_completed = date.today() >= datetime.strptime(probation_end, "%Y-%m-%d").date()
        except ValueError:
            probation_completed = None

    return {
        "full_name": user.get("full_name", ""),
        "username": user.get("username", ""),
        "department": user.get("department", ""),
        "manager_username": user.get("manager_username", ""),
        "probation_completed": probation_completed,
        "employment_type": user.get("employment_type", ""),
    }


def _format_flow2_chat_answer(parsed_request: dict, decision_result: dict) -> str:
    """
    Build natural language assistant response for experimental Flow 2 decision support.
    """
    requested_days = int(decision_result.get("requested_days", parsed_request.get("requested_days") or 1))
    birthday_covered_days = int(decision_result.get("birthday_leave_days_covered", 0))
    annual_days_needed = int(decision_result.get("additional_annual_leave_days_needed", 0))
    annual_leave_remaining = int(decision_result.get("annual_leave_remaining", 0))
    annual_balance_sufficient = bool(decision_result.get("annual_leave_balance_sufficient", False))
    sales_june_applies = bool(decision_result.get("sales_june_restriction_applies", False))
    hod_approval_required = bool(decision_result.get("head_of_department_approval_required", False))
    manager_required = bool(decision_result.get("manager_approval_required", False))
    decision_title = decision_result.get("decision_title", "Decision support result")
    manager_line = "Manager approval is required." if manager_required else "Manager approval is not required."

    lines = [
        decision_title,
        decision_result.get("policy_summary", ""),
        decision_result.get("explanation", ""),
        "",
        f"Requested days: {requested_days}",
        f"Birthday Leave days covered: {birthday_covered_days}",
    ]

    if annual_days_needed > 0:
        lines.append(
            f"Additional days that may need standard annual leave: {annual_days_needed}"
        )
        lines.append(
            f"Annual leave remaining: {annual_leave_remaining} "
            f"({'sufficient' if annual_balance_sufficient else 'insufficient'} for additional days)"
        )
    else:
        lines.append("No additional annual leave days are needed for this request.")

    lines.extend(
        [
            manager_line,
        ]
    )
    if sales_june_applies:
        lines.append(
            f"Head of Department approval required: {'Yes' if hod_approval_required else 'No'}"
        )
        if decision_result.get("sales_june_policy_summary"):
            lines.append(decision_result.get("sales_june_policy_summary", ""))
        if decision_result.get("additional_approval_message"):
            lines.append(decision_result.get("additional_approval_message", ""))
    return "\n".join(lines).strip()


def run_policy_qa_query(question: str, user: dict):
    """
    Route user message:
    - policy_qa -> Flow 1 RAG
    - birthday_leave_decision -> Flow 2 experimental deterministic decision support
    """
    if not question.strip():
        st.warning("Please enter a policy question.")
        return

    try:
        intent = detect_chat_intent(question)
        if intent == "policy_qa":
            employee_context = _build_flow1_employee_context(user)
            if not is_faiss_index_ready():
                st.info("Building HR knowledge base index. This may take a moment.")
                with st.spinner("Building HR knowledge base index. This may take a moment."):
                    st.session_state.policy_qa_result = ask_hr_knowledge_base(
                        question.strip(),
                        employee_context=employee_context,
                        top_k=5,
                    )
            else:
                st.session_state.policy_qa_result = ask_hr_knowledge_base(
                    question.strip(),
                    employee_context=employee_context,
                    top_k=5,
                )
        else:
            # Flow 2 (experimental): conversational decision support for birthday leave.
            parsed_request = parse_leave_request_message(question)
            employee_profile_used = _build_flow1_employee_context(user)
            if not parsed_request.get("requested_date"):
                st.session_state.policy_qa_result = {
                    "flow_mode": "birthday_leave_decision",
                    "answer": (
                        "To check birthday leave eligibility, please provide the requested leave date "
                        "(for example: 2026-05-17 or May 17)."
                    ),
                    "sources": [],
                    "retrieved_chunks": [],
                    "detected_intent": intent,
                    "parsed_request_data": parsed_request,
                    "employee_profile_used": employee_profile_used,
                    "policy_summary": "Birthday Leave evaluation requires a requested leave date.",
                    "policy_sources": [],
                    "passed_conditions": [],
                    "failed_conditions": [],
                }
                return

            requested_days = parsed_request.get("requested_days") or 1
            decision_result = check_birthday_leave_eligibility(
                employee_username=user.get("username", ""),
                requested_leave_date=parsed_request["requested_date"],
                requested_days=int(requested_days),
                additional_leave_start_date=parsed_request.get("additional_start_date"),
            )

            flow2_answer = _format_flow2_chat_answer(parsed_request, decision_result)
            flow2_sources = [
                {
                    "title": title,
                    "category": "Policy Source",
                    "content_type": "RAG Rule Extraction",
                    "page_id": "",
                    "attachment_name": "",
                }
                for title in decision_result.get("policy_sources", [])
            ]

            st.session_state.policy_qa_result = {
                "flow_mode": "birthday_leave_decision",
                "answer": flow2_answer,
                "sources": flow2_sources,
                "retrieved_chunks": decision_result.get("retrieved_chunks", []),
                "detected_intent": intent,
                "parsed_request_data": parsed_request,
                "employee_profile_used": employee_profile_used,
                **decision_result,
            }
    except FileNotFoundError:
        st.session_state.policy_qa_result = None
        st.warning(
            "Knowledge base index is not built yet. Please run scripts/build_faiss_index.py."
        )
    except Exception as exc:
        st.session_state.policy_qa_result = None
        st.error(
            "Could not query the knowledge base right now. "
            "Please check API settings and try again."
        )
        st.caption(f"Error: {exc}")


def deduplicate_sources(sources):
    """Deduplicate source list for UI display at document/page level."""
    unique_sources = []
    seen = set()

    for source in sources:
        page_id = (source.get("page_id", "") or "").strip()
        title = (source.get("title", "") or "").strip()

        # Primary dedup key: page_id.
        # Fallback key: title + page_id shape requested for UI dedup.
        key = page_id if page_id else (title, page_id)

        if key in seen:
            continue
        seen.add(key)
        unique_sources.append(source)

    return unique_sources


def render_policy_qa_section(user: dict):
    """
    Flow 1: Pure RAG policy Q&A.
    This section answers policy questions from KB documents only.
    It does not create requests or make personal eligibility decisions.
    """
    st.subheader("Policy Q&A mode")
    st.caption(
        "This assistant answers questions based on HR knowledge base documents. "
        "It does not make personal eligibility decisions."
    )

    st.markdown("**Example questions**")
    example_col1, example_col2, example_col3 = st.columns(3)
    selected_example_question = None

    if example_col1.button("Birthday leave policy", use_container_width=True):
        selected_example_question = "What is the birthday leave policy?"
    if example_col2.button("Probation and birthday leave", use_container_width=True):
        selected_example_question = "Can employees on probation use birthday leave?"
    if example_col3.button("Advance request timing", use_container_width=True):
        selected_example_question = "How many days in advance should birthday leave be requested?"

    if example_col1.button("Annual leave approval timing", use_container_width=True):
        selected_example_question = "How many days in advance is annual leave request required?"
    if example_col2.button("Carry-over expiry", use_container_width=True):
        selected_example_question = "When do carry-over leave days expire?"
    if example_col3.button("Sales June rule", use_container_width=True):
        selected_example_question = "What is the Sales department June vacation restriction?"

    if selected_example_question:
        # Set value before input widget is instantiated in this run.
        st.session_state.policy_qa_question = selected_example_question
        run_policy_qa_query(selected_example_question, user)

    policy_question = st.text_input(
        "Ask HR Knowledge Base",
        key="policy_qa_question",
        placeholder="Example: What are birthday leave rules during probation?",
    )

    if st.button("Ask Knowledge Base", use_container_width=True):
        run_policy_qa_query(policy_question, user)

    result = st.session_state.policy_qa_result
    if not result:
        return

    sources = deduplicate_sources(result.get("sources", []))

    if result.get("flow_mode") == "birthday_leave_decision":
        with st.container(border=True):
            st.markdown(f"### {result.get('decision_title', 'Decision support result')}")
            st.write(result.get("explanation", "No explanation available."))

        st.markdown("### Policy summary")
        st.write(result.get("policy_summary", "No policy summary available."))

        st.markdown("### Personal evaluation result")
        st.write(f"Requested days: {result.get('requested_days', '-')}")
        st.write(f"Birthday Leave days covered: {result.get('birthday_leave_days_covered', '-')}")
        st.write(
            f"Additional annual leave days needed: {result.get('additional_annual_leave_days_needed', '-')}"
        )
        st.write(f"Annual Leave Remaining: {result.get('annual_leave_remaining', '-')}")
        st.write(
            "Balance sufficient: "
            f"{'Yes' if result.get('annual_leave_balance_sufficient') else 'No'}"
        )
        st.write(result.get("annual_leave_balance_message", ""))
        st.write(
            "Sales June restriction applies: "
            f"{'Yes' if result.get('sales_june_restriction_applies') else 'No'}"
        )
        st.write(
            "Head of Department approval required: "
            f"{'Yes' if result.get('head_of_department_approval_required') else 'No'}"
        )
        if result.get("sales_june_policy_summary"):
            st.write(result.get("sales_june_policy_summary"))
        if result.get("additional_approval_message"):
            st.write(result.get("additional_approval_message"))
        st.write(
            f"Manager approval required: {'Yes' if result.get('manager_approval_required') else 'No'}"
        )
        st.write(f"Decision status: {result.get('decision_status', '-')}")

        st.markdown("### Passed conditions")
        passed_conditions = result.get("passed_conditions", [])
        if not passed_conditions:
            st.write("- None")
        else:
            for item in passed_conditions:
                if isinstance(item, dict):
                    st.markdown(f"- {item.get('details', item.get('description', ''))}")
                else:
                    st.markdown(f"- {item}")

        st.markdown("### Failed conditions")
        failed_conditions = result.get("failed_conditions", [])
        if not failed_conditions:
            st.write("- None")
        else:
            for item in failed_conditions:
                if isinstance(item, dict):
                    st.markdown(f"- {item.get('details', item.get('description', ''))}")
                else:
                    st.markdown(f"- {item}")
    else:
        with st.container(border=True):
            st.markdown("**Answer**")
            st.write(result.get("answer", "No answer returned."))

        with st.container(border=True):
            source_titles = [item.get("title", "") for item in sources if item.get("title")]
            unique_titles = list(dict.fromkeys(source_titles))
            if unique_titles:
                st.markdown("**Retrieved Document Titles**")
                st.write(", ".join(unique_titles))

    with st.expander("Sources"):
        if not sources:
            st.write("No sources returned.")
        else:
            for index, source in enumerate(sources, start=1):
                title = source.get("title", "-")
                category = source.get("category", "-")
                content_type = source.get("content_type", "-")

                source_line = (
                    f"{index}. {title} | category: {category} | content type: {content_type}"
                )
                st.write(source_line)

    details_label = (
        "Decision evaluation details"
        if result.get("flow_mode") == "birthday_leave_decision"
        else "Retrieval details / Debug view"
    )
    with st.expander(details_label):
        if result.get("flow_mode") == "birthday_leave_decision":
            st.markdown("**Detected intent**")
            st.write(result.get("detected_intent", "-"))

            st.markdown("**Extracted request data**")
            st.json(result.get("parsed_request_data", {}))

            st.markdown("**Employee profile used**")
            st.json(result.get("employee_profile_used", {}))

            st.markdown("**Birthday date used for evaluation**")
            st.write(result.get("birthday_date_for_evaluation", "-"))

            st.markdown("**Allowed Birthday Leave window**")
            st.write(
                f"{result.get('allowed_window_start', '-')} to {result.get('allowed_window_end', '-')}"
            )

            st.markdown("**Retrieved policy sources**")
            for source in result.get("policy_sources", []):
                st.write(f"- {source}")

            st.markdown("**Sales June policy stacking**")
            st.write(
                f"Restriction applies: {'Yes' if result.get('sales_june_restriction_applies') else 'No'}"
            )
            st.write(
                "Head of Department approval required: "
                f"{'Yes' if result.get('head_of_department_approval_required') else 'No'}"
            )
            if result.get("sales_june_policy_summary"):
                st.write(result.get("sales_june_policy_summary"))
            if result.get("additional_approval_message"):
                st.write(result.get("additional_approval_message"))

            st.markdown("**Deterministic checks**")
            st.json(result.get("deterministic_checks", {}))

        retrieved_chunks = result.get("retrieved_chunks", [])
        if not retrieved_chunks:
            if result.get("flow_mode") != "birthday_leave_decision":
                st.write("No retrieval chunks available.")
        else:
            st.markdown("**Retrieved policy chunks**")
            for chunk in retrieved_chunks:
                rank = chunk.get("rank", "-")
                distance = chunk.get("distance", None)
                metadata = chunk.get("metadata", {})
                chunk_text = chunk.get("text", "") or ""
                preview = chunk_text[:320].replace("\n", " ").strip()
                if not preview:
                    preview = "(no text preview)"

                st.markdown(f"**Rank #{rank}**")
                st.write(
                    f"Distance: {distance:.4f}" if isinstance(distance, (float, int)) else "Distance: -"
                )
                st.write(f"Title: {metadata.get('title', '-')}")
                st.write(f"Category: {metadata.get('category', '-')}")
                st.write(f"Content Type: {metadata.get('content_type', '-')}")
                st.write(f"Attachment Name: {metadata.get('attachment_name', '-') or '-'}")
                st.write(f"Email Date: {metadata.get('email_date', '-') or '-'}")
                st.write(f"Preview: {preview}")

                with st.expander("Show full retrieved chunk text"):
                    st.markdown("**Full chunk text**")
                    st.code(chunk_text if chunk_text else "(empty chunk)")
                    st.markdown("**Chunk metadata**")
                    st.json(metadata)

                st.divider()


def get_employee_name_map():
    """Build employee_id -> full_name mapping for manager view."""
    users = load_users()
    mapping = {}
    for username, profile in users.items():
        mapping[str(profile.get("employee_id", ""))] = profile.get("full_name", username)
    return mapping


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
    annual_remaining = get_leave_balance_value(user["employee_id"], "annual_leave", "remaining_days", 0)

    st.title("HR AI Assistant Portal")
    st.write(f"Welcome, **{user['full_name']}**.")

    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Annual Leave Remaining", str(annual_remaining))
    metric_col2.metric("Department", user["department"])
    metric_col3.metric("Manager", user["manager_username"] or "-")

    render_policy_qa_section(user)

    st.divider()
    st.subheader("My HR Requests")
    employee_requests = get_employee_requests(user["employee_id"])

    if employee_requests.empty:
        st.info("No HR requests yet.")
    else:
        st.table(
            employee_requests[
                ["request_type", "leave_start_date", "request_date", "status"]
            ].rename(
                columns={
                    "request_type": "Request Type",
                    "leave_start_date": "Leave Date",
                    "request_date": "Created Date",
                    "status": "Status",
                }
            )
        )


# -----------------------------
# MANAGER PORTAL
# -----------------------------

def manager_portal(user):
    name_map = get_employee_name_map()
    pending_requests = get_manager_pending_requests(user["username"])

    st.title("Manager Approval Portal")
    st.write(f"Welcome, **{user['full_name']}**.")
    st.metric("Pending Requests", int(len(pending_requests)))

    if pending_requests.empty:
        st.info("No pending requests.")
        return

    st.subheader("Pending Requests")

    for _, request_row in pending_requests.iterrows():
        request_id = request_row["request_id"]
        employee_id = str(request_row["employee_id"])
        employee_name = name_map.get(employee_id, employee_id)

        with st.container(border=True):
            st.write(f"**Employee:** {employee_name} ({employee_id})")
            st.write(f"**Request type:** {request_row['request_type']}")
            st.write(f"**Leave date:** {request_row['leave_start_date'] or '-'}")
            st.write(f"**Created date:** {request_row['request_date']}")
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

    annual_remaining = get_leave_balance_value(user["employee_id"], "annual_leave", "remaining_days", 0)

    st.sidebar.header("Employee Profile")
    st.sidebar.write(f"Name: {user['full_name']}")
    st.sidebar.write(f"Employee ID: {user['employee_id']}")
    st.sidebar.write(f"Role: {user['role']}")
    st.sidebar.write(f"Department: {user['department']}")
    st.sidebar.write(f"Hire date: {user['hire_date']}")
    st.sidebar.write(f"Birthday: {user['birthday']}")
    st.sidebar.write(f"Annual leave remaining: {annual_remaining}")
    st.sidebar.write(f"Manager username: {user['manager_username'] or '-'}")
    st.sidebar.write(f"Email: {user['email']}")

    if st.sidebar.button("Log out"):
        st.session_state.logged_in = False
        st.session_state.current_user = None
        st.session_state.policy_qa_result = None
        st.session_state.policy_qa_question = ""
        st.rerun()

    if str(user["role"]).lower() == "manager":
        manager_portal(user)
    else:
        employee_portal(user)


if st.session_state.logged_in:
    main_app()
else:
    login_screen()
