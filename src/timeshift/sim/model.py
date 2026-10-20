"""Immutable mission-state model for the TIME//SHIFT lunar-base simulation.

This is an illustrative discrete-time model, not a validated aerospace digital twin.
Every quantity carries an explicit unit in its name. All state objects are frozen
dataclasses; transitions build new objects instead of mutating existing ones, so a
forked branch can never write back into the canonical mission state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any

SIM_VERSION = "timeshift-sim/1.0.0"

# One tick is five simulated minutes.
TICK_MINUTES = 5
TICK_HOURS = TICK_MINUTES / 60.0


class ModuleStatus(str, Enum):
    NOMINAL = "nominal"
    DAMAGED = "damaged"      # degraded function, no atmosphere loss
    BREACHED = "breached"    # leaking atmosphere
    ISOLATED = "isolated"    # sealed off: no leak, no function, crew evacuated
    DESTROYED = "destroyed"  # terminal


@dataclass(frozen=True)
class Module:
    module_id: str
    name: str
    status: ModuleStatus
    integrity_pct: float          # 0..100
    powered: bool
    load_kw: float                # electrical demand when powered
    critical: bool                # life-critical: shedding it is restricted


@dataclass(frozen=True)
class CrewMember:
    crew_id: str
    name: str
    location: str                 # module_id
    health_pct: float             # 0..100; 0 means deceased
    on_eva: bool = False

    @property
    def alive(self) -> bool:
        return self.health_pct > 0.0


@dataclass(frozen=True)
class RepairJob:
    """An in-progress EVA repair. Completes when ticks_remaining reaches 0."""

    module_id: str
    crew_id: str
    ticks_remaining: int
    integrity_gain_pct: float


@dataclass(frozen=True)
class MissionState:
    mission_id: str
    scenario_id: str
    seed: int
    tick: int
    revision: int                       # bumps on every committed action
    oxygen_reserve_kg: float
    oxygen_capacity_kg: float
    power_reserve_kwh: float
    power_capacity_kwh: float
    solar_peak_kw: float
    reactor_output_kw: float
    reactor_temp_c: float
    reactor_heat_rate_c_per_tick: float  # net heating when pumps are unpowered/degraded
    reactor_online: bool
    coolant_vents_remaining: int
    vent_cooldown_ticks: int            # reactor output halved while > 0
    backup_charge_kwh: float
    backup_active: bool
    backup_output_kw: float
    repair_kits: int
    leak_rate_kg_per_tick_at_zero_integrity: float
    modules: tuple[Module, ...]
    crew: tuple[CrewMember, ...]
    repairs: tuple[RepairJob, ...] = ()
    incident_log: tuple[str, ...] = field(default_factory=tuple)
    sim_version: str = SIM_VERSION

    # ---- lookups ---------------------------------------------------------

    def module(self, module_id: str) -> Module | None:
        for m in self.modules:
            if m.module_id == module_id:
                return m
        return None

    def module_ids(self) -> list[str]:
        return [m.module_id for m in self.modules]

    def crew_member(self, crew_id: str) -> CrewMember | None:
        for c in self.crew:
            if c.crew_id == crew_id:
                return c
        return None

    def alive_crew(self) -> list[CrewMember]:
        return [c for c in self.crew if c.alive]

    # ---- functional replacement -----------------------------------------

    def with_module(self, module: Module) -> MissionState:
        mods = tuple(module if m.module_id == module.module_id else m for m in self.modules)
        return replace(self, modules=mods)

    def with_crew_member(self, member: CrewMember) -> MissionState:
        crew = tuple(member if c.crew_id == member.crew_id else c for c in self.crew)
        return replace(self, crew=crew)

    def log(self, message: str) -> MissionState:
        return replace(self, incident_log=(*self.incident_log, f"T+{self.tick:03d} {message}"))

    # ---- serialization ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for m in d["modules"]:
            m["status"] = m["status"].value if isinstance(m["status"], Enum) else m["status"]
        return d

    def state_hash(self) -> str:
        """Stable SHA-256 over the physical state (incident log excluded)."""
        d = self.to_dict()
        d.pop("incident_log", None)
        blob = json.dumps(d, sort_keys=True, separators=(",", ":"), default=_round_float)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _round_float(value: Any) -> Any:  # pragma: no cover - json fallback
    return str(value)
