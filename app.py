"""
ARGUS — Multi-Agent Research Console
A control-room style Streamlit front end for the search -> read -> write -> critique
agent pipeline defined in agents.py.

Note: this file calls the same building blocks pipeline.py uses (build_search_agent,
build_reader_agent, writer_chain, critic_chain) directly, instead of calling
run_research_pipeline() as one opaque blocking call. That's what lets the UI show
real, live per-stage progress instead of a single spinner. Two bugs present in
pipeline.py are fixed here (see the "FIX vs pipeline.py" comments below) — worth
porting the same fixes back into pipeline.py for the terminal version.
"""

import hashlib
import html
import time

import streamlit as st
from agents import build_reader_agent, build_search_agent, writer_chain, critic_chain

# ----------------------------------------------------------------------------
# Page config
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="ARGUS · Research Console",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

STAGES = ["SEARCH", "READ", "WRITE", "CRITIQUE"]

# ----------------------------------------------------------------------------
# Design tokens / global styling
# ----------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --void:#05070A;
  --panel:#0D1117;
  --panel-raised:#131A24;
  --line:#1F2A38;
  --cyan:#4FD1C5;
  --violet:#A78BFA;
  --text:#E6EDF3;
  --muted:#7E8B9A;
  --success:#34D399;
  --warning:#FBBF24;
  --error:#F87171;
}

html, body, .stApp{
  background: radial-gradient(ellipse 120% 80% at 50% -10%, #0A1420 0%, var(--void) 55%) !important;
  color: var(--text);
  font-family: 'Inter', sans-serif;
}
[data-testid="stHeader"]{ background: transparent; }
[data-testid="stSidebar"]{
  background: var(--panel);
  border-right: 1px solid var(--line);
}
#MainMenu, footer { visibility: hidden; }

h1, h2, h3, .argus-display{
  font-family: 'Space Grotesk', sans-serif !important;
  letter-spacing: 0.01em;
}

.mono{ font-family:'JetBrains Mono', monospace; }

/* ---------- top status bar ---------- */
.argus-topbar{
  display:flex; justify-content:space-between; align-items:center;
  padding: 14px 22px; margin-bottom: 28px;
  background: linear-gradient(180deg, var(--panel-raised) 0%, var(--panel) 100%);
  border: 1px solid var(--line); border-radius: 10px;
}
.argus-brand{ display:flex; align-items:center; gap:12px; }
.argus-brand .mark{
  width:34px; height:34px; border-radius:8px;
  background: conic-gradient(from 220deg, var(--cyan), var(--violet), var(--cyan));
  display:flex; align-items:center; justify-content:center;
  font-family:'Space Grotesk',sans-serif; font-weight:700; color:var(--void); font-size:16px;
}
.argus-brand .title{ font-size:19px; font-weight:600; color:var(--text); line-height:1.1; }
.argus-brand .subtitle{ font-size:11.5px; color:var(--muted); letter-spacing:0.08em; text-transform:uppercase; }
.argus-status{ display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); }
.dot{ width:8px; height:8px; border-radius:50%; background:var(--success); box-shadow: 0 0 8px var(--success); }
.dot.pulse{ animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse{ 0%,100%{opacity:1;} 50%{opacity:0.35;} }

/* ---------- pipeline tracker ---------- */
.tracker{ display:flex; align-items:center; margin: 6px 0 30px 0; }
.node-wrap{ display:flex; flex-direction:column; align-items:center; flex:0 0 auto; width:120px; }
.node{
  width:46px; height:46px; border-radius:50%;
  border:2px solid var(--line); background:var(--panel-raised);
  display:flex; align-items:center; justify-content:center;
  font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted);
  transition: all 0.35s ease;
}
.node.done{ border-color: var(--success); color: var(--success); background: rgba(52,211,153,0.08); }
.node.active{
  border-color: var(--cyan); color: var(--cyan); background: rgba(79,209,197,0.10);
  box-shadow: 0 0 0 4px rgba(79,209,197,0.12), 0 0 16px rgba(79,209,197,0.35);
  animation: node-pulse 1.4s ease-in-out infinite;
}
.node.error{ border-color: var(--error); color: var(--error); background: rgba(248,113,113,0.10); }
@keyframes node-pulse{ 0%,100%{ box-shadow:0 0 0 4px rgba(79,209,197,0.12), 0 0 16px rgba(79,209,197,0.35);} 50%{ box-shadow:0 0 0 7px rgba(79,209,197,0.06), 0 0 24px rgba(79,209,197,0.55);} }
.node-label{ margin-top:8px; font-size:10.5px; letter-spacing:0.1em; color:var(--muted); font-family:'JetBrains Mono',monospace; }
.node-label.on{ color: var(--text); }
.connector{ flex:1 1 auto; height:2px; background: var(--line); margin: 0 -14px; position:relative; top:-19px; transition: background 0.35s ease; }
.connector.done{ background: var(--success); }
.connector.active{ background: linear-gradient(90deg, var(--success), var(--cyan)); }

/* ---------- command bar ---------- */
.stTextInput input{
  background: var(--panel) !important; color: var(--text) !important;
  border: 1px solid var(--line) !important; border-radius: 8px !important;
  font-family:'JetBrains Mono',monospace !important; font-size:14.5px !important;
  padding: 12px 14px !important;
}
.stTextInput input:focus{ border-color: var(--cyan) !important; box-shadow: 0 0 0 1px var(--cyan) !important; }
.stTextInput label{ color: var(--muted) !important; font-size:11.5px !important; letter-spacing:0.08em; text-transform:uppercase; }

.stButton button, .stFormSubmitButton button{
  background: linear-gradient(180deg, #1a2230, #10151d) !important;
  color: var(--cyan) !important;
  border: 1px solid var(--cyan) !important;
  border-radius: 8px !important;
  font-family:'JetBrains Mono',monospace !important;
  letter-spacing: 0.08em; font-weight:500;
  padding: 10px 22px !important;
  transition: all 0.2s ease;
}
.stButton button:hover, .stFormSubmitButton button:hover{
  background: var(--cyan) !important; color: var(--void) !important;
  box-shadow: 0 0 18px rgba(79,209,197,0.45);
}

/* ---------- HUD panel ---------- */
.hud-panel{
  position:relative; background: var(--panel);
  border: 1px solid var(--line); border-radius: 10px;
  padding: 20px 22px; margin-top: 6px;
}
.hud-panel::before, .hud-panel::after,
.hud-panel .c2::before, .hud-panel .c2::after{
  content:""; position:absolute; width:14px; height:14px; opacity:0.8;
}
.hud-panel::before{ top:-1px; left:-1px; border-top:2px solid var(--cyan); border-left:2px solid var(--cyan); border-radius: 4px 0 0 0;}
.hud-panel::after{ top:-1px; right:-1px; border-top:2px solid var(--cyan); border-right:2px solid var(--cyan); border-radius: 0 4px 0 0;}
.hud-panel .c2::before{ bottom:-1px; left:-1px; border-bottom:2px solid var(--cyan); border-left:2px solid var(--cyan); border-radius: 0 0 0 4px;}
.hud-panel .c2::after{ bottom:-1px; right:-1px; border-bottom:2px solid var(--cyan); border-right:2px solid var(--cyan); border-radius: 0 0 4px 0;}
.hud-label{ font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:0.12em; color:var(--muted); text-transform:uppercase; margin-bottom:10px; display:flex; justify-content:space-between; }
.hud-body{ font-family:'JetBrains Mono',monospace; font-size:13px; line-height:1.65; color:#C7D2DE; white-space:pre-wrap; max-height:420px; overflow-y:auto; }

/* ---------- stat chips ---------- */
.chip-row{ display:flex; gap:10px; flex-wrap:wrap; margin: 4px 0 22px 0; }
.chip{
  font-family:'JetBrains Mono',monospace; font-size:11.5px; color:var(--muted);
  background: var(--panel-raised); border:1px solid var(--line); border-radius:20px;
  padding: 6px 13px;
}
.chip b{ color: var(--cyan); font-weight:600; }

/* ---------- tabs ---------- */
.stTabs [data-baseweb="tab-list"]{ gap: 4px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"]{
  font-family:'JetBrains Mono',monospace; font-size:12.5px; letter-spacing:0.05em;
  color: var(--muted); background: transparent; border-radius: 6px 6px 0 0;
}
.stTabs [aria-selected="true"]{ color: var(--cyan) !important; border-bottom: 2px solid var(--cyan) !important; }

@media (prefers-reduced-motion: reduce){
  .dot.pulse, .node.active{ animation: none; }
}
@media (max-width: 700px){
  .node-wrap{ width: 78px; }
  .node-label{ font-size:9px; }
}
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
if "state" not in st.session_state:
    st.session_state.state = None
if "topic" not in st.session_state:
    st.session_state.topic = ""
if "session_id" not in st.session_state:
    st.session_state.session_id = hashlib.sha1(str(time.time()).encode()).hexdigest()[:4].upper()

# ----------------------------------------------------------------------------
# Top bar
# ----------------------------------------------------------------------------
st.markdown(
    f"""
<div class="argus-topbar">
  <div class="argus-brand">
    <div class="mark">A</div>
    <div>
      <div class="title">ARGUS</div>
      <div class="subtitle">Multi-Agent Research Console</div>
    </div>
  </div>
  <div class="argus-status">
    <span class="mono">SESSION #{st.session_state.session_id}</span>
    <span style="opacity:0.3">|</span>
    <span class="dot pulse"></span> AGENTS ONLINE
  </div>
</div>
""",
    unsafe_allow_html=True,
)


def render_tracker(active_idx: int, error_idx: int = -1) -> str:
    """active_idx: -1 = nothing started, 0..3 = current stage, 4 = all done."""
    nodes_html = []
    for i, name in enumerate(STAGES):
        if i == error_idx:
            node_cls, label_cls, glyph = "error", "on", "✕"
        elif i < active_idx or active_idx == 4:
            node_cls, label_cls, glyph = "done", "on", "✓"
        elif i == active_idx:
            node_cls, label_cls, glyph = "active", "on", f"0{i+1}"
        else:
            node_cls, label_cls, glyph = "", "", f"0{i+1}"

        nodes_html.append(
            f'<div class="node-wrap"><div class="node {node_cls}">{glyph}</div>'
            f'<div class="node-label {label_cls}">{name}</div></div>'
        )
        if i < len(STAGES) - 1:
            if i < active_idx or active_idx == 4:
                conn_cls = "done"
            elif i == active_idx and error_idx == -1:
                conn_cls = "active"
            else:
                conn_cls = ""
            nodes_html.append(f'<div class="connector {conn_cls}"></div>')

    return f'<div class="tracker">{"".join(nodes_html)}</div>'


tracker_slot = st.empty()
tracker_slot.markdown(render_tracker(-1), unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# Command input
# ----------------------------------------------------------------------------
with st.form("research_form", clear_on_submit=False):
    c1, c2 = st.columns([0.85, 0.15])
    with c1:
        topic = st.text_input(
            "Query",
            value=st.session_state.topic,
            placeholder='research.run(topic="e.g. impact of quantum computing on cryptography")',
            label_visibility="collapsed",
        )
    with c2:
        submitted = st.form_submit_button("▶ RUN", use_container_width=True)

status_slot = st.empty()

# ----------------------------------------------------------------------------
# Pipeline execution (mirrors pipeline.run_research_pipeline, stage by stage,
# so the tracker above updates live as each agent actually finishes)
# ----------------------------------------------------------------------------
if submitted:
    if not topic.strip():
        st.warning("Enter a topic before launching the pipeline.")
    else:
        st.session_state.topic = topic
        st.session_state.state = None
        state = {}

        def status(msg, color="var(--muted)"):
            status_slot.markdown(f'<span class="mono" style="color:{color}">› {msg}</span>', unsafe_allow_html=True)

        try:
            # Stage 0 — SEARCH
            tracker_slot.markdown(render_tracker(0), unsafe_allow_html=True)
            status("dispatching search agent...")
            search_agent = build_search_agent()
            search_result = search_agent.invoke(
                {"messages": [("user", f"Find recent, reliable and detailed information about: {topic}")]}
            )
            state["search_result"] = search_result["messages"][-1].content

            # Stage 1 — READ
            tracker_slot.markdown(render_tracker(1), unsafe_allow_html=True)
            status("reader agent scraping top source...")
            reader_agent = build_reader_agent()
            reader_result = reader_agent.invoke(
                {
                    "messages": [
                        (
                            "user",
                            f"Based on the following search results about '{topic}', "
                            f"pick the most relevant URL and scrape it for deeper content.\n\n"
                            f"Search Results:\n{state['search_result'][:800]}",
                        )
                    ]
                }
            )
            state["scraped_content"] = reader_result["messages"][-1].content

            # Stage 2 — WRITE
            tracker_slot.markdown(render_tracker(2), unsafe_allow_html=True)
            status("writer chain drafting report...")
            # FIX vs pipeline.py: original code concatenated search_result twice
            # instead of including scraped_content — fixed here.
            research_combined = (
                f"SEARCH RESULTS : \n {state['search_result']}\n\n"
                f"DETAILED SCRAPED CONTENT : \n {state['scraped_content']}"
            )
            state["report"] = writer_chain.invoke({"topic": topic, "research": research_combined})

            # Stage 3 — CRITIQUE
            tracker_slot.markdown(render_tracker(3), unsafe_allow_html=True)
            status("critic chain reviewing report...")
            # FIX vs pipeline.py: original code never assigned the critic's
            # output to state["feedback"] — fixed here.
            state["feedback"] = critic_chain.invoke({"report": state["report"]})

            tracker_slot.markdown(render_tracker(4), unsafe_allow_html=True)
            status("pipeline complete", color="var(--success)")
            st.session_state.state = state

        except Exception as e:
            done_count = len(state)
            tracker_slot.markdown(render_tracker(done_count, error_idx=done_count), unsafe_allow_html=True)
            status(f"pipeline failed — {e}", color="var(--error)")
            st.session_state.state = state or None

# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
state = st.session_state.state
if state:
    def wc(s):
        return len(s) if isinstance(s, str) else len(str(s)) if s else 0

    st.markdown(
        f"""
<div class="chip-row">
  <div class="chip">TOPIC · <b>{html.escape(st.session_state.topic)}</b></div>
  <div class="chip">SEARCH_YIELD · <b>{wc(state.get('search_result',''))}</b> chars</div>
  <div class="chip">SCRAPED · <b>{wc(state.get('scraped_content',''))}</b> chars</div>
  <div class="chip">REPORT · <b>{wc(state.get('report',''))}</b> chars</div>
</div>
""",
        unsafe_allow_html=True,
    )

    tab_report, tab_feedback, tab_search, tab_scraped = st.tabs(
        ["◆ REPORT", "◆ CRITIQUE", "◆ SEARCH LOG", "◆ SOURCE CONTENT"]
    )

    def panel(label, body):
        body_str = body if isinstance(body, str) else (str(body) if body else "— no data —")
        st.markdown(
            f"""
<div class="hud-panel"><div class="c2">
  <div class="hud-label"><span>{label}</span><span>ARGUS</span></div>
  <div class="hud-body">{html.escape(body_str)}</div>
</div></div>
""",
            unsafe_allow_html=True,
        )

    with tab_report:
        report = state.get("report", "")
        st.markdown(report if isinstance(report, str) else str(report))
        st.download_button(
            "⬇ Download report (.md)",
            data=report if isinstance(report, str) else str(report),
            file_name=f"{st.session_state.topic.replace(' ', '_')}_report.md",
        )

    with tab_feedback:
        feedback = state.get("feedback")
        if feedback:
            st.markdown(feedback if isinstance(feedback, str) else str(feedback))
        else:
            st.info("No critic feedback returned for this run.")

    with tab_search:
        panel("SEARCH_AGENT.OUTPUT", state.get("search_result", ""))

    with tab_scraped:
        panel("READER_AGENT.OUTPUT", state.get("scraped_content", ""))

elif not submitted:
    st.markdown(
        '<div class="chip-row"><div class="chip">STANDING BY · enter a topic and press RUN to launch the pipeline</div></div>',
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="argus-display" style="font-size:15px;font-weight:600;">SYSTEM</div>', unsafe_allow_html=True)
    st.caption("agents.py · pipeline.py · .env must sit next to this file.")
    st.markdown("**Pipeline**")
    st.markdown(
        '<span class="mono" style="font-size:12px;color:var(--muted)">SEARCH → READ → WRITE → CRITIQUE</span>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("**Run locally**")
    st.code("streamlit run streamlit_app.py", language="bash")
