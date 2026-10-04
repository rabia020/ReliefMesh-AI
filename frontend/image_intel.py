"""Phase 18: Image Intelligence page (Streamlit).
Run on its own:  streamlit run frontend/image_intel.py
The function render_image_intelligence() can also be called from your dashboard.
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


def render_image_intelligence():
    st.header("Image Intelligence")
    st.warning(
        "AI image reading can be wrong. It only nudges evidence confidence a little, "
        "and a human still decides."
    )
    upload = st.file_uploader("Disaster photo", type=["jpg", "jpeg", "png", "webp"])
    report_id = st.text_input("Link to a report or incident id (optional, e.g. INC-021)")
    force = st.checkbox("Ignore cache and analyze again", value=False)

    if upload is None:
        return
    st.image(upload, width=420)
    if not st.button("Analyze image", type="primary"):
        return

    with st.spinner("Reading the photo..."):
        try:
            response = httpx.post(
                f"{BACKEND_URL}/images/analyze",
                files={"file": (upload.name, upload.getvalue(), upload.type or "image/jpeg")},
                data={"report_id": report_id.strip(), "force": str(force).lower()},
                timeout=180.0,
            )
        except httpx.HTTPError as error:
            st.error(f"Cannot reach the backend at {BACKEND_URL}: {error}")
            return
    if response.status_code >= 400:
        st.error(f"{response.status_code}: {response.json().get('detail', response.text)}")
        return

    result = response.json()
    analysis = result["analysis"]
    st.success(analysis["summary"] or "Analysis complete.")
    st.caption(f"{result['provider']} / {result['model']} | cached: {result['cached']} | "
               f"model confidence: {analysis['confidence']:.0%}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Flood water", analysis["flood_water"].replace("_", " "))
    col2.metric("Road blocked", str(analysis["road_blocked"]))
    col3.metric("Damaged structures", str(analysis["damaged_structures"]))
    col1.metric("Vehicles", str(analysis["vehicles"]["count"]))
    col2.metric("People visible", str(analysis["people_visible"]))
    col3.metric("Crowding", analysis["crowding"])
    st.markdown("**Hazards:** " + (", ".join(analysis["hazards"]) or "none seen"))


if __name__ == "__main__":
    st.set_page_config(page_title="ReliefMesh Image Intelligence", layout="wide")
    render_image_intelligence()