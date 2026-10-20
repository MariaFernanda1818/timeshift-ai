"""Evidence: deterministic, ID-addressable observations derived from mission state.

Trusted evidence comes only from simulated sensors (the state itself). Untrusted evidence
comes from scenario reports. Every observation carries the tick and revision it was read
at, which is what makes stale-evidence detection possible.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import MissionState
from .physics import generation_kw, load_kw
from .scenarios import Report


@dataclass(frozen=True)
class Observation:
    evidence_id: str
    tick: int
    revision: int
    source: str
    trusted: bool
    text: str


def observe(s: MissionState, reports: tuple[Report, ...] = ()) -> list[Observation]:
    t, r = s.tick, s.revision

    def ob(key: str, text: str) -> Observation:
        return Observation(f"E{t:03d}-{key}", t, r, "telemetry", True, text)

    out = [
        ob("PWR", f"Power reserve {s.power_reserve_kwh:.1f}/{s.power_capacity_kwh:.0f} kWh; "
                  f"generation {generation_kw(s):.1f} kW vs load {load_kw(s):.1f} kW "
                  f"(net {generation_kw(s) - load_kw(s):+.1f} kW)"),
        ob("O2", f"Oxygen reserve {s.oxygen_reserve_kg:.1f}/{s.oxygen_capacity_kg:.0f} kg"),
        ob("RX", f"Reactor {'online' if s.reactor_online else 'OFFLINE'} at "
                 f"{s.reactor_temp_c:.0f} C (SCRAM 900 C); vents remaining "
                 f"{s.coolant_vents_remaining}"),
        ob("BKP", f"Backup bank {'ACTIVE' if s.backup_active else 'standby'}, "
                  f"{s.backup_charge_kwh:.1f} kWh, {s.backup_output_kw:.0f} kW output"),
        ob("KITS", f"Repair kits available: {s.repair_kits}"),
    ]
    for m in s.modules:
        out.append(ob(
            f"MOD-{m.module_id}",
            f"{m.module_id} status={m.status.value} integrity={m.integrity_pct:.0f}% "
            f"powered={'yes' if m.powered else 'no'} load={m.load_kw:.1f} kW"
            + (" pressure=NOMINAL" if m.status.value in ("nominal", "damaged") else ""),
        ))
    for c in s.crew:
        where = "EVA" if c.on_eva else c.location
        out.append(ob(f"CREW-{c.crew_id}",
                      f"{c.crew_id} {c.name} in {where}, health {c.health_pct:.0f}%"))
    for rep in reports:
        out.append(Observation(rep.report_id, rep.tick, r, rep.source, False, rep.text))
    return out


def render_evidence(obs: list[Observation]) -> str:
    lines = []
    for o in obs:
        trust = "TRUSTED" if o.trusted else "UNVERIFIED"
        lines.append(f"[{o.evidence_id}] ({trust}, {o.source}, tick {o.tick}) {o.text}")
    return "\n".join(lines)
