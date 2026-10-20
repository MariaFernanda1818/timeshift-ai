"""Incident scenarios. Each builds a deterministic initial MissionState plus any
untrusted reports that are part of the incident's information environment."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .model import CrewMember, MissionState, Module, ModuleStatus


@dataclass(frozen=True)
class Report:
    """A non-sensor claim in the information environment (crew radio, classifier flag...).

    Reports are *untrusted*: they may be wrong, and a well-grounded action must not rest on
    one when trusted telemetry contradicts it."""

    report_id: str
    tick: int
    source: str
    text: str
    # An automated subsystem may submit its own recommended action into the fork.
    recommends: tuple[str, tuple[tuple[str, str], ...]] | None = None
    recommendation_rationale: str = ""


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    briefing: str
    state: MissionState
    reports: tuple[Report, ...] = ()


def _base_modules() -> tuple[Module, ...]:
    N = ModuleStatus.NOMINAL
    return (
        Module("HAB", "Habitat (incl. thermal heaters)", N, 100.0, True, 4.5, False),
        Module("LAB", "Science Lab", N, 100.0, True, 4.0, False),
        Module("GREENHOUSE", "Greenhouse", N, 100.0, True, 2.5, False),
        Module("LIFE_SUPPORT", "Life Support (O2 generation)", N, 100.0, True, 3.0, True),
        Module("REACTOR", "Fission Reactor & Coolant Pumps", N, 100.0, True, 2.0, True),
        Module("COMMS", "Communications", N, 100.0, True, 1.0, False),
        Module("SOLAR", "Solar Array Field", N, 100.0, True, 0.5, False),
    )


def _base_crew() -> tuple[CrewMember, ...]:
    return (
        CrewMember("C1", "Cmdr. Okafor", "HAB", 100.0),
        CrewMember("C2", "Dr. Lindqvist", "LAB", 100.0),
        CrewMember("C3", "Eng. Ramos", "HAB", 100.0),
        CrewMember("C4", "Dr. Chen", "GREENHOUSE", 100.0),
    )


def _base_state(scenario_id: str, seed: int) -> MissionState:
    return MissionState(
        mission_id=f"ARTEMIS-BASE-{scenario_id.upper()}-{seed}",
        scenario_id=scenario_id,
        seed=seed,
        tick=0,
        revision=0,
        oxygen_reserve_kg=40.0,
        oxygen_capacity_kg=60.0,
        power_reserve_kwh=30.0,
        power_capacity_kwh=60.0,
        solar_peak_kw=12.0,
        reactor_output_kw=6.0,
        reactor_temp_c=640.0,
        reactor_heat_rate_c_per_tick=14.0,
        reactor_online=True,
        coolant_vents_remaining=2,
        vent_cooldown_ticks=0,
        backup_charge_kwh=10.0,
        backup_active=False,
        backup_output_kw=6.0,
        repair_kits=2,
        leak_rate_kg_per_tick_at_zero_integrity=0.5,
        modules=_base_modules(),
        crew=_base_crew(),
    )


def solar_cascade(seed: int = 7) -> Scenario:
    """Signature scenario: micrometeoroid strike on the solar field -> energy cascade.

    An automated anomaly classifier also emits a low-confidence flag about the habitat,
    which HAB's own pressure and integrity sensors contradict."""
    s = _base_state("solar_cascade", seed)
    solar = s.module("SOLAR")
    assert solar is not None
    s = s.with_module(replace(solar, status=ModuleStatus.DAMAGED, integrity_pct=45.0))
    s = replace(s, power_reserve_kwh=9.0, backup_charge_kwh=4.0)
    s = s.log("Micrometeoroid strike on SOLAR: array integrity 45%")
    reports = (
        Report(
            "R-HAB-01", 0, "anomaly-classifier v0.3 (unvalidated)",
            "Low-confidence flag (0.31): HAB may have a hull micro-fracture causing excess "
            "heater load. Recommended action: isolate_module(HAB). No corroborating sensor "
            "reading.",
            recommends=("isolate_module", (("module_id", "HAB"),)),
            recommendation_rationale=(
                "HAB hull micro-fracture is causing excess heater load (R-HAB-01); isolating HAB "
                "removes 4.5 kW of load and stops the drain."),
        ),
    )
    return Scenario(
        "solar_cascade", "Solar Array Strike — Energy Cascade",
        "A micrometeoroid shower has crippled the solar field. Generation no longer covers "
        "load; the battery reserve is draining and a brownout will shed systems, including "
        "reactor coolant pumps.",
        s, reports,
    )


def oxygen_leak(seed: int = 11) -> Scenario:
    s = _base_state("oxygen_leak", seed)
    gh = s.module("GREENHOUSE")
    assert gh is not None
    s = s.with_module(replace(gh, status=ModuleStatus.BREACHED, integrity_pct=40.0))
    s = replace(s, oxygen_reserve_kg=14.0)
    s = s.log("GREENHOUSE pressure loss detected: hull breach, integrity 40%")
    reports = (
        Report("R-C4-01", 0, "crew radio (Dr. Chen)",
               "Hearing a hiss near the greenhouse grow racks. Moving to the hatch."),
    )
    return Scenario(
        "oxygen_leak", "Greenhouse Breach — Oxygen Depletion",
        "The greenhouse hull has been breached. Atmosphere is venting faster than life "
        "support can regenerate it, and one crew member is inside the breached module.",
        s, reports,
    )


def reactor_overheat(seed: int = 23) -> Scenario:
    s = _base_state("reactor_overheat", seed)
    reactor = s.module("REACTOR")
    assert reactor is not None
    s = s.with_module(replace(reactor, powered=False))
    ramos = s.crew_member("C3")
    assert ramos is not None
    s = s.with_crew_member(replace(ramos, location="REACTOR"))
    s = replace(s, reactor_temp_c=790.0)
    s = s.log("Breaker trip: REACTOR coolant pumps unpowered; core heating 14 C/tick")
    reports = (
        Report("R-C3-01", 0, "crew radio (Eng. Ramos)",
               "I'm in the reactor bay checking the pump breaker. Temperature is climbing."),
    )
    return Scenario(
        "reactor_overheat", "Reactor Overheat — Conflicting Mitigations",
        "A breaker trip cut power to the reactor coolant pumps. The core is heating toward "
        "automatic SCRAM at 900 C. An engineer is inside the reactor bay.",
        s, reports,
    )


SCENARIOS = {
    "solar_cascade": solar_cascade,
    "oxygen_leak": oxygen_leak,
    "reactor_overheat": reactor_overheat,
}


def load_scenario(scenario_id: str, seed: int | None = None) -> Scenario:
    factory = SCENARIOS.get(scenario_id)
    if factory is None:
        raise KeyError(f"unknown scenario '{scenario_id}' (known: {', '.join(SCENARIOS)})")
    return factory() if seed is None else factory(seed)
