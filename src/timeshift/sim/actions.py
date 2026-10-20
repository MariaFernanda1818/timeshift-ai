"""Mission actions: explicit preconditions, resource costs and pure apply functions.

`validate_action` never raises; it returns a list of human-readable violations.
`apply_action` assumes validation passed and returns a new state (pure).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .model import MissionState, ModuleStatus, RepairJob

VENT_TEMP_DROP_C = 160.0
VENT_COOLDOWN_TICKS = 6
REPAIR_TICKS = 8
REPAIR_GAIN_PCT = 55.0
EVA_O2_COST_KG = 0.6
NON_ISOLATABLE = frozenset({"LIFE_SUPPORT"})
RELOCATION_TARGETS = ("HAB", "LAB", "GREENHOUSE")


@dataclass(frozen=True)
class Action:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        items = ",".join(f"{k}={self.args[k]}" for k in sorted(self.args))
        return f"{self.tool}({items})"


ACTION_SCHEMAS: dict[str, dict[str, type]] = {
    "isolate_module": {"module_id": str},
    "activate_backup_power": {},
    "reroute_power": {"source_module": str, "target_module": str},
    "vent_reactor": {},
    "repair_solar_array": {"crew_id": str},
}

ACTION_DESCRIPTIONS: dict[str, str] = {
    "isolate_module": (
        "Seal a module: stops any atmosphere leak and removes its electrical load, but the module "
        "stops functioning and its crew relocate. LIFE_SUPPORT cannot be isolated."
    ),
    "activate_backup_power": (
        "Bring the battery backup bank online, adding its output until its charge is depleted."
    ),
    "reroute_power": (
        "Cut power to source_module and energise target_module (e.g. restore reactor coolant "
        "pumps by shedding the lab)."
    ),
    "vent_reactor": (
        f"Emergency coolant vent: reactor temperature drops {VENT_TEMP_DROP_C:.0f} C at once, "
        f"reactor output is halved for {VENT_COOLDOWN_TICKS} ticks, consumes one vent charge. "
        "Unsafe while crew are inside REACTOR."
    ),
    "repair_solar_array": (
        f"Send one healthy crew member on an {REPAIR_TICKS}-tick EVA to repair SOLAR "
        f"(+{REPAIR_GAIN_PCT:.0f}% integrity). Consumes one repair kit and "
        f"{EVA_O2_COST_KG} kg O2."
    ),
}


def validate_schema(action: Action) -> list[str]:
    schema = ACTION_SCHEMAS.get(action.tool)
    if schema is None:
        return [f"unknown tool '{action.tool}' (allowed: {', '.join(sorted(ACTION_SCHEMAS))})"]
    errors = []
    for name, typ in schema.items():
        if name not in action.args:
            errors.append(f"missing argument '{name}'")
        elif not isinstance(action.args[name], typ):
            errors.append(f"argument '{name}' must be {typ.__name__}")
    for name in action.args:
        if name not in schema:
            errors.append(f"unexpected argument '{name}'")
    return errors


def validate_action(s: MissionState, action: Action) -> list[str]:
    """Deterministic preconditions. Empty list means the action is legal in state `s`."""
    errors = validate_schema(action)
    if errors:
        return errors
    a = action.args
    if action.tool == "isolate_module":
        m = s.module(a["module_id"])
        if m is None:
            return [f"module '{a['module_id']}' does not exist (known: {', '.join(s.module_ids())})"]
        if m.module_id in NON_ISOLATABLE:
            errors.append(f"{m.module_id} is life-critical and cannot be isolated")
        if m.status in (ModuleStatus.ISOLATED, ModuleStatus.DESTROYED):
            errors.append(f"{m.module_id} is already {m.status.value}")
        crew_here = [c for c in s.alive_crew() if c.location == m.module_id and not c.on_eva]
        if crew_here and not _relocation_target(s, exclude=m.module_id):
            errors.append("no habitable module available to relocate crew")
    elif action.tool == "activate_backup_power":
        if s.backup_active:
            errors.append("backup bank is already active")
        if s.backup_charge_kwh <= 0:
            errors.append("backup bank has no charge")
    elif action.tool == "reroute_power":
        src, dst = s.module(a["source_module"]), s.module(a["target_module"])
        if src is None:
            errors.append(f"module '{a['source_module']}' does not exist")
        if dst is None:
            errors.append(f"module '{a['target_module']}' does not exist")
        if src is None or dst is None:
            return errors
        if src.module_id == dst.module_id:
            errors.append("source and target must differ")
        if src.critical:
            errors.append(f"{src.module_id} is life-critical; its power cannot be shed")
        if not src.powered:
            errors.append(f"{src.module_id} is not powered; nothing to reroute")
        if dst.status in (ModuleStatus.ISOLATED, ModuleStatus.DESTROYED):
            errors.append(f"{dst.module_id} is {dst.status.value} and cannot be energised")
    elif action.tool == "vent_reactor":
        reactor = s.module("REACTOR")
        if reactor is None or reactor.status == ModuleStatus.DESTROYED:
            errors.append("reactor is unavailable")
        if s.coolant_vents_remaining <= 0:
            errors.append("no coolant vent charges remaining")
        if any(c.location == "REACTOR" and c.alive and not c.on_eva for c in s.crew):
            errors.append("crew are inside REACTOR; venting would expose them")
    elif action.tool == "repair_solar_array":
        c = s.crew_member(a["crew_id"])
        solar = s.module("SOLAR")
        if c is None:
            errors.append(f"crew member '{a['crew_id']}' does not exist")
        elif not c.alive or c.health_pct < 60:
            errors.append(f"{c.crew_id} is not fit for EVA (health {c.health_pct:.0f}%)")
        elif c.on_eva:
            errors.append(f"{c.crew_id} is already on EVA")
        if solar is None or solar.status == ModuleStatus.DESTROYED:
            errors.append("solar array is unavailable")
        elif solar.integrity_pct >= 95:
            errors.append("solar array does not need repair")
        if s.repair_kits <= 0:
            errors.append("no repair kits remaining")
        if s.oxygen_reserve_kg < EVA_O2_COST_KG:
            errors.append("insufficient oxygen for EVA")
        if any(j.module_id == "SOLAR" for j in s.repairs):
            errors.append("a solar repair is already in progress")
    return errors


def _relocation_target(s: MissionState, exclude: str) -> str | None:
    for mid in RELOCATION_TARGETS:
        m = s.module(mid)
        if mid != exclude and m and m.status in (ModuleStatus.NOMINAL, ModuleStatus.DAMAGED):
            return mid
    return None


def apply_action(s: MissionState, action: Action) -> MissionState:
    """Apply a validated action. Pure: returns a new state."""
    a = action.args
    if action.tool == "isolate_module":
        m = s.module(a["module_id"])
        assert m is not None
        s = s.with_module(replace(m, status=ModuleStatus.ISOLATED, powered=False))
        target = _relocation_target(s, exclude=m.module_id)
        for c in s.crew:
            if c.location == m.module_id and not c.on_eva and target:
                s = s.with_crew_member(replace(c, location=target))
        if m.module_id == "REACTOR":
            s = replace(s, reactor_online=False)
        return s.log(f"ACTION isolate_module {m.module_id}")
    if action.tool == "activate_backup_power":
        return replace(s, backup_active=True).log("ACTION activate_backup_power")
    if action.tool == "reroute_power":
        src, dst = s.module(a["source_module"]), s.module(a["target_module"])
        assert src is not None and dst is not None
        s = s.with_module(replace(src, powered=False))
        s = s.with_module(replace(dst, powered=True))
        return s.log(f"ACTION reroute_power {src.module_id} -> {dst.module_id}")
    if action.tool == "vent_reactor":
        return replace(
            s,
            reactor_temp_c=s.reactor_temp_c - VENT_TEMP_DROP_C,
            coolant_vents_remaining=s.coolant_vents_remaining - 1,
            vent_cooldown_ticks=VENT_COOLDOWN_TICKS,
        ).log("ACTION vent_reactor")
    if action.tool == "repair_solar_array":
        c = s.crew_member(a["crew_id"])
        assert c is not None
        s =s.with_crew_member(replace(c, on_eva=True))
        s = replace(
            s,
            repair_kits=s.repair_kits - 1,
            oxygen_reserve_kg=s.oxygen_reserve_kg - EVA_O2_COST_KG,
            repairs=(*s.repairs, RepairJob("SOLAR", c.crew_id, REPAIR_TICKS, REPAIR_GAIN_PCT)),
        )
        return s.log(f"ACTION repair_solar_array crew={c.crew_id}")
    raise ValueError(f"unknown tool {action.tool}")
