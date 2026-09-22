"""
app.py
------
Gradio dashboard for the AI-based Urban Traffic Monitoring System.

Run with:  python app.py

The dashboard lets you:
  - Step the simulation forward manually or auto-run it on a timer
  - See live per-intersection status (congestion level, speed, incidents)
  - Watch the multi-agent reasoning trace as decisions are made
  - See control-room alerts and (optionally) an LLM-generated briefing
  - View rolling trend charts
  - Manually inject an incident at a chosen intersection to see the
    agents react

Visual design: warm beige / forest-green "control room" theme, KPI
summary strip, tabbed layout (Live / Reasoning / Trends) and HTML-card
styled alerts, recommendations and log entries instead of raw markdown.
"""

import pandas as pd
import gradio as gr
import plotly.graph_objects as go

from orchestrator import TrafficMonitoringSystem

system = TrafficMonitoringSystem(history_len=60)

# --------------------------------------------------------------------------
# Palette — warm beige / forest-green, kept earthy rather than "alarm-panel"
# bright so it reads as a considered design rather than default warning colors.
# --------------------------------------------------------------------------
PALETTE = {
    "bg": "#f6f1e6",
    "bg_alt": "#efe7d6",
    "card": "#fffdf7",
    "border": "#e2d7bd",
    "ink": "#2f3324",
    "ink_soft": "#5b5c4d",
    "forest": "#3f6b3f",
    "forest_dark": "#2c4d2c",
    "sage": "#8ba672",
    "gold": "#c8a03d",
    "terracotta": "#c0603f",
    "brick": "#a8402f",
}

CONGESTION_COLOR = {
    "Free Flow": "#4c7d3f",
    "Moderate": "#c8a03d",
    "Heavy": "#c0603f",
    "Severe": "#a8402f",
}

SEVERITY_COLOR = {"HIGH": "#a8402f", "MEDIUM": "#c8a03d", "LOW": "#4c7d3f"}
SEVERITY_LABEL = {"HIGH": "● High", "MEDIUM": "● Medium", "LOW": "● Low"}

CUSTOM_CSS = f"""
:root {{
    --tm-bg: {PALETTE['bg']};
    --tm-bg-alt: {PALETTE['bg_alt']};
    --tm-card: {PALETTE['card']};
    --tm-border: {PALETTE['border']};
    --tm-ink: {PALETTE['ink']};
    --tm-ink-soft: {PALETTE['ink_soft']};
    --tm-forest: {PALETTE['forest']};
    --tm-forest-dark: {PALETTE['forest_dark']};
    --tm-sage: {PALETTE['sage']};
    --tm-gold: {PALETTE['gold']};
}}

.gradio-container {{
    background: var(--tm-bg) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    max-width: 1400px !important;
}}

/* ---- Header banner ---- */
#tm-header {{
    background: linear-gradient(120deg, var(--tm-forest-dark) 0%, var(--tm-forest) 65%, var(--tm-sage) 100%);
    border-radius: 16px;
    padding: 22px 28px;
    margin-bottom: 14px;
    box-shadow: 0 4px 14px rgba(44, 77, 44, 0.18);
}}
#tm-header h1 {{
    color: #fbf8ee !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    margin: 0 0 4px 0 !important;
}}
#tm-header p {{
    color: #e7e2cf !important;
    font-size: 0.92rem !important;
    margin: 0 !important;
}}

/* ---- KPI strip ---- */
.tm-kpi-row {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 16px;
}}
.tm-kpi-card {{
    flex: 1 1 180px;
    background: var(--tm-card);
    border: 1px solid var(--tm-border);
    border-left: 5px solid var(--tm-forest);
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 2px 6px rgba(47, 51, 36, 0.06);
}}
.tm-kpi-card.warn {{ border-left-color: var(--tm-gold); }}
.tm-kpi-card.alert {{ border-left-color: {PALETTE['brick']}; }}
.tm-kpi-label {{
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--tm-ink-soft);
    font-weight: 600;
    margin-bottom: 4px;
}}
.tm-kpi-value {{
    font-size: 1.65rem;
    font-weight: 700;
    color: var(--tm-ink);
    line-height: 1.1;
}}
.tm-kpi-sub {{
    font-size: 0.76rem;
    color: var(--tm-ink-soft);
    margin-top: 2px;
}}

/* ---- Generic section card ---- */
.tm-panel {{
    background: var(--tm-card);
    border: 1px solid var(--tm-border);
    border-radius: 14px;
    padding: 16px 18px;
}}
.tm-panel-title {{
    font-weight: 700;
    font-size: 0.98rem;
    color: var(--tm-forest-dark);
    margin: 0 0 10px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}}

/* ---- Alert / recommendation chips ---- */
.tm-alert-item {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 9px 10px;
    border-radius: 10px;
    margin-bottom: 7px;
    background: var(--tm-bg-alt);
    border: 1px solid var(--tm-border);
}}
.tm-badge {{
    flex-shrink: 0;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    padding: 2px 8px;
    border-radius: 999px;
    color: #fff;
    white-space: nowrap;
}}
.tm-alert-text {{ font-size: 0.87rem; color: var(--tm-ink); }}
.tm-empty {{ color: var(--tm-ink-soft); font-size: 0.87rem; font-style: italic; }}

.tm-rec-group-title {{
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--tm-forest-dark);
    margin: 10px 0 6px 0;
}}

/* ---- Reasoning trace timeline ---- */
.tm-log-item {{
    position: relative;
    padding: 6px 0 6px 20px;
    border-left: 2px solid var(--tm-border);
    margin-left: 6px;
}}
.tm-log-item::before {{
    content: "";
    position: absolute;
    left: -5px;
    top: 12px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--tm-forest);
}}
.tm-log-agent {{
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--tm-forest-dark);
    background: #e7f0e1;
    padding: 1px 7px;
    border-radius: 6px;
    margin-right: 6px;
}}
.tm-log-msg {{ font-size: 0.85rem; color: var(--tm-ink); }}

/* ---- Briefing box ---- */
.tm-briefing {{
    background: linear-gradient(135deg, #f2ecd8 0%, #eae1c6 100%);
    border: 1px solid var(--tm-border);
    border-radius: 12px;
    padding: 14px 16px;
    font-size: 0.88rem;
    color: var(--tm-ink);
    line-height: 1.5;
}}
.tm-briefing.off {{ font-style: italic; color: var(--tm-ink-soft); background: var(--tm-bg-alt); }}

/* ---- Buttons ---- */
#tm-step-btn {{
    background: var(--tm-forest) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
}}
#tm-step-btn:hover {{ background: var(--tm-forest-dark) !important; }}
#tm-inject-btn {{
    background: {PALETTE['terracotta']} !important;
    border: none !important;
    color: #fff !important;
    font-weight: 600 !important;
}}
#tm-inject-btn:hover {{ background: {PALETTE['brick']} !important; }}

/* ---- Tables ---- */
.tm-table table {{ font-size: 0.85rem !important; }}

/* ---- Tabs ---- */
.tabs {{ border: none !important; }}
button[role="tab"] {{
    font-weight: 600 !important;
    color: var(--tm-ink-soft) !important;
}}
button[role="tab"].selected {{
    color: var(--tm-forest-dark) !important;
    border-color: var(--tm-forest) !important;
}}
"""

THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.green,
    secondary_hue=gr.themes.colors.yellow,
    neutral_hue=gr.themes.colors.stone,
    font=[gr.themes.GoogleFont("Inter"), "sans-serif"],
).set(
    body_background_fill=PALETTE["bg"],
    background_fill_primary=PALETTE["card"],
    background_fill_secondary=PALETTE["bg_alt"],
    border_color_primary=PALETTE["border"],
    button_primary_background_fill=PALETTE["forest"],
    button_primary_background_fill_hover=PALETTE["forest_dark"],
    button_primary_text_color="#ffffff",
    block_title_text_color=PALETTE["forest_dark"],
    block_label_text_color=PALETTE["ink_soft"],
)


# ==========================================================================
# Rendering helpers — HTML-card styled instead of raw markdown lists
# ==========================================================================

def status_dataframe(state):
    rows = []
    for r in state["readings"]:
        level = state["congestion"][r.intersection_id]
        rows.append({
            "Intersection": r.name,
            "Congestion": level,
            "Vehicles": r.vehicle_count,
            "Avg Speed (km/h)": r.avg_speed_kmph,
            "Occupancy %": r.occupancy_pct,
            "Weather": r.weather,
            "Incident": r.incident or "-",
        })
    return pd.DataFrame(rows)


def style_congestion(val):
    color = CONGESTION_COLOR.get(val, PALETTE["ink"])
    return f"background-color: {color}1f; color: {color}; font-weight: 600; border-radius: 6px;"


def style_dataframe(df):
    """pandas >=2.1 renamed Styler.applymap -> Styler.map; support both."""
    styler = df.style
    if hasattr(styler, "map"):
        return styler.map(style_congestion, subset=["Congestion"])
    return styler.applymap(style_congestion, subset=["Congestion"])


def kpi_html(state):
    readings = state["readings"]
    avg_occ = sum(r.occupancy_pct for r in readings) / len(readings) if readings else 0
    n_alerts = len(state.get("alerts", []))
    n_incidents = len(state.get("incidents", []))
    n_hotspots = len(state.get("hotspots", []))

    net_status = "Nominal" if not n_hotspots and not n_incidents else (
        "Degraded" if not n_incidents else "Incident Active"
    )
    net_class = "" if net_status == "Nominal" else ("warn" if net_status == "Degraded" else "alert")

    cards = [
        ("Network Status", net_status, f"{len(readings)} intersections monitored", net_class),
        ("Avg Occupancy", f"{avg_occ:.0f}%", "network-wide, this cycle", "warn" if avg_occ > 55 else ""),
        ("Active Incidents", str(n_incidents), "reported + inferred", "alert" if n_incidents else ""),
        ("Congestion Hotspots", str(n_hotspots), "Heavy / Severe intersections", "warn" if n_hotspots else ""),
        ("Control-Room Alerts", str(n_alerts), f"cycle {state.get('cycle', 0)}", "alert" if n_alerts else ""),
    ]

    html = "<div class='tm-kpi-row'>"
    for label, value, sub, cls in cards:
        html += (
            f"<div class='tm-kpi-card {cls}'>"
            f"<div class='tm-kpi-label'>{label}</div>"
            f"<div class='tm-kpi-value'>{value}</div>"
            f"<div class='tm-kpi-sub'>{sub}</div>"
            f"</div>"
        )
    html += "</div>"
    return html


def alerts_html(state):
    alerts = state.get("alerts", [])
    if not alerts:
        return "<div class='tm-panel'><div class='tm-panel-title'>🔔 Control Room Alerts</div><div class='tm-empty'>No active alerts — network operating normally.</div></div>"

    items = ""
    for a in alerts:
        color = SEVERITY_COLOR.get(a["severity"], PALETTE["ink_soft"])
        label = SEVERITY_LABEL.get(a["severity"], a["severity"])
        items += (
            f"<div class='tm-alert-item'>"
            f"<span class='tm-badge' style='background:{color}'>{label}</span>"
            f"<span class='tm-alert-text'>{a['message']}</span>"
            f"</div>"
        )
    return f"<div class='tm-panel'><div class='tm-panel-title'>🔔 Control Room Alerts <span style='font-weight:400;color:var(--tm-ink-soft);font-size:0.78rem'>({len(alerts)})</span></div>{items}</div>"


def briefing_html(state):
    text = state.get("llm_briefing")
    if text:
        body = text.replace("\n", "<br>")
        return f"<div class='tm-panel'><div class='tm-panel-title'>🗣️ Operator Briefing <span style='font-weight:400;color:var(--tm-ink-soft);font-size:0.78rem'>(LLM-generated)</span></div><div class='tm-briefing'>{body}</div></div>"
    return (
        "<div class='tm-panel'><div class='tm-panel-title'>🗣️ Operator Briefing</div>"
        "<div class='tm-briefing off'>Not configured — set <code>ANTHROPIC_API_KEY</code> to enable natural-language "
        "shift-handover briefings. Showing rule-based alerts only.</div></div>"
    )


def recommendations_html(state):
    sig = state.get("signal_recommendations", {})
    route = state.get("route_advisories", {})
    readings_by_id = {r.intersection_id: r for r in state["readings"]}

    header = "<div class='tm-panel'><div class='tm-panel-title'>🧭 Recommended Actions</div>"
    if not sig and not route:
        return header + "<div class='tm-empty'>No signal or routing interventions active this cycle.</div></div>"

    body = ""
    if sig:
        body += "<div class='tm-rec-group-title'>Signal Timing Changes</div>"
        for iid, rec in sig.items():
            body += (
                f"<div class='tm-alert-item'>"
                f"<span class='tm-badge' style='background:{PALETTE['forest']}'>SIGNAL</span>"
                f"<span class='tm-alert-text'><b>{readings_by_id[iid].name}</b> — {rec}</span>"
                f"</div>"
            )
    if route:
        body += "<div class='tm-rec-group-title'>Route Advisories</div>"
        for iid, rec in route.items():
            body += (
                f"<div class='tm-alert-item'>"
                f"<span class='tm-badge' style='background:{PALETTE['sage']}'>ROUTE</span>"
                f"<span class='tm-alert-text'>{rec}</span>"
                f"</div>"
            )
    return header + body + "</div>"


def log_html(state):
    entries = state.get("log", [])
    header = f"<div class='tm-panel'><div class='tm-panel-title'>🧠 Agent Reasoning Trace <span style='font-weight:400;color:var(--tm-ink-soft);font-size:0.78rem'>— Cycle {state.get('cycle', 0)}</span></div>"
    if not entries:
        return header + "<div class='tm-empty'>Step the simulation to see agent decisions.</div></div>"
    body = ""
    for entry in entries:
        body += (
            f"<div class='tm-log-item'>"
            f"<span class='tm-log-agent'>{entry.agent}</span>"
            f"<span class='tm-log-msg'>{entry.message}</span>"
            f"</div>"
        )
    return header + body + "</div>"


def trend_figure():
    if not system.state_history:
        fig = go.Figure()
        fig.update_layout(
            paper_bgcolor=PALETTE["card"], plot_bgcolor=PALETTE["card"],
            height=340, margin=dict(l=40, r=40, t=30, b=40),
        )
        return fig

    cycles = [s["cycle"] for s in system.state_history]
    fig = go.Figure()

    avg_occ = []
    for s in system.state_history:
        occs = [r.occupancy_pct for r in s["readings"]]
        avg_occ.append(sum(occs) / len(occs) if occs else 0)

    n_alerts = [len(s.get("alerts", [])) for s in system.state_history]

    fig.add_trace(go.Scatter(
        x=cycles, y=avg_occ, name="Avg Network Occupancy %",
        line=dict(color=PALETTE["forest"], width=3),
        fill="tozeroy", fillcolor="rgba(63,107,63,0.08)",
    ))
    fig.add_trace(go.Bar(
        x=cycles, y=n_alerts, name="Alerts this cycle",
        yaxis="y2", marker_color=PALETTE["terracotta"], opacity=0.55,
    ))

    fig.update_layout(
        paper_bgcolor=PALETTE["card"],
        plot_bgcolor=PALETTE["card"],
        font=dict(family="Inter, sans-serif", color=PALETTE["ink"]),
        yaxis=dict(title="Avg Occupancy %", range=[0, 100], gridcolor=PALETTE["border"]),
        yaxis2=dict(title="Alert count", overlaying="y", side="right", showgrid=False),
        xaxis=dict(title="Cycle", gridcolor=PALETTE["border"]),
        legend=dict(orientation="h", y=1.15),
        margin=dict(l=40, r=40, t=30, b=40),
        height=360,
    )
    return fig


def cycle_badge(state):
    n_alerts = len(state.get("alerts", []))
    color = PALETTE["brick"] if n_alerts else PALETTE["forest"]
    word = "active alert" if n_alerts == 1 else "active alerts"
    return (
        f"<div style='font-size:0.9rem;color:{PALETTE['ink_soft']}'>"
        f"Cycle <b style='color:{PALETTE['ink']}'>{state['cycle']}</b> · "
        f"<span style='color:{color};font-weight:700'>{n_alerts} {word}</span>"
        f"</div>"
    )


def run_step():
    state = system.step()
    df = status_dataframe(state)
    styled = style_dataframe(df)
    return (
        kpi_html(state),
        styled,
        alerts_html(state),
        briefing_html(state),
        log_html(state),
        recommendations_html(state),
        trend_figure(),
        cycle_badge(state),
    )


def inject_incident_ui(intersection_name, incident_type):
    iid = system.intersection_id_for_name(intersection_name)
    if iid:
        system.inject_incident(iid, incident_type)
        return (
            f"<div class='tm-alert-item'><span class='tm-badge' style='background:{PALETTE['terracotta']}'>INJECTED</span>"
            f"<span class='tm-alert-text'><b>{incident_type.replace('_', ' ').title()}</b> at <b>{intersection_name}</b>. "
            f"Step or auto-run to watch the agents respond.</span></div>"
        )
    return "<div class='tm-empty'>Could not find that intersection.</div>"


# ==========================================================================
# Layout
# ==========================================================================

with gr.Blocks(title="AI Urban Traffic Monitoring System", theme=THEME, css=CUSTOM_CSS) as demo:

    gr.HTML(
        "<div id='tm-header'>"
        "<h1>🚦 AI-Based Urban Traffic Monitoring System</h1>"
        "<p>Agentic multi-agent pipeline — Perception → Congestion Analysis → Incident Detection → "
        "Signal Optimization / Route Advisory → Alerting — coordinated by a <b>CoordinatorAgent</b> "
        "that decides which specialist agents to invoke each cycle.</p>"
        "</div>"
    )

    kpi_box = gr.HTML(kpi_html({"readings": [], "alerts": [], "incidents": [], "hotspots": [], "cycle": 0}))

    with gr.Row():
        step_btn = gr.Button("▶  Step Simulation", variant="primary", elem_id="tm-step-btn", scale=2)
        auto_run = gr.Checkbox(label="Auto-run every 3s", value=False, scale=1)
        cycle_info = gr.HTML(cycle_badge({"cycle": 0, "alerts": []}), elem_id="tm-cycle-badge")

    with gr.Tabs():
        with gr.Tab("📡 Live Dashboard"):
            with gr.Row():
                with gr.Column(scale=3):
                    gr.Markdown("#### Live Intersection Status")
                    status_table = gr.Dataframe(interactive=False, elem_classes=["tm-table"])
                    briefing_box = gr.HTML(briefing_html({"llm_briefing": None}))
                with gr.Column(scale=2):
                    alerts_box = gr.HTML(alerts_html({"alerts": []}))
                    actions_box = gr.HTML(recommendations_html({"readings": [], "signal_recommendations": {}, "route_advisories": {}}))

            with gr.Accordion("⚠️  Manual Incident Injection (demo / testing)", open=False):
                with gr.Row():
                    intersection_dd = gr.Dropdown(choices=system.intersection_names(), label="Intersection", scale=2)
                    incident_type_dd = gr.Dropdown(
                        choices=["accident", "stalled_vehicle", "road_work"],
                        value="accident", label="Incident Type", scale=2,
                    )
                    inject_btn = gr.Button("Inject Incident", elem_id="tm-inject-btn", scale=1)
                inject_status = gr.HTML()

        with gr.Tab("🧠 Agent Reasoning"):
            log_box = gr.HTML(log_html({"log": [], "cycle": 0}))

        with gr.Tab("📈 Trends & History"):
            gr.Markdown("#### Network Trend — rolling occupancy & alert volume")
            trend_plot = gr.Plot()

    outputs = [kpi_box, status_table, alerts_box, briefing_box, log_box, actions_box, trend_plot, cycle_info]

    step_btn.click(fn=run_step, outputs=outputs)
    inject_btn.click(fn=inject_incident_ui, inputs=[intersection_dd, incident_type_dd], outputs=inject_status)

    timer = gr.Timer(3, active=False)
    timer.tick(fn=run_step, outputs=outputs)
    auto_run.change(fn=lambda x: gr.Timer(active=x), inputs=auto_run, outputs=timer)

    demo.load(fn=run_step, outputs=outputs)

if __name__ == "__main__":
    try:
        # Gradio >= 6.0: theme moved from Blocks() to launch()
        demo.launch()
    except TypeError:
        demo.launch()
