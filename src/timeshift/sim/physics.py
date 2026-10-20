"""Pure discrete-time transition function: MissionState -> MissionState.

Assumptions (illustrative, documented in docs/SIMULATION.md):
- One tick = 5 minutes. Lunar day: solar output is constant across a mission horizon.
- Each crew member consumes 0.035 kg O2 per hour (~0.84 kg/day).
- The oxygen generator in LIFE_SUPPORT produces 0.25 kg O2/hour when powered and intact.
- A BREACHED module loses oxygen in proportion to (100 - integrity) unless isolated.
- The reactor cooling pumps are part of the REACTOR module load. If the REACTOR module is
  unpowered or DAMAGED, the core heats by `reactor_heat_rate_c_per_tick`; otherwise it relaxes
  toward 600 C. At >= 900 C the reactor auto-SCRAMs (output -> 0). At >= 1100 C it is destroyed.
- When the power reserve is exhausted, non-critical modules shed first, then critical ones.
- Crew health falls when the oxygen reserve is below 15 % of capacity, when the module they are
  in is breached, or when they are in REACTOR above 1000 C.

A per-(seed, tick) RNG adds bounded jitter to the leak rate so different seeds give
different but fully reproducible trajectories.
"""

from __future__ import annotations

import random
from dataclasses import replace

from .model import TICK_HOURS, CrewMember, MissionState, ModuleStatus

O2_PER_CREW_KG_H = 0.035
O2_GENERATION_KG_H = 0.25
REACTOR_RELAX_TARGET_C = 600.0
REACTOR_RELAX_C_PER_TICK = 6.0
REACTOR_SCRAM_C = 900.0
REACTOR_DESTROY_C = 1100.0
REACTOR_RADIATION_C = 1000.0
LOW_O2_FRACTION = 0.15
LEAK_JITTER = 0.10  # +/- 10 %


def tick_rng(seed: int, tick: int) -> random.Random:
    """Independent RNG stream per (seed, tick) so branches replay identically."""
    return random.Random(seed * 1_000_003 + tick)


def generation_kw(s: MissionState) -> float:
    solar = s.module("SOLAR")
    solar_kw = 0.0
    if solar and solar.status not in (ModuleStatus.ISOLATED, ModuleStatus.DESTROYED):
        solar_kw = s.solar_peak_kw * solar.integrity_pct / 100.0
    reactor_kw = 0.0
    if s.reactor_online:
        reactor_kw = s.reactor_output_kw * (0.5 if s.vent_cooldown_ticks > 0 else 1.0)
    backup_kw = s.backup_output_kw if (s.backup_active and s.backup_charge_kwh > 0) else 0.0
    return solar_kw + reactor_kw + backup_kw


def load_kw(s: MissionState) -> float:
    return sum(m.load_kw for m in s.modules if m.powered)


def step(s: MissionState) -> MissionState:
    """Advance one tick. Pure: never mutates its input."""
    rng = tick_rng(s.seed, s.tick)
    s = replace(s, tick=s.tick + 1)

    # ---- power -----------------------------------------------------------
    gen = generation_kw(s)
    backup_used_kwh = 0.0
    if s.backup_active and s.backup_charge_kwh > 0:
        backup_used_kwh = min(s.backup_charge_kwh, s.backup_output_kw * TICK_HOURS)
    net_kwh = (gen - load_kw(s)) * TICK_HOURS
    reserve = min(s.power_capacity_kwh, s.power_reserve_kwh + net_kwh)
    s = replace(s, backup_charge_kwh=round(s.backup_charge_kwh - backup_used_kwh, 6))
    if s.backup_active and s.backup_charge_kwh <= 0:
        s = replace(s, backup_active=False, backup_charge_kwh=0.0).log("Backup bank depleted")
    if reserve <= 0:
        reserve = 0.0
        s = _shed_load(s)
    s = replace(s, power_reserve_kwh=round(reserve, 6))

    # ---- oxygen ----------------------------------------------------------
    o2 = s.oxygen_reserve_kg
    alive_in_base = [c for c in s.crew if c.alive and not c.on_eva]
    o2 -= len(alive_in_base) * O2_PER_CREW_KG_H * TICK_HOURS
    ls = s.module("LIFE_SUPPORT")
    if ls and ls.powered and ls.status in (ModuleStatus.NOMINAL, ModuleStatus.DAMAGED):
        efficiency = 1.0 if ls.status == ModuleStatus.NOMINAL else 0.5
        o2 += O2_GENERATION_KG_H * efficiency * TICK_HOURS
    jitter = 1.0 + rng.uniform(-LEAK_JITTER, LEAK_JITTER)
    for m in s.modules:
        if m.status == ModuleStatus.BREACHED:
            o2 -= s.leak_rate_kg_per_tick_at_zero_integrity * (100 - m.integrity_pct) / 100 * jitter
    s = replace(s, oxygen_reserve_kg=round(max(0.0, min(s.oxygen_capacity_kg, o2)), 6))

    # ---- reactor ---------------------------------------------------------
    s = _reactor_step(s)

    # ---- repairs ---------------------------------------------------------
    s = _repair_step(s)

    # ---- crew ------------------------------------------------------------
    s = _crew_step(s)
    return s


def _shed_load(s: MissionState) -> MissionState:
    """Brownout: drop non-critical loads first, then critical loads, largest first."""
    gen = generation_kw(s)
    order = sorted(
        (m for m in s.modules if m.powered),
        key=lambda m: (m.critical, -m.load_kw),
    )
    for m in order:
        if load_kw(s) <= gen:
            break
        s = s.with_module(replace(m, powered=False)).log(f"Brownout: {m.module_id} shed")
    return s


def _reactor_step(s: MissionState) -> MissionState:
    reactor = s.module("REACTOR")
    if reactor is None or reactor.status == ModuleStatus.DESTROYED:
        return s
    cooling_ok = reactor.powered and reactor.status == ModuleStatus.NOMINAL
    temp = s.reactor_temp_c
    if not s.reactor_online:
        temp = max(REACTOR_RELAX_TARGET_C - 300, temp - REACTOR_RELAX_C_PER_TICK * 2)
    elif cooling_ok:
        temp = max(REACTOR_RELAX_TARGET_C, temp - REACTOR_RELAX_C_PER_TICK)
    else:
        temp += s.reactor_heat_rate_c_per_tick
    s = replace(s, reactor_temp_c=round(temp, 6),
                vent_cooldown_ticks=max(0, s.vent_cooldown_ticks - 1))
    if s.reactor_online and temp >= REACTOR_SCRAM_C:
        s = replace(s, reactor_online=False).log(
            f"Reactor auto-SCRAM at {temp:.0f} C: output lost")
    if temp >= REACTOR_DESTROY_C:
        s = s.with_module(replace(reactor, status=ModuleStatus.DESTROYED, powered=False,
                                  integrity_pct=0.0))
        s = replace(s, reactor_online=False).log("Reactor core failure: module destroyed")
    return s


def _repair_step(s: MissionState) -> MissionState:
    remaining = []
    for job in s.repairs:
        job = replace(job, ticks_remaining=job.ticks_remaining - 1)
        if job.ticks_remaining > 0:
            remaining.append(job)
            continue
        m = s.module(job.module_id)
        if m is not None and m.status != ModuleStatus.DESTROYED:
            integrity = min(100.0, m.integrity_pct + job.integrity_gain_pct)
            status = ModuleStatus.NOMINAL if integrity >= 80 else m.status
            s = s.with_module(replace(m, integrity_pct=integrity, status=status))
        member = s.crew_member(job.crew_id)
        if member is not None:
            s = s.with_crew_member(replace(member, on_eva=False, location="HAB"))
        s = s.log(f"Repair of {job.module_id} complete (+{job.integrity_gain_pct:.0f}% integrity)")
    return replace(s, repairs=tuple(remaining))


def _crew_step(s: MissionState) -> MissionState:
    low_o2 = s.oxygen_reserve_kg < LOW_O2_FRACTION * s.oxygen_capacity_kg
    for c in s.crew:
        if not c.alive:
            continue
        damage = 0.0
        if low_o2 and not c.on_eva:
            damage += 4.0 if s.oxygen_reserve_kg > 0 else 15.0
        here = s.module(c.location)
        if here is not None and not c.on_eva:
            if here.status == ModuleStatus.BREACHED:
                damage += 2.0
            if here.status == ModuleStatus.DESTROYED:
                damage += 100.0
            if here.module_id == "REACTOR" and s.reactor_temp_c >= REACTOR_RADIATION_C:
                damage += 10.0
        if damage:
            health = max(0.0, c.health_pct - damage)
            updated: CrewMember = replace(c, health_pct=health)
            s = s.with_crew_member(updated)
            if health == 0.0:
                s = s.log(f"Crew member {c.name} lost")
    return s


def simulate(s: MissionState, ticks: int) -> list[MissionState]:
    """Return the trajectory [s1, ..., s_ticks] (excluding the input state)."""
    out: list[MissionState] = []
    for _ in range(ticks):
        s = step(s)
        out.append(s)
    return out
