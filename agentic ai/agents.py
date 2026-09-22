"""
agents.py
---------
Defines the individual agents that make up the agentic traffic-monitoring
pipeline. Each agent has a single responsibility and exposes a `run()`
method that takes the current world-state dict, updates it, and appends a
human-readable reasoning trace entry describing what it perceived and
decided. This trace is what makes the system "agentic" and inspectable:
every decision is logged with its justification, not just its output.

Agents communicate purely through the shared `state` dict that the
Orchestrator passes down the pipeline (a simple, dependency-free
blackboard architecture) -- no agent needs to know about any other agent.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from traffic_simulator import IntersectionReading

try:
    from llm_agent import explain_with_llm, llm_available
except ImportError:
    llm_available = lambda: False
    explain_with_llm = None


CONGESTION_THRESHOLDS = {
    # occupancy_pct upper bound -> label
    "Free Flow": 30,
    "Moderate": 55,
    "Heavy": 80,
    "Severe": 100,
}


def classify_congestion(occupancy_pct: float) -> str:
    for label, upper in CONGESTION_THRESHOLDS.items():
        if occupancy_pct <= upper:
            return label
    return "Severe"


@dataclass
class AgentLogEntry:
    agent: str
    message: str


class BaseAgent:
    name = "BaseAgent"

    def log(self, state: Dict[str, Any], message: str):
        state.setdefault("log", []).append(
            AgentLogEntry(agent=self.name, message=message)
        )


class PerceptionAgent(BaseAgent):
    """Ingests raw sensor readings into the shared state. In a real
    deployment this is where camera/IoT/GPS feeds would be normalized."""

    name = "PerceptionAgent"

    def run(self, state: Dict[str, Any], readings: List[IntersectionReading]):
        state["readings"] = readings
        n_incidents = sum(1 for r in readings if r.incident)
        self.log(
            state,
            f"Ingested {len(readings)} intersection feeds "
            f"({n_incidents} reporting an active incident).",
        )
        return state


class CongestionAnalysisAgent(BaseAgent):
    """Classifies congestion level per intersection and flags hotspots."""

    name = "CongestionAnalysisAgent"

    def run(self, state: Dict[str, Any]):
        analysis = {}
        hotspots = []
        for r in state["readings"]:
            level = classify_congestion(r.occupancy_pct)
            analysis[r.intersection_id] = level
            if level in ("Heavy", "Severe"):
                hotspots.append((r.intersection_id, r.name, level))

        state["congestion"] = analysis
        state["hotspots"] = hotspots

        if hotspots:
            summary = ", ".join(f"{n} ({l})" for _, n, l in hotspots)
            self.log(state, f"Detected {len(hotspots)} congestion hotspot(s): {summary}.")
        else:
            self.log(state, "No significant congestion detected across the network.")
        return state


class IncidentDetectionAgent(BaseAgent):
    """Looks for active incidents and abnormal speed drops that a sensor
    might not explicitly flag as an 'incident' but that behave like one."""

    name = "IncidentDetectionAgent"

    SPEED_DROP_THRESHOLD_KMPH = 12.0

    def run(self, state: Dict[str, Any]):
        incidents = []
        for r in state["readings"]:
            if r.incident:
                incidents.append(
                    {"id": r.intersection_id, "name": r.name, "type": r.incident,
                     "confidence": "reported"}
                )
            elif r.avg_speed_kmph < self.SPEED_DROP_THRESHOLD_KMPH and r.occupancy_pct > 60:
                # inferred anomaly: heavy occupancy + crawling speed with no
                # reported incident code -> likely unreported obstruction
                incidents.append(
                    {"id": r.intersection_id, "name": r.name,
                     "type": "suspected_obstruction", "confidence": "inferred"}
                )

        state["incidents"] = incidents
        if incidents:
            self.log(
                state,
                f"Flagged {len(incidents)} incident(s): "
                + ", ".join(f"{i['name']} [{i['type']}/{i['confidence']}]" for i in incidents)
                + ".",
            )
        else:
            self.log(state, "No incidents detected this cycle.")
        return state


class SignalOptimizationAgent(BaseAgent):
    """Recommends traffic-signal timing adjustments for congested or
    incident-affected intersections."""

    name = "SignalOptimizationAgent"

    def run(self, state: Dict[str, Any]):
        recommendations = {}
        incident_ids = {i["id"] for i in state.get("incidents", [])}

        for r in state["readings"]:
            level = state["congestion"][r.intersection_id]
            if r.intersection_id in incident_ids:
                recommendations[r.intersection_id] = (
                    "Hold extended green on bypass approach; dispatch signal to "
                    "flashing-caution mode near incident to aid emergency access."
                )
            elif level == "Severe":
                recommendations[r.intersection_id] = (
                    "Extend green phase +25% on highest-volume approach; "
                    "shorten pedestrian cycle where safe."
                )
            elif level == "Heavy":
                recommendations[r.intersection_id] = (
                    "Extend green phase +10-15% on primary approach."
                )
            # Free Flow / Moderate -> no change needed, omitted from dict

        state["signal_recommendations"] = recommendations
        if recommendations:
            self.log(
                state,
                f"Issued signal-timing adjustments for {len(recommendations)} "
                f"intersection(s).",
            )
        else:
            self.log(state, "No signal-timing changes required this cycle.")
        return state


class RouteAdvisoryAgent(BaseAgent):
    """Suggests rerouting for drivers approaching congested/incident zones,
    based on which nearby intersections currently have spare capacity."""

    name = "RouteAdvisoryAgent"

    def run(self, state: Dict[str, Any]):
        readings_by_id = {r.intersection_id: r for r in state["readings"]}
        congestion = state["congestion"]
        problem_ids = {h[0] for h in state["hotspots"]} | {i["id"] for i in state["incidents"]}

        free_alternatives = [
            r.name for r in state["readings"]
            if congestion[r.intersection_id] in ("Free Flow", "Moderate")
            and r.intersection_id not in problem_ids
        ]

        advisories = {}
        for pid in problem_ids:
            name = readings_by_id[pid].name
            if free_alternatives:
                alt = free_alternatives[0]  # simple nearest-available heuristic
                advisories[pid] = f"Advise rerouting away from {name} via {alt}."
            else:
                advisories[pid] = f"No low-congestion alternative currently available near {name}; advise general slowdown warning."

        state["route_advisories"] = advisories
        if advisories:
            self.log(state, f"Prepared {len(advisories)} rerouting advisory message(s) for drivers.")
        else:
            self.log(state, "Network flowing normally; no rerouting advisories needed.")
        return state


class AlertAgent(BaseAgent):
    """Synthesizes everything upstream agents found into human-readable
    alerts for a traffic control room operator, optionally using an LLM to
    phrase a natural-language incident briefing."""

    name = "AlertAgent"

    def run(self, state: Dict[str, Any]):
        alerts = []

        for inc in state.get("incidents", []):
            severity = "HIGH" if inc["confidence"] == "reported" else "MEDIUM"
            alerts.append(
                {
                    "severity": severity,
                    "message": f"[{severity}] {inc['type'].replace('_', ' ').title()} "
                               f"at {inc['name']}.",
                }
            )

        for iid, name, level in state.get("hotspots", []):
            if iid not in {i["id"] for i in state.get("incidents", [])}:
                alerts.append(
                    {"severity": "MEDIUM" if level == "Heavy" else "HIGH",
                     "message": f"[{'HIGH' if level=='Severe' else 'MEDIUM'}] "
                                f"{level} congestion building at {name}."}
                )

        state["alerts"] = alerts

        if llm_available() and (state.get("incidents") or state.get("hotspots")):
            try:
                briefing = explain_with_llm(state)
                state["llm_briefing"] = briefing
                self.log(state, "Generated LLM-based operator briefing.")
            except Exception as e:
                state["llm_briefing"] = None
                self.log(state, f"LLM briefing unavailable ({e}); using rule-based alerts only.")
        else:
            state["llm_briefing"] = None

        self.log(state, f"Compiled {len(alerts)} alert(s) for the control room.")
        return state


class CoordinatorAgent(BaseAgent):
    """The top-level orchestrating agent. It doesn't do domain analysis
    itself -- instead it decides *which* specialist agents to invoke this
    cycle and in what order, based on what perception turned up. This is
    the 'agentic' decision-making layer: the pipeline is not a fixed
    static sequence, it adapts each cycle."""

    name = "CoordinatorAgent"

    def __init__(self):
        self.perception = PerceptionAgent()
        self.congestion = CongestionAnalysisAgent()
        self.incident = IncidentDetectionAgent()
        self.signal = SignalOptimizationAgent()
        self.route = RouteAdvisoryAgent()
        self.alert = AlertAgent()

    def run_cycle(self, readings: List[IntersectionReading]) -> Dict[str, Any]:
        state: Dict[str, Any] = {"log": []}

        self.perception.run(state, readings)
        self.congestion.run(state)
        self.incident.run(state)

        # Agentic branching: only invoke signal optimization / routing when
        # there is actually something worth optimizing for. A pure fixed
        # pipeline would run these unconditionally every cycle; the
        # coordinator instead reasons about necessity first.
        if state["hotspots"] or state["incidents"]:
            self.log(state, "Congestion or incidents present -> invoking "
                             "SignalOptimizationAgent and RouteAdvisoryAgent.")
            self.signal.run(state)
            self.route.run(state)
        else:
            state["signal_recommendations"] = {}
            state["route_advisories"] = {}
            self.log(state, "Network nominal -> skipping signal/routing agents this cycle.")

        self.alert.run(state)
        return state
