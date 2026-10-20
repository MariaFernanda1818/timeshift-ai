# Simulation model (`timeshift-sim/1.0.0`)

**Illustrative, not a validated aerospace model.** The numbers produce meaningful trade-offs
for the agent. They are not engineering predictions.

## State and units

| Field | Unit | Notes |
|---|---|---|
| tick | 5 minutes | discrete time |
| oxygen_reserve_kg / capacity | kg | 60 kg capacity |
| power_reserve_kwh / capacity | kWh | 60 kWh battery |
| solar_peak_kw | kW | 12 kW × SOLAR integrity |
| reactor_output_kw | kW | 6 kW; halved for 6 ticks after a vent |
| reactor_temp_c | °C | SCRAM ≥ 900, destroyed ≥ 1100, crew radiation in REACTOR ≥ 1000 |
| backup_charge_kwh / output | kWh / kW | only while active |
| module load_kw | kW | HAB 4.5, LAB 4, GREENHOUSE 2.5, LIFE_SUPPORT 3, REACTOR pumps 2, COMMS 1, SOLAR 0.5 |
| crew health_pct | % | 0 = lost |

## Per-tick transition (`physics.step`, pure)

1. **Power:** reserve += (generation − powered load) × 5/60 h, capped. At 0, brownout sheds
   non-critical loads first (largest first), then critical ones.
2. **Oxygen:** −0.035 kg/h per crew member in base. +0.25 kg/h from LIFE_SUPPORT if powered
   (half if damaged). Breached modules leak `0.5 kg/tick × (100 − integrity)/100 × jitter`,
   where jitter is ±10% from an RNG seeded by (seed, tick).
3. **Reactor:** if pumps are powered and nominal, relax toward 600 °C at 6 °C/tick. Otherwise heat
   at `reactor_heat_rate` (14 °C/tick). Offline cores cool.
4. **Repairs:** EVA jobs count down. On completion, integrity is added and the crew member returns.
5. **Crew:** damage applies from low O₂ (< 15% capacity), being in a breached module, or radiation.

## Actions (preconditions → effect)

| Tool | Preconditions | Effect / cost |
|---|---|---|
| `isolate_module(module_id)` | exists; not LIFE_SUPPORT; not already isolated/destroyed; relocation target available | sealed, unpowered, crew relocated |
| `activate_backup_power()` | not active; charge > 0 | +6 kW until depleted |
| `reroute_power(source, target)` | both exist; differ; source powered and non-critical; target not isolated/destroyed | source off, target on |
| `vent_reactor()` | reactor available; vents left; **no crew in REACTOR** | −160 °C now, output halved 6 ticks, −1 vent |
| `repair_solar_array(crew_id)` | crew exists, alive, health ≥ 60, not on EVA; SOLAR < 95%; kit; O₂ ≥ 0.6 kg; no concurrent repair | 8-tick EVA, +55% integrity, −1 kit, −0.6 kg O₂ |

## Guarantees (tested in `tests/test_simulation.py`)

- Same initial state + seed + actions → identical state hashes.
- `MissionState` is a frozen dataclass. Forking never changes the canonical hash.
- A branch run alone equals the same branch run alongside others (isolation).
- Invariants hold for 120 ticks in every scenario: O₂, power and backup within bounds;
  health and integrity within 0..100.

## Scenarios

| id | Incident | Notable trap |
|---|---|---|
| `solar_cascade` | Solar field at 45%; reserve draining toward brownout | Unverified classifier flag R-HAB-01 suggests isolating HAB. The simulator ranks it #1 |
| `oxygen_leak` | GREENHOUSE breached at 40%; O₂ 14 kg | Wrong-target isolations |
| `reactor_overheat` | Coolant pumps unpowered; 790 °C; engineer inside REACTOR | Venting is illegal while crew is inside; rerouting power is the safe fix |
