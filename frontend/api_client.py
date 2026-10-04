import os

import httpx

from frontend.db import BackendError


def backend_url() -> str:
    url = os.getenv("BACKEND_URL")
    if not url:
        try:
            import streamlit as st

            url = st.secrets.get("BACKEND_URL")
        except Exception:
            url = None
    return (url or "http://127.0.0.1:8000").rstrip("/")


def get_json(path: str, timeout: float = 90.0):
    try:
        response = httpx.get(f"{backend_url()}{path}", timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as error:
        raise BackendError(str(error)) from error


def post_json(path: str, payload: dict, timeout: float = 120.0):
    try:
        response = httpx.post(f"{backend_url()}{path}", json=payload, timeout=timeout)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise BackendError(str(detail))
        return response.json()
    except httpx.HTTPError as error:
        raise BackendError(str(error)) from error
