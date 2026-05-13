import os

from dotenv import load_dotenv


def get_secret(key: str, default: str | None = None) -> str | None:
    """
    Read secret from local .env first, then Streamlit secrets.
    If found in Streamlit secrets, also mirror to os.environ so libraries
    relying on env vars (for example ChatOpenAI) can work without changes.
    """
    load_dotenv()

    env_value = os.getenv(key)
    if env_value:
        return env_value

    try:
        import streamlit as st

        if key in st.secrets:
            secret_value = str(st.secrets[key])
            os.environ[key] = secret_value
            return secret_value
    except Exception:
        # Streamlit runtime/secrets may be unavailable in non-Streamlit scripts.
        pass

    return default


def require_secret(key: str) -> str:
    """Get required secret or raise a clear error."""
    value = get_secret(key)
    if not value:
        raise ValueError(f"{key} is missing. Provide it in .env or Streamlit secrets.")
    return value
