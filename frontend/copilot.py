"""Phase 20: AI Copilot chat page (Streamlit).
Run on its own:  streamlit run frontend/copilot.py
The function render_copilot() can also be called from your dashboard.
"""
import json
import os

import httpx
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
EXAMPLES = [
    "What are the three most urgent incidents?",
    "Where should I send the two available boats?",
    "Which incidents involve medical emergencies?",
    "Why is Incident 2 critical?",
    "Which shelter can accommodate 30 people?",
]


def _ask(question):
    try:
        response = httpx.post(f"{BACKEND_URL}/copilot/ask", json={"question": question}, timeout=180.0)
    except httpx.HTTPError as error:
        return None, f"Cannot reach the backend at {BACKEND_URL}: {error}"
    if response.status_code >= 400:
        return None, f"{response.status_code}: {response.text}"
    return response.json(), None


def _show_tools(tools):
    with st.expander(f"MCP tools used ({len(tools)})"):
        if not tools:
            st.write("No tools were needed.")
        for call in tools:
            st.markdown(f"- **{call['server']}.{call['tool']}** `{json.dumps(call['args'])}` "
                        f"gave {call['result']} ({call['ms']} ms)")


def render_copilot():
    st.header("AI Copilot")
    st.warning("SIMULATED data. The copilot reads data and recommends. It cannot dispatch anything: "
               "a human approves every action in the Approval Center.")
    if "copilot_messages" not in st.session_state:
        st.session_state["copilot_messages"] = []

    with st.expander("Example questions", expanded=not st.session_state["copilot_messages"]):
        for example in EXAMPLES:
            if st.button(example, key=f"example_{example}"):
                st.session_state["copilot_pending"] = example

    for message in st.session_state["copilot_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("meta"):
                st.caption(message["meta"])
            if message["role"] == "assistant" and "tools" in message:
                _show_tools(message["tools"])

    question = st.chat_input("Ask about incidents, resources, shelters, hospitals...")
    question = question or st.session_state.pop("copilot_pending", None)
    if question:
        st.session_state["copilot_messages"].append({"role": "user", "content": question})
        with st.spinner("Asking the MCP tools..."):
            data, error = _ask(question)
        if error:
            st.session_state["copilot_messages"].append({"role": "assistant", "content": error})
        else:
            st.session_state["copilot_messages"].append({
                "role": "assistant", "content": data["answer"], "tools": data["tool_calls"],
                "meta": f"intent: {data['intent']} (by {data['routed_by']}) | answered by: {data['answered_by']}",
            })
        st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="ReliefMesh AI Copilot", layout="wide")
    render_copilot()