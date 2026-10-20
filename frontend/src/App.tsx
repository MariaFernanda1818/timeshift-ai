import { useEffect, useMemo, useState } from "react";
import { Comparison } from "./components/Comparison";
import { DecisionGate } from "./components/DecisionGate";
import { FutureExplorer, verdictFor } from "./components/FutureExplorer";
import { LunarBase } from "./components/LunarBase";
import { MissionStatus } from "./components/MissionStatus";
import { Timeline } from "./components/Timeline";
import type { DecisionView } from "./types";
import { useMission } from "./useMission";

interface Scenario { scenario_id: string; title: string }
interface Replay { name: string; scenario: string; events: number }

export default function App() {
  const { source, view, startLive, startReplay, speed, setSpeed, replayTotal } = useMission();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [replays, setReplays] = useState<Replay[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [scenario, setScenario] = useState("solar_cascade");
  const [proposer, setProposer] = useState("bedrock");
  const [selected, setSelected] = useState<string | null>(null);
  const [scrub, setScrub] = useState(20);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/scenarios").then(r => r.json()).then(setScenarios).catch(() => setErr("API unreachable"));
    fetch("/api/replays").then(r => r.json()).then(setReplays).catch(() => {});
    const h = () => fetch("/api/health").then(r => r.json()).then(j => setHealth(j.decider)).catch(() => setHealth({ status: "unreachable" }));
    h();
    const t = setInterval(h, 15000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => { if (view.status === "done") fetch("/api/replays").then(r => r.json()).then(setReplays).catch(() => {}); }, [view.status]);

  const fork = view.forks.at(-1) ?? null;
  useEffect(() => { setSelected(null); if (fork) setScrub(fork.horizon); }, [fork?.fork_id, source]); // eslint-disable-line react-hooks/exhaustive-deps
  const committedKeys = useMemo(() => new Set(view.committed.map(c => c.tool + JSON.stringify(c.args))), [view.committed]);
  const selBranch = fork?.branches.find(b => b.branch_id === selected) ?? null;
  const [picked, setPicked] = useState<DecisionView | null>(null);
  useEffect(() => setPicked(null), [view.decisions.length, selected]);
  const shownDecision = picked ?? (fork && selBranch ? verdictFor(fork, selBranch, view.decisions) : undefined) ?? view.decisions.at(-1) ?? null;
  const pending = view.status === "running" && !!fork && view.decisions.length === 0;
  const ghostState = selBranch?.final_state ?? null;
  const live = source.kind === "live";
  const review = (branch_id: string, approve: boolean) => {
    if (source.kind !== "live" || !view.review) return;
    fetch(`/api/missions/${source.missionId}/review`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ fork_id: view.review.fork_id, branch_id, approve, operator: "operator" }),
    }).then(async r => { if (!r.ok) setErr(await r.text()); });
  };

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-line bg-void/90 backdrop-blur px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex items-baseline gap-2">
            <h1 className="mono text-lg font-semibold tracking-[0.2em]">TIME<span className="text-amber">//</span>SHIFT</h1>
            <span className="hidden md:inline text-[11px] text-dim">Explore possible futures. Verify decisions. Change the outcome.</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 ml-auto">
            <span className={`mono text-[10px] px-1.5 py-0.5 rounded border ${source.kind === "replay" ? "border-amber text-amber" : live ? "border-ok text-ok" : "border-line text-dim"}`}>
              {source.kind === "replay" ? `RECORDED RUN · ${source.name} · ${view.events.length}/${replayTotal}${view.events.length === replayTotal && replayTotal ? " · COMPLETE" : ""}` : live ? `LIVE · ${source.missionId}` : "STANDBY"}
            </span>
            <select aria-label="Scenario" className="bg-panel border border-line rounded px-2 py-1 text-[12px]" value={scenario} onChange={e => setScenario(e.target.value)}>
              {scenarios.map(s => <option key={s.scenario_id} value={s.scenario_id}>{s.title}</option>)}
            </select>
            <select aria-label="Proposer" className="bg-panel border border-line rounded px-2 py-1 text-[12px]" value={proposer} onChange={e => setProposer(e.target.value)}>
              <option value="bedrock">Proposer: Amazon Bedrock agent</option>
              <option value="fixture">Proposer: fixed candidate set</option>
            </select>
            <button disabled={view.status === "running" && live} onClick={() => startLive(scenario, proposer).catch(e => setErr(String(e)))}
              className="rounded bg-amber/90 hover:bg-amber text-void font-semibold text-[12px] px-3 py-1 disabled:opacity-40">Run live</button>
            <select aria-label="Recorded runs" className="bg-panel border border-line rounded px-2 py-1 text-[12px] max-w-[180px]" value="" onChange={e => e.target.value && startReplay(e.target.value)}>
              <option value="">Replay recording…</option>
              {replays.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
            </select>
            <select aria-label="Replay speed" className="bg-panel border border-line rounded px-1 py-1 text-[12px]" value={speed} onChange={e => setSpeed(Number(e.target.value))}>
              {[0.5, 1, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
            </select>
          </div>
        </div>
      </header>

      {(err || view.error) && <div className="mx-4 mt-3 rounded border border-alert bg-alert/10 p-2 text-sm">{err || view.error}</div>}

      <main className="p-3 md:p-4 grid gap-3 md:gap-4 xl:grid-cols-[minmax(300px,1fr)_minmax(0,2fr)_minmax(320px,1.1fr)]">
        <div className="space-y-3 md:space-y-4 min-w-0">
          <MissionStatus s={view.state} emergency={view.title || "No active incident"} />
          <LunarBase s={ghostState ?? view.state} ghost={ghostState ? `${selected} future @ T+${fork?.horizon}` : null} />
          <section className="panel p-4" aria-label="Agent reasoning">
            <h2 className="panel-title mb-2">C · Agent reasoning</h2>
            {view.agentBriefing ? (
              <details className="text-[12px]">
                <summary className="cursor-pointer text-dim"><span className="mono text-[10px] text-amber border border-amber/60 rounded px-1 mr-1">UNVERIFIED</span>Bedrock free-text briefing</summary>
                <p className="mt-1 whitespace-pre-wrap text-ink/80">{view.agentBriefing.replace(/\*\*/g, "")}</p>
              </details>
            ) :
              view.proposer === "fixture" ? <p className="text-[12px] text-dim">Candidates in this run come from the <b className="text-amber">fixed fixture set</b> (hand-written, identical across benchmark configurations), not from Bedrock. Branch outcomes and Decider verdicts are real.</p> :
                <p className="text-[12px] text-dim">{view.briefing || "Start a live run or replay a recording."}</p>}
            {view.explanation?.explanation && (
              <div className="mt-3 border-t border-line pt-2 text-[12px] space-y-1">
                <div className="flex items-center gap-2"><span className="panel-title">Consequence explanation</span>
                  <span className={`mono text-[10px] px-1 rounded border ${view.explanation.grounded ? "border-ok text-ok" : "border-alert text-alert"}`}>{view.explanation.grounded ? "NUMBERS VERIFIED" : "UNSUPPORTED CLAIMS"}</span></div>
                {view.explanation.grounded ? (<>
                  <p className="text-ink">{view.explanation.explanation.headline}</p>
                  <p>{view.explanation.explanation.why_selected}</p>
                  {view.explanation.explanation.rejected.map((r: any) => <p key={r.branch_id}><b className="mono text-alert">{r.branch_id}</b> {r.reason}</p>)}
                  <p className="text-dim">Limits: {view.explanation.explanation.limitations}</p>
                </>) : <p className="text-alert">Explanation withheld: it cited values not in the simulation packet ({view.explanation.unsupported_claims.join(", ")}).</p>}
              </div>
            )}
            {view.explanation?.error && <p className="text-[12px] text-alert mt-2">Explanation failed: {view.explanation.error}</p>}
            {view.agentUsage && <div className="mono text-[10px] text-dim mt-2">tokens in {view.agentUsage.input_tokens} · out {view.agentUsage.output_tokens}</div>}
          </section>
        </div>
        <div className="space-y-3 md:space-y-4 min-w-0">
          <FutureExplorer fork={fork} decisions={view.decisions} committedKeys={committedKeys} selected={selected} onSelect={setSelected} scrub={Math.min(scrub, fork?.horizon ?? 20)} setScrub={setScrub} />
          <Comparison fork={fork} decisions={view.decisions} committedKeys={committedKeys} />
        </div>
        <div className="space-y-3 md:space-y-4 min-w-0">
          {view.status === "awaiting_review" && view.review && source.kind === "live" && (
            <section className="panel p-4 border-amber" aria-label="Operator review">
              <h2 className="panel-title text-amber">Operator review required</h2>
              <p className="text-[12px] text-dim mt-1">No branch reached PROCEED. The gate sent {view.review.branches.join(", ")} to human review. Approving commits it under your name; the deterministic policy is re-checked first.</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {view.review.branches.map(b => (
                  <span key={b} className="flex gap-1">
                    <button className="rounded bg-ok/90 text-void text-[12px] font-semibold px-2 py-1" onClick={() => review(b, true)}>Approve {b}</button>
                    <button className="rounded border border-alert text-alert text-[12px] px-2 py-1" onClick={() => review(b, false)}>Reject {b}</button>
                  </span>
                ))}
              </div>
            </section>
          )}
          <DecisionGate d={shownDecision} all={view.decisions} onPick={setPicked} pending={pending} deciderHealth={health} />
          <Timeline events={view.events} />
        </div>
      </main>
      <footer className="px-4 pb-4 text-[11px] text-dim">
        Illustrative simulation — not a validated aerospace model. Bedrock proposes · Simulation explores · Decider evaluates · Deterministic policies enforce.
      </footer>
    </div>
  );
}
