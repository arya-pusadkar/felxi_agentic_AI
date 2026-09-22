# AI-Based Urban Traffic Monitoring System (Agentic AI + Gradio)

A multi-agent traffic monitoring dashboard. Specialized agents perceive,
analyze, and act on live (simulated) intersection data, coordinated by a
`CoordinatorAgent` that decides which agents to run each cycle based on
what it observes — not a fixed static pipeline.

## Architecture

```
traffic_simulator.py   Synthetic sensor/camera feed data per intersection
                        (swap this out for real IoT/CCTV/GPS feeds later)

agents.py               PerceptionAgent          -> ingest raw readings
                         CongestionAnalysisAgent  -> classify congestion levels
                         IncidentDetectionAgent   -> flag reported + inferred incidents
                         SignalOptimizationAgent  -> recommend signal-timing changes
                         RouteAdvisoryAgent       -> suggest driver reroutes
                         AlertAgent               -> compile control-room alerts
                         CoordinatorAgent         -> decides which agents run each
                                                      cycle ("agentic" branching)

llm_agent.py             Optional: uses the Claude API to turn a cycle's
                          findings into a natural-language operator briefing.
                          Fully optional — system works without it.

orchestrator.py          Wires the simulator + CoordinatorAgent together,
                          keeps rolling history for charts/logs.

app.py                   Gradio dashboard (entry point).
```

### Why this is "agentic"

Each agent:
1. **Perceives** a slice of state (readings, congestion levels, etc.)
2. **Reasons** about it against thresholds / inferred anomalies
3. **Acts** by writing decisions back to a shared state ("blackboard")
4. **Logs** a human-readable justification for what it did

The `CoordinatorAgent` doesn't just run every agent every cycle — it
inspects what `PerceptionAgent`/`CongestionAnalysisAgent` found and only
invokes `SignalOptimizationAgent`/`RouteAdvisoryAgent` when there's
actually a hotspot or incident to respond to. That conditional,
state-dependent invocation is the core "agentic" behavior, and it's fully
visible in the "Agent Reasoning Trace" panel in the UI.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open the local URL Gradio prints (usually `http://127.0.0.1:7860`).

## Using the dashboard

- **▶ Step Simulation** — advance one monitoring cycle manually
- **Auto-run** — steps automatically every 3 seconds
- **Live Intersection Status** — table color-coded by congestion level
- **Network Trend** — rolling chart of average occupancy % and alert counts
- **Control Room Alerts** — severity-tagged alerts from `AlertAgent`
- **Recommended Actions** — signal-timing and rerouting suggestions
- **Operator Briefing** — natural-language summary (LLM-powered if configured)
- **Agent Reasoning Trace** — full log of what each agent perceived/decided
- **Manual Incident Injection** — force an accident/stall/road-work at a
  chosen intersection to watch the agents respond in real time

## Enabling the LLM-powered operator briefing (optional)

By default `llm_agent.py` is inactive and the system runs entirely on
rule-based logic. To enable Claude-generated natural-language briefings:

```bash
export ANTHROPIC_API_KEY="your-key-here"
python app.py
```

When incidents or hotspots are present, the `AlertAgent` will call the
Claude API to phrase a short shift-handover style briefing from the
structured findings. If the key isn't set, or the call fails, the system
falls back to the rule-based alert list with no interruption.

## Extending to real data

Replace `TrafficSimulator.step()` in `traffic_simulator.py` with real
integrations, keeping the same `IntersectionReading` fields:

- IoT inductive loop sensors → `vehicle_count`, `occupancy_pct`
- CCTV + computer vision (e.g. YOLO vehicle/pedestrian counting) → `vehicle_count`, `pedestrian_count`
- GPS probe / floating car data → `avg_speed_kmph`
- Weather API → `weather`
- 911/road-authority incident feed → `incident`

No other file needs to change — every downstream agent consumes the same
`IntersectionReading` contract.

## Customizing thresholds & agents

- Congestion thresholds: `CONGESTION_THRESHOLDS` in `agents.py`
- Add a new agent: subclass `BaseAgent`, implement `run(state, ...)`,
  wire it into `CoordinatorAgent.run_cycle()` in `agents.py`
- Add a new intersection: extend the list passed to `TrafficSimulator`
  in `orchestrator.py`
