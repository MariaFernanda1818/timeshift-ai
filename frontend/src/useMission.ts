import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DecisionView, ForkView, MissionEvent, MissionStateSnap } from "./types";

export type Source =
  | { kind: "idle" }
  | { kind: "live"; missionId: string }
  | { kind: "replay"; name: string };

export interface MissionView {
  events: MissionEvent[];
  state: MissionStateSnap | null;
  initial: MissionStateSnap | null;
  title: string;
  briefing: string;
  scenario: string;
  forks: ForkView[];
  decisions: DecisionView[];
  committed: { proposal_id: string; tool: string; args: Record<string, unknown>; tick: number }[];
  proposer: string | null;
  status: "idle" | "running" | "awaiting_review" | "done" | "error";
  review: { fork_id: string; branches: string[] } | null;
  error: string | null;
  agentBriefing: string | null;
  agentUsage: Record<string, any> | null;
  explanation: Record<string, any> | null;
}

/** Pure reduction of the event log into a view. The UI never invents state. */
export function reduce(events: MissionEvent[]): MissionView {
  const v: MissionView = {
    events, state: null, initial: null, title: "", briefing: "", scenario: "", forks: [],
    decisions: [], committed: [], proposer: null, status: "idle", error: null,
    agentBriefing: null, agentUsage: null, explanation: null, review: null,
  };
  for (const e of events) {
    const p = e.payload;
    switch (e.type) {
      case "mission.started":
        v.state = p.state; v.initial = p.state; v.title = p.title; v.briefing = p.briefing;
        v.scenario = p.scenario; v.status = "running"; break;
      case "mission.advanced":
      case "action.committed":
        v.state = p.state;
        if (e.type === "action.committed")
          v.committed.push({ ...p.proposal, tick: e.tick });
        break;
      case "fork.created": v.forks.push(p as ForkView); break;
      case "gate.decision": v.decisions.push(p as DecisionView); break;
      case "agent.proposals": v.proposer = p.proposer; break;
      case "agent.finished": v.agentBriefing = p.briefing; v.agentUsage = p.usage; break;
      case "agent.explanation": v.explanation = p; break;
      case "run.status":
        if (p.status === "done") { v.status = "done"; v.review = null; }
        if (p.status === "running") v.status = "running";
        if (p.status === "awaiting_review") { v.status = "awaiting_review"; v.review = { fork_id: p.fork_id, branches: p.branches }; }
        if (p.status === "error") { v.status = "error"; v.error = p.error; }
        break;
    }
  }
  if (events.length && v.status === "running" && !events.some(e => e.type === "run.status"))
    v.status = "done"; // recordings made by scripts/run_cycle.py have no run.status events
  return v;
}

export function useMission() {
  const [source, setSource] = useState<Source>({ kind: "idle" });
  const [events, setEvents] = useState<MissionEvent[]>([]);
  const [speed, setSpeed] = useState(1);
  const [replayTotal, setReplayTotal] = useState(0);
  const timers = useRef<number[]>([]);
  const es = useRef<EventSource | null>(null);

  const stop = useCallback(() => {
    timers.current.forEach(t => clearTimeout(t));
    timers.current = [];
    es.current?.close();
    es.current = null;
  }, []);

  const startLive = useCallback(async (scenario: string, proposer: string) => {
    stop();
    setEvents([]);
    const r = await fetch("/api/missions", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ scenario, proposer }),
    });
    if (!r.ok) throw new Error(await r.text());
    const { mission_id } = await r.json();
    setSource({ kind: "live", missionId: mission_id });
    const src = new EventSource(`/api/missions/${mission_id}/events`);
    es.current = src;
    src.onmessage = m => {
      const ev = JSON.parse(m.data) as MissionEvent;
      setEvents(prev => (prev.some(x => x.seq === ev.seq) ? prev : [...prev, ev]));
    };
    src.addEventListener("end", () => src.close());
  }, [stop]);

  /** Replays a recording with its original relative timing (compressed by `speed`, gaps capped). */
  const startReplay = useCallback(async (name: string) => {
    stop();
    setEvents([]);
    setSource({ kind: "replay", name });
    const all: MissionEvent[] = await (await fetch(`/api/replays/${name}`)).json();
    setReplayTotal(all.length);
    let delay = 0;
    all.forEach((ev, i) => {
      const gap = i === 0 ? 0 : Math.min(4, Math.max(0.6, ev.ts - all[i - 1].ts));
      delay += (gap * 1000) / speed;
      timers.current.push(window.setTimeout(() => setEvents(prev => [...prev, ev]), delay));
    });
  }, [stop, speed]);

  useEffect(() => stop, [stop]);
  const view = useMemo(() => reduce(events), [events]);
  return { source, view, startLive, startReplay, speed, setSpeed, replayTotal };
}
