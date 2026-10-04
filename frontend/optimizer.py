"""Phase 19: Resource Optimization page (Streamlit), with cost and time.
Run on its own:  streamlit run frontend/optimizer.py
The function render_optimizer() can also be called from your dashboard.
"""
import os

import httpx
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _call(method, path, params=None):
    try:
        response = httpx.request(method, f"{BACKEND_URL}{path}", params=params, timeout=60.0)
    except httpx.HTTPError as error:
        return None, f"Cannot reach the backend at {BACKEND_URL}: {error}"
    if response.status_code >= 400:
        return None, f"{response.status_code}: {response.text}"
    return response.json(), None


def render_optimizer():
    st.header("Resource Optimization")
    st.warning("SIMULATED data. This is a recommendation only. "
               "A human approves every dispatch in the Approval Center.")

    budget = st.number_input("Budget limit (simulated units, 0 = no limit)",
                             min_value=0, value=0, step=500)
    params = {"budget": budget} if budget > 0 else None

    plan, error = _call("GET", "/optimize/plan", params)
    if error:
        st.error(error)
        return

    summary = plan["summary"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Dispatches", summary["dispatches"])
    col2.metric("Incidents helped", summary["incidents_helped"])
    col3.metric("People in helped incidents", summary["people_in_helped_incidents"])
    col4.metric("Incidents with unmet needs", summary["incidents_with_unmet_needs"])

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Estimated cost", f"{summary['total_cost']:,}")
    avg = summary["avg_eta_min"]
    col6.metric("Average arrival", "n/a" if avg is None else f"{avg:.0f} min")
    cpp = summary["cost_per_person"]
    col7.metric("Cost per person", "n/a" if cpp is None else f"{cpp:,.0f}")
    left = summary["budget_left"]
    col8.metric("Budget left", "no limit" if left is None else f"{left:,}")
    st.caption(f"Costs are illustrative, in {plan['currency']}. They come from one table in "
               "agents/optimizer.py and can be replaced with real tariffs.")
    st.info(plan["summary_text"])

    st.subheader("Recommended allocation")
    if not plan["assignments"]:
        st.write("No allocation to recommend right now.")
    for item in plan["assignments"]:
        with st.container(border=True):
            st.markdown(f"**{item['resource_name']}** to **{item['incident_id']}** "
                        f"({item['priority']}): value {item['value']}, "
                        f"arrives in about {item['eta_min']:.0f} min, cost {item['cost']:,}")
            st.caption(item["explanation"])

    if plan["unassigned_incidents"]:
        st.subheader("Still unmet")
        for item in plan["unassigned_incidents"]:
            reasons = "; ".join(f"{m['need']}: {m['reason']}" for m in item["missing"])
            st.markdown(f"- **{item['incident_id']}** ({item['priority']}): {reasons}")

    with st.expander("Skipped incidents and unused resources"):
        for item in plan["excluded"]:
            st.markdown(f"- {item['incident_id']}: {item['reason']}")
        for item in plan["unused_resources"]:
            st.markdown(f"- {item['name']}: {item['reason']}")
    with st.expander("How the optimizer decides"):
        st.write(plan["objective"])

    if plan["assignments"] and st.button("Send plan to Approval Center", type="primary"):
        data, error = _call("POST", "/optimize/propose", params)
        if error:
            st.error(error)
        else:
            st.success(f"{data['created']} PROPOSED action(s) created. "
                       "Open the Approval Center to approve or reject them.")


if __name__ == "__main__":
    st.set_page_config(page_title="ReliefMesh Resource Optimization", layout="wide")
    render_optimizer()