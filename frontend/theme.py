import html

import streamlit as st

NAVY = "#17323f"
TEAL = "#0b6e57"
RED = "#c8242f"
ORANGE = "#d9731f"
GREEN = "#0b8a6a"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea {{
  font-family: 'Schibsted Grotesk', 'Segoe UI', system-ui, sans-serif !important;
}}
.stApp {{ background: #f4f7f9; color: {NAVY}; }}
#MainMenu, footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.2rem; max-width: 1500px; }}

section[data-testid="stSidebar"] {{ background: #ffffff; border-right: 1px solid #e3e9ee; }}
section[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}
.rm-brand {{ display:flex; align-items:center; gap:14px; margin: 4px 0 22px 0; }}
.rm-logo {{ width:46px; height:46px; background:{NAVY}; color:#fff; display:flex;
  align-items:center; justify-content:center; font-size:22px; border-radius:3px; }}
.rm-brand-name {{ font-weight:800; font-size:22px; letter-spacing:.2px; color:{NAVY}; }}
.rm-sim {{ background:#f1f3f4; border:1px solid #dfe4e8; padding:14px 16px; margin-bottom:22px; }}
.rm-sim b {{ display:block; font-size:11px; letter-spacing:.4px; text-transform:uppercase; margin-bottom:6px; }}
.rm-sim span {{ font-size:15px; line-height:1.5; }}

section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label {{
  padding: 10px 14px; border-radius: 2px; width: 100%; cursor: pointer;
  color: #3b525e; font-weight: 500; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {{ display:none; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {{ background:#eef3f6; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {{
  background: {NAVY}; color: #ffffff; font-weight: 600; }}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) * {{ color:#fff !important; }}
section[data-testid="stSidebar"] div[role="radiogroup"] p {{ font-size: 17px; margin:0; }}

.rm-head {{ display:flex; justify-content:space-between; align-items:flex-start;
  border-bottom:1px solid #e3e9ee; padding-bottom:14px; margin-bottom:22px; }}
.rm-crumb {{ display:flex; align-items:center; gap:10px; font-size:14px; letter-spacing:.3px;
  text-transform:uppercase; color:#4a606b; font-weight:500; }}
.rm-demo {{ background:{TEAL}; color:#fff; font-weight:700; font-size:12px; padding:5px 10px; }}
.rm-title {{ font-size:40px; font-weight:800; margin:4px 0 0 0; color:{NAVY}; display:flex; align-items:center; gap:12px; }}
.rm-title .ico {{ color:{TEAL}; font-size:30px; }}
.rm-clock {{ text-align:right; font-size:12px; color:#4a606b; text-transform:uppercase; }}
.rm-clock b {{ display:block; font-size:19px; color:{NAVY}; margin-top:6px; text-transform:none; font-weight:600; }}

.rm-banner {{ padding:16px 20px; margin-bottom:22px; font-size:17px; line-height:1.6; border:1px solid; }}
.rm-banner b {{ display:block; font-size:12px; text-transform:uppercase; letter-spacing:.3px; margin-bottom:4px; }}
.rm-warn {{ background:#fdf6dc; border-color:#efd98a; color:#4d3b05; }}
.rm-ok {{ background:#d8f0e8; border-color:#a6dcc9; color:#134d3d; }}
.rm-info {{ background:#e3eff7; border-color:#b4d3e8; color:#143f5a; }}

.rm-section {{ display:flex; justify-content:space-between; align-items:baseline; margin:10px 0 14px 0; }}
.rm-section h2 {{ font-size:28px; font-weight:800; margin:0; color:{NAVY}; }}
.rm-section span {{ color:#4a606b; font-size:15px; }}

.rm-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:20px; margin-bottom:20px; }}
.rm-card {{ background:#fff; border:1px solid #dfe6eb; padding:22px 24px; min-height:150px;
  display:flex; flex-direction:column; justify-content:space-between; }}
.rm-card .lbl {{ font-size:15px; font-weight:600; color:#3b525e; }}
.rm-card .val {{ font-size:46px; font-weight:800; line-height:1; color:{NAVY}; }}
.rm-red {{ color:{RED} !important; }} .rm-orange {{ color:{ORANGE} !important; }} .rm-green {{ color:{GREEN} !important; }}
@media (max-width: 1000px) {{ .rm-grid {{ grid-template-columns:repeat(2, minmax(0,1fr)); }} }}

.rm-panel {{ background:#fff; border:1px solid #dfe6eb; margin:6px 0 22px 0; }}
.rm-panel-head {{ padding:18px 24px; }}
.rm-panel-head h3 {{ margin:0; font-size:19px; font-weight:800; letter-spacing:.3px; text-transform:uppercase; }}
.rm-panel-head p {{ margin:4px 0 0 0; color:#4a606b; font-size:15px; }}
.rm-scroll {{ overflow-x:auto; }}
table.rm-table {{ width:100%; border-collapse:collapse; font-size:16px; }}
.rm-table th {{ text-align:left; font-size:12px; letter-spacing:.4px; text-transform:uppercase; color:#4a606b;
  background:#f8fafb; padding:14px 18px; border-top:1px solid #e3e9ee; border-bottom:1px solid #e3e9ee; font-weight:600; }}
.rm-table td {{ padding:14px 18px; border-bottom:1px solid #eef2f5; vertical-align:middle; }}
.rm-table td.id {{ font-weight:600; color:#3b525e; white-space:nowrap; }}
.rm-table td.needs {{ color:#4a606b; font-size:14px; }}
.rm-table td.rep {{ color:{GREEN}; font-weight:600; text-align:right; }}
.rm-badge {{ display:inline-block; font-size:12px; font-weight:700; letter-spacing:.4px; padding:6px 14px; text-transform:uppercase; }}
.rm-b-critical {{ background:#fbdede; color:{RED}; }}
.rm-b-high {{ background:#fde6c9; color:#c0541a; }}
.rm-b-medium {{ background:#fff1b8; color:#8a6a00; }}
.rm-b-low {{ background:#dff1e6; color:#1a7a52; }}
.rm-b-unrated {{ background:#e8edf0; color:#4a606b; }}

.rm-dark {{ background:{NAVY}; color:#fff; padding:26px 28px; min-height:430px; }}
.rm-dark h4 {{ margin:0 0 14px 0; font-size:16px; font-weight:700; text-transform:uppercase; letter-spacing:.3px; color:#fff; }}
.rm-dark p {{ font-size:18px; line-height:1.6; margin:0 0 18px 0; color:#fff; }}
.rm-dark hr {{ border:0; border-top:1px solid #3a5663; margin:18px 0; }}
.rm-dark .small {{ font-size:12px; text-transform:uppercase; color:#b6c7cf; margin-bottom:8px; }}
.rm-dark .body {{ font-size:15px; line-height:1.6; }}

div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {{
  border-radius: 2px; border:1px solid #dfe6eb; background:#fff; color:{NAVY}; font-weight:500; }}
div[data-testid="stButton"] button:hover {{ border-color:{TEAL}; color:{TEAL}; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid #dfe6eb; padding:14px 18px; }}
div[data-testid="stExpander"] {{ background:#fff; border:1px solid #dfe6eb; border-radius:2px; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def sidebar_brand() -> None:
    st.sidebar.markdown(
        '<div class="rm-brand"><div class="rm-logo">◇</div>'
        '<div class="rm-brand-name">RELIEFMESH AI</div></div>'
        '<div class="rm-sim"><b>Simulated environment</b>'
        "<span>Decision-support prototype.</span></div>",
        unsafe_allow_html=True,
    )


def page_header(title: str, icon: str = "◎", scenario: str = "", clock: str = "") -> None:
    crumb = (
        f'<div class="rm-crumb"><span class="rm-demo">DEMO</span><span>{esc(scenario)}</span></div>'
        if scenario else ""
    )
    clock_html = f'<div class="rm-clock">Demo clock<b>{esc(clock)}</b></div>' if clock else ""
    st.markdown(
        f'<div class="rm-head"><div>{crumb}'
        f'<div class="rm-title"><span class="ico">{icon}</span>{esc(title)}</div></div>'
        f"{clock_html}</div>",
        unsafe_allow_html=True,
    )


def banner(kind: str, text: str, heading: str = "") -> None:
    head = f"<b>{esc(heading)}</b>" if heading else ""
    st.markdown(f'<div class="rm-banner rm-{kind}">{head}{esc(text)}</div>', unsafe_allow_html=True)


def section(title: str, right: str = "") -> None:
    st.markdown(
        f'<div class="rm-section"><h2>{esc(title)}</h2><span>{esc(right)}</span></div>',
        unsafe_allow_html=True,
    )


def metric_grid(cards) -> None:
    cells = "".join(
        f'<div class="rm-card"><div class="lbl">{esc(label)}</div>'
        f'<div class="val {"rm-" + color if color else ""}">{esc(value)}</div></div>'
        for label, value, color in cards
    )
    st.markdown(f'<div class="rm-grid">{cells}</div>', unsafe_allow_html=True)


def priority_badge(priority: str) -> str:
    key = (priority or "unrated").lower()
    if key not in ("critical", "high", "medium", "low"):
        key = "unrated"
    return f'<span class="rm-badge rm-b-{key}">{esc(priority or "Unrated")}</span>'


def _pretty_need(need: str) -> str:
    return need.replace("_", " ")


def ledger_html(title: str, subtitle: str, incidents) -> str:
    rows = []
    for inc in incidents:
        conf = "-" if inc.get("confidence") is None else f'{inc["confidence"]}%'
        needs = ", ".join(_pretty_need(n) for n in inc.get("needs", [])).capitalize() or "-"
        rows.append(
            "<tr>"
            f'<td class="id">{esc(inc["id"])}</td>'
            f'<td>{priority_badge(inc.get("priority"))}</td>'
            f"<td>{esc(conf)}</td>"
            f'<td>{esc(inc.get("title"))}</td>'
            f'<td>{esc(inc.get("affected"))}</td>'
            f'<td>{"Yes" if inc.get("medical") else "No"}</td>'
            f'<td class="needs">{esc(needs)}</td>'
            f'<td class="rep">{esc(inc.get("reports"))}</td>'
            "</tr>"
        )
    head = "".join(
        f"<th>{h}</th>"
        for h in ("ID", "Priority", "Conf.", "Description", "Affected", "Medical", "Needs", "Reports")
    )
    return (
        '<div class="rm-panel"><div class="rm-panel-head">'
        f"<h3>{esc(title)}</h3><p>{esc(subtitle)}</p></div>"
        f'<div class="rm-scroll"><table class="rm-table"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></div>'
    )


def dark_status_panel(heading: str, text: str, record_title: str, record_text: str) -> str:
    return (
        f'<div class="rm-dark"><h4>✓ {esc(heading)}</h4><p>{esc(text)}</p><hr>'
        f'<div class="small">{esc(record_title)}</div><div class="body">{esc(record_text)}</div></div>'
    )
