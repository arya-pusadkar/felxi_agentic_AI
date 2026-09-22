"""
orchestrator.py
----------------
Ties the TrafficSimulator (data source) and CoordinatorAgent (agentic
pipeline) together, and keeps rolling history so the Gradio UI can plot
trends and show a scrolling reasoning log rather than only the latest
snapshot.
"""

from collections import deque
from typing import Dict, Any, List

from traffic_simulator import TrafficSimulator
from agents import CoordinatorAgent


class TrafficMonitoringSystem:
    def __init__(self, history_len: int = 50, seed: int = None):
        self.simulator = TrafficSimulator(seed=seed)
        self.coordinator = CoordinatorAgent()
        self.cycle_count = 0
        self.history_len = history_len

        # rolling history for charts / log panel
        self.state_history: deque = deque(maxlen=history_len)
        self.log_history: deque = deque(maxlen=200)
        self.alert_history: deque = deque(maxlen=100)

    def step(self) -> Dict[str, Any]:
        self.cycle_count += 1
        readings = self.simulator.step()
        state = self.coordinator.run_cycle(readings)
        state["cycle"] = self.cycle_count

        self.state_history.append(state)
        for entry in state["log"]:
            self.log_history.append((self.cycle_count, entry.agent, entry.message))
        for alert in state.get("alerts", []):
            self.alert_history.append((self.cycle_count, alert["severity"], alert["message"]))

        return state

    def inject_incident(self, intersection_id: str, incident_type: str = "accident"):
        self.simulator.inject_incident(intersection_id, incident_type)

    def intersection_names(self) -> List[str]:
        return [i["name"] for i in self.simulator.intersections]

    def intersection_id_for_name(self, name: str) -> str:
        for i in self.simulator.intersections:
            if i["name"] == name:
                return i["id"]
        return None

    def latest_state(self) -> Dict[str, Any]:
        return self.state_history[-1] if self.state_history else None
