"""FORK REALITY: branch the canonical state, apply candidate actions, simulate an identical
horizon for each branch, and score the outcomes with an explicit deterministic function.

The canonical state is never mutated: MissionState is frozen and every branch starts from
the same immutable snapshot. A NO-OP baseline branch is always included so every candidate
is judged against "do nothing".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .actions import Action, apply_action, validate_action
from .model import SIM_VERSION, MissionState
from .physics import simulate


@dataclass(frozen=True)
class ScoreWeights:
    """Weights of the outcome score. Each component is normalised to 0..1 first."""

    crew: float = 0.35
    oxygen: float = 0.15
    power: float = 0.20
    reactor: float = 0.15
    continuity: float = 0.10   # penalises brownout load-shedding events
    resources: float = 0.05


@dataclass(frozen=True)
class Outcome:
    crew_alive: int
    crew_total: int
    mean_crew_health_pct: float
    oxygen_kg: float
    power_kwh: float
    min_power_kwh: float
    reactor_temp_c: float
    peak_reactor_temp_c: float
    reactor_online: bool
    brownout_events: int
    resources_used: int
    score: float
    components: dict[str, float]


@dataclass(frozen=True)
class Branch:
    branch_id: str
    action: Action | None              # None = NO-OP baseline
    legal: bool
    violations: tuple[str, ...]
    trajectory: tuple[MissionState, ...]
    outcome: Outcome | None
    events: tuple[str, ...] = field(default_factory=tuple)

    @property
    def label(self) -> str:
        return "NO-OP (do nothing)" if self.action is None else self.action.key()


@dataclass(frozen=True)
class ForkResult:
    origin_tick: int
    origin_revision: int
    origin_hash: str
    seed: int
    horizon: int
    sim_version: str
    weights: ScoreWeights
    branches: tuple[Branch, ...]

    def ranked(self) -> list[Branch]:
        legal = [b for b in self.branches if b.legal and b.outcome and b.action is not None]
        return sorted(legal, key=lambda b: b.outcome.score if b.outcome else 0, reverse=True)

    def baseline(self) -> Branch:
        return next(b for b in self.branches if b.action is None)


def score_outcome(origin: MissionState, traj: list[MissionState], weights: ScoreWeights) -> Outcome:
    final = traj[-1] if traj else origin
    alive = final.alive_crew()
    crew_c = sum(c.health_pct for c in final.crew) / (100.0 * len(final.crew))
    oxygen_c = min(1.0, final.oxygen_reserve_kg / final.oxygen_capacity_kg)
    min_power = min((s.power_reserve_kwh for s in traj), default=origin.power_reserve_kwh)
    power_c = min(1.0, final.power_reserve_kwh / final.power_capacity_kwh)
    peak_temp = max((s.reactor_temp_c for s in traj), default=origin.reactor_temp_c)
    # 1.0 at <= 700 C, 0.0 at >= 1100 C, and halved if the reactor ended offline.
    reactor_c = max(0.0, min(1.0, (1100.0 - peak_temp) / 400.0))
    if not final.reactor_online:
        reactor_c *= 0.5
    used = (origin.repair_kits - final.repair_kits) + (
        origin.coolant_vents_remaining - final.coolant_vents_remaining)
    resources_c = max(0.0, 1.0 - 0.25 * used)
    brownouts = sum(1 for line in final.incident_log if "Brownout" in line) - sum(
        1 for line in origin.incident_log if "Brownout" in line)
    continuity_c = 1.0 - min(1.0, brownouts / 3.0)
    comps = {"crew": crew_c, "oxygen": oxygen_c, "power": power_c, "reactor": reactor_c,
             "continuity": continuity_c, "resources": resources_c}
    score = sum(getattr(weights, k) * v for k, v in comps.items())
    return Outcome(
        crew_alive=len(alive), crew_total=len(final.crew),
        mean_crew_health_pct=round(100 * crew_c, 2),
        oxygen_kg=round(final.oxygen_reserve_kg, 3), power_kwh=round(final.power_reserve_kwh, 3),
        min_power_kwh=round(min_power, 3), reactor_temp_c=round(final.reactor_temp_c, 1),
        peak_reactor_temp_c=round(peak_temp, 1), reactor_online=final.reactor_online,
        brownout_events=brownouts, resources_used=used, score=round(score, 4),
        components={k: round(v, 4) for k, v in comps.items()},
    )


def run_branch(origin: MissionState, action: Action | None, horizon: int,
               weights: ScoreWeights, branch_id: str) -> Branch:
    if action is not None:
        violations = validate_action(origin, action)
        if violations:
            return Branch(branch_id, action, False, tuple(violations), (), None)
        start = apply_action(origin, action)
    else:
        start = origin
    traj = simulate(start, horizon)
    outcome = score_outcome(origin, traj, weights)
    new_events = tuple(traj[-1].incident_log[len(origin.incident_log):]) if traj else ()
    return Branch(branch_id, action, True, (), tuple(traj), outcome, new_events)


def fork_reality(origin: MissionState, candidates: list[Action], horizon: int = 20,
                 weights: ScoreWeights | None = None, max_candidates: int = 3) -> ForkResult:
    if len(candidates) > max_candidates:
        raise ValueError(f"at most {max_candidates} candidates per fork (got {len(candidates)})")
    if horizon < 1 or horizon > 120:
        raise ValueError("horizon must be within 1..120 ticks")
    w = weights or ScoreWeights()
    branches = [run_branch(origin, None, horizon, w, "B0")]
    for i, action in enumerate(candidates, start=1):
        branches.append(run_branch(origin, action, horizon, w, f"B{i}"))
    return ForkResult(origin.tick, origin.revision, origin.state_hash(), origin.seed, horizon,
                      SIM_VERSION, w, tuple(branches))
