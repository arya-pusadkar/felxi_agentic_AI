"""
traffic_simulator.py
---------------------
Simulates real-time traffic sensor / camera feed data for a set of urban
intersections. In a production system this module would be replaced with
real integrations (IoT loop sensors, CCTV + computer vision counts, GPS
probe data, etc.). The rest of the system (agents, orchestrator, UI) is
written against this same data contract, so swapping in real feeds later
only requires rewriting this one file.
"""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class IntersectionReading:
    intersection_id: str
    name: str
    timestamp: str
    vehicle_count: int          # vehicles observed in last cycle
    avg_speed_kmph: float        # average vehicle speed
    occupancy_pct: float         # % of road segment occupied by vehicles
    pedestrian_count: int
    weather: str
    incident: Optional[str] = None   # e.g. "accident", "stalled_vehicle", None


class TrafficSimulator:
    """Generates evolving synthetic traffic conditions for a fixed set of
    intersections, with a small probability of injecting incidents so the
    agent pipeline has something interesting to react to."""

    WEATHER_OPTIONS = ["clear", "rain", "fog", "heavy_rain"]

    def __init__(self, intersections: Optional[list] = None, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)

        self.intersections = intersections or [
            {"id": "INT-01", "name": "MG Road & 5th Ave"},
            {"id": "INT-02", "name": "Ring Road Junction"},
            {"id": "INT-03", "name": "Station Road Crossing"},
            {"id": "INT-04", "name": "Airport Highway Entrance"},
            {"id": "INT-05", "name": "Market Square"},
        ]

        # per-intersection running baseline so values drift smoothly
        # instead of jumping randomly every cycle
        self._baseline = {
            i["id"]: {
                "vehicle_count": random.randint(20, 60),
                "avg_speed_kmph": random.uniform(25, 45),
                "occupancy_pct": random.uniform(10, 40),
            }
            for i in self.intersections
        }
        self._active_incidents = {}   # intersection_id -> incident type
        self._weather = random.choice(self.WEATHER_OPTIONS)

    def _drift(self, value, lo, hi, step):
        value += random.uniform(-step, step)
        return max(lo, min(hi, value))

    def maybe_change_weather(self, p=0.05):
        if random.random() < p:
            self._weather = random.choice(self.WEATHER_OPTIONS)

    def inject_incident(self, intersection_id: str, incident_type: str = "accident"):
        """Manually trigger an incident at a given intersection (used by the
        UI 'Simulate Incident' button, and by automated demo/testing)."""
        self._active_incidents[intersection_id] = incident_type

    def clear_incident(self, intersection_id: str):
        self._active_incidents.pop(intersection_id, None)

    def step(self) -> list:
        """Advance the simulation by one cycle and return a fresh reading
        for every intersection."""
        self.maybe_change_weather()
        weather_penalty = {
            "clear": 1.0, "rain": 0.85, "fog": 0.75, "heavy_rain": 0.6
        }[self._weather]

        readings = []
        now = datetime.now().isoformat(timespec="seconds")

        for intr in self.intersections:
            iid = intr["id"]
            base = self._baseline[iid]

            # small random chance of a spontaneous incident if none active
            if iid not in self._active_incidents and random.random() < 0.02:
                self._active_incidents[iid] = random.choice(
                    ["accident", "stalled_vehicle", "road_work"]
                )

            base["vehicle_count"] = self._drift(base["vehicle_count"], 5, 150, 6)
            base["occupancy_pct"] = self._drift(base["occupancy_pct"], 5, 98, 4)

            speed = self._drift(base["avg_speed_kmph"], 3, 60, 4) * weather_penalty
            incident = self._active_incidents.get(iid)

            if incident:
                # incidents choke throughput and speed sharply
                speed *= 0.35
                base["occupancy_pct"] = min(98, base["occupancy_pct"] * 1.6)

            base["avg_speed_kmph"] = speed

            readings.append(
                IntersectionReading(
                    intersection_id=iid,
                    name=intr["name"],
                    timestamp=now,
                    vehicle_count=int(base["vehicle_count"]),
                    avg_speed_kmph=round(base["avg_speed_kmph"], 1),
                    occupancy_pct=round(base["occupancy_pct"], 1),
                    pedestrian_count=random.randint(0, 40),
                    weather=self._weather,
                    incident=incident,
                )
            )

            # incidents auto-clear after a few cycles, at random
            if incident and random.random() < 0.15:
                self.clear_incident(iid)

        return readings
