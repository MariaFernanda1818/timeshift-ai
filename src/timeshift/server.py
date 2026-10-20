"""FastAPI application: mission API + Server-Sent Events + static dashboard.

    uvicorn timeshift.server:app --port 8080

Live runs execute real Decider inference (and Bedrock when proposer=bedrock). Recorded runs
under runs/*.jsonl are replayed verbatim and are labelled as recordings in the UI.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import threading
import traceback
import uuid
from typing import Any, Literal

from counterfactual_decision_gate import (
    CounterfactualDecisionGate,
    DeciderClient,
    DeciderError,
    Thresholds,
)
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .fixtures import FIXTURE_PROPOSALS
from .mission import Event, Mission, Proposal
from .sim.scenarios import SCENARIOS, load_scenario

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNS = pathlib.Path(os.environ.get("TIMESHIFT_RUNS_DIR", ROOT / "runs"))
DIST = pathlib.Path(os.environ.get("TIMESHIFT_UI_DIST", ROOT / "frontend" / "dist"))

app = FastAPI(title="TIME//SHIFT", version="0.1.0")
MISSIONS: dict[str, Mission] = {}
RUN_LOCK = threading.Lock()  # Decider is driven one request at a time


def decider_client() -> DeciderClient:
    return DeciderClient(timeout_s=float(os.environ.get("DECIDER_TIMEOUT_S", "600")), retries=0,
                         expected_checkpoint=os.environ.get("DECIDER_EXPECTED_CHECKPOINT"))


def thresholds() -> Thresholds:
    return Thresholds(proceed_at=float(os.environ.get("DECIDER_PROCEED_AT", "0.70")),
                      deny_below=float(os.environ.get("DECIDER_DENY_BELOW", "0.40")))


class StartMission(BaseModel):
    scenario: str = "solar_cascade"
    seed: int | None = None
    proposer: Literal["fixture", "bedrock"] = "fixture"
    advance_after: int = 12


@app.get("/api/health")
def health() -> dict[str, Any]:
    out: dict[str, Any] = {"bedrock_model_id": os.environ.get("BEDROCK_MODEL_ID")}
    try:
        out["decider"] = {"status": "ok", **decider_client().health(refresh=True)}
    except DeciderError as exc:
        out["decider"] = {"status": exc.status, "error": str(exc)}
    return out


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    out = []
    for sid in SCENARIOS:
        sc = load_scenario(sid)
        out.append({"scenario_id": sid, "title": sc.title, "briefing": sc.briefing,
                    "has_fixture": sid in FIXTURE_PROPOSALS})
    return out


@app.post("/api/missions")
def start_mission(req: StartMission) -> dict[str, str]:
    if req.scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario {req.scenario}")
    th = thresholds()
    escalate = None
    if os.environ.get("TIMESHIFT_ESCALATION") == "bedrock":
        from .judge import BedrockJudge

        escalate = BedrockJudge().escalation(th.proceed_at, th.deny_below)
    gate = CounterfactualDecisionGate(decider_client(), th, escalate=escalate)
    m = Mission.from_scenario(req.scenario, req.seed, gate)
    mid = uuid.uuid4().hex[:10]
    MISSIONS[mid] = m
    threading.Thread(target=_run, args=(mid, m, req), daemon=True).start()
    return {"mission_id": mid}


def _run(mid: str, m: Mission, req: StartMission) -> None:
    with RUN_LOCK:
        try:
            m.emit("run.status", {"status": "running", "proposer": req.proposer})
            if req.proposer == "bedrock":
                from .agent import MissionAgent

                MissionAgent(m, m.gate).run()  # type: ignore[arg-type]
            else:
                m.emit("agent.proposals", {"proposer": "fixture",
                                           "proposals": FIXTURE_PROPOSALS[req.scenario]})
                props = [Proposal(**p, based_on_revision=m.state.revision,
                                  based_on_tick=m.state.tick)
                         for p in FIXTURE_PROPOSALS[req.scenario]]
                out = m.decide(props)
                if out.get("review"):
                    m.emit("run.status", {"status": "awaiting_review", "fork_id": out["fork_id"],
                                          "branches": out["review"],
                                          "advance_after": req.advance_after})
                    return
            if req.advance_after:
                m.advance(req.advance_after)
            m.emit("run.status", {"status": "done"})
        except Exception as exc:  # noqa: BLE001 -- surfaced to the UI, never swallowed
            m.emit("run.status", {"status": "error", "error": f"{type(exc).__name__}: {exc}",
                                  "trace": traceback.format_exc()[-2000:]})
        finally:
            RUNS.mkdir(parents=True, exist_ok=True)
            (RUNS / f"live-{m.scenario.scenario_id}-{mid}.jsonl").write_text(
                "\n".join(e.model_dump_json() for e in m.events) + "\n", encoding="utf-8")


@app.get("/api/missions/{mid}/events")
async def stream(mid: str, since: int = -1) -> StreamingResponse:
    m = MISSIONS.get(mid)
    if m is None:
        raise HTTPException(404, "unknown mission")

    async def gen():
        sent = since
        while True:
            for e in m.events[sent + 1:]:
                yield f"data: {e.model_dump_json()}\n\n"
                sent = e.seq
            last = m.events[-1] if m.events else None
            if last and last.type == "run.status" and last.payload.get("status") in (
                    "done", "error"):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


class ReviewDecision(BaseModel):
    fork_id: str
    branch_id: str
    approve: bool
    operator: str = "operator"


@app.post("/api/missions/{mid}/review")
def review(mid: str, body: ReviewDecision) -> dict[str, Any]:
    m = MISSIONS.get(mid)
    if m is None:
        raise HTTPException(404, "unknown mission")
    with RUN_LOCK:
        try:
            m.resolve_review(body.fork_id, body.branch_id, body.operator[:40], body.approve)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
        last = next((e for e in reversed(m.events) if e.type == "run.status"), None)
        ticks = (last.payload.get("advance_after", 0) if last else 0) or 0
        if body.approve and ticks:
            m.advance(ticks)
        m.emit("run.status", {"status": "done"})
        RUNS.mkdir(parents=True, exist_ok=True)
        (RUNS / f"live-{m.scenario.scenario_id}-{mid}.jsonl").write_text(
            "\n".join(e.model_dump_json() for e in m.events) + "\n", encoding="utf-8")
    return {"revision": m.state.revision}


@app.post("/api/missions/{mid}/advance")
def advance(mid: str, ticks: int = 1) -> dict[str, Any]:
    m = MISSIONS.get(mid)
    if m is None:
        raise HTTPException(404, "unknown mission")
    if not 1 <= ticks <= 60:
        raise HTTPException(422, "ticks must be 1..60")
    m.advance(ticks)
    return {"tick": m.state.tick}


@app.get("/api/replays")
def replays() -> list[dict[str, Any]]:
    if not RUNS.exists():
        return []
    out = []
    for p in sorted(RUNS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        first = json.loads(p.read_text(encoding="utf-8", errors="replace").splitlines()[0])
        out.append({"name": p.stem, "scenario": first["payload"].get("scenario"),
                    "mission_id": first["mission_id"], "events": sum(1 for _ in p.open())})
    return out


@app.get("/api/replays/{name}")
def replay(name: str) -> list[dict[str, Any]]:
    p = (RUNS / f"{name}.jsonl").resolve()
    if p.parent != RUNS.resolve() or not p.exists():
        raise HTTPException(404, "unknown replay")
    return [Event.model_validate_json(line).model_dump() for line in p.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()]


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
