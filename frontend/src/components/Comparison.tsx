import type { BranchView, DecisionView, ForkView } from "../types";
import { BRANCH_COLORS, verdictFor } from "./FutureExplorer";

function Col({ title, sub, b, i, tone }: { title: string; sub: string; b: BranchView | undefined; i: number; tone: string }) {
  const o = b?.outcome;
  return (
    <div className={`rounded border p-3 ${tone}`}>
      <div className="panel-title">{title}</div>
      <div className="text-[11px] text-dim mb-2">{sub}</div>
      {b && o ? (
        <>
          <div className="mono text-sm [overflow-wrap:anywhere]" style={{ color: BRANCH_COLORS[i % 4] }}>{b.branch_id} · {b.label}</div>
          <dl className="mono text-[11px] grid grid-cols-2 gap-x-3 gap-y-0.5 mt-2">
            <dt className="text-dim">sim score</dt><dd>{o.score.toFixed(3)}</dd>
            <dt className="text-dim">crew alive</dt><dd>{o.crew_alive}/{o.crew_total}</dd>
            <dt className="text-dim">O₂ final</dt><dd>{o.oxygen_kg.toFixed(1)} kg</dd>
            <dt className="text-dim">power final</dt><dd>{o.power_kwh.toFixed(1)} kWh</dd>
            <dt className="text-dim">reactor peak</dt><dd>{o.peak_reactor_temp_c.toFixed(0)} °C</dd>
            <dt className="text-dim">brownouts</dt><dd>{o.brownout_events}</dd>
          </dl>
          {b.cited_evidence.length > 0 && <div className="mt-2 text-[11px] text-dim">premise: <span className="mono">{b.cited_evidence.join(", ")}</span></div>}
          {b.final_state && <div className="mt-1 text-[11px] text-dim">modules isolated: <span className="mono text-ink">{b.final_state.modules.filter(m => m.status === "isolated").map(m => m.module_id).join(", ") || "none"}</span></div>}
        </>
      ) : <div className="text-sm text-dim">—</div>}
    </div>
  );
}

export function Comparison({ fork, decisions, committedKeys }: { fork: ForkView | null; decisions: DecisionView[]; committedKeys: Set<string> }) {
  if (!fork) return null;
  const top = fork.branches.find(b => b.branch_id === fork.ranked[0]);
  const committed = fork.branches.find(b => b.action && committedKeys.has(b.action.tool + JSON.stringify(b.action.args)));
  const topVerdict = top ? verdictFor(fork, top, decisions)?.verdict : undefined;
  const same = top && committed && top.branch_id === committed.branch_id;
  const idx = (b?: BranchView) => (b ? fork.branches.indexOf(b) : 0);
  return (
    <section className="panel p-4" aria-label="Comparison">
      <h2 className="panel-title">G · Comparison — same seed, same horizon, same candidates</h2>
      <p className="text-[12px] text-dim mt-1 mb-3">
        Outcomes below are <b className="text-ink">simulated</b> over {fork.horizon} ticks from the identical state ({fork.origin_hash}).
        {!committed ? " Nothing has been committed yet." : same ? " Here the gate approved the simulator's top-ranked branch, so both configurations agree." :
          topVerdict === "DENY" ? " Selecting purely by simulated score commits the top branch. TIME//SHIFT refused it: the gate found it unsupported by trusted evidence or in violation of policy." :
            " The committed branch differs from the top-scoring one."}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <Col title="A · Score-greedy, no evidence gate" sub="Same candidates + deterministic checks; commits the highest simulated score" b={top} i={idx(top)} tone="border-alert/50" />
        <Col title="C · TIME//SHIFT" sub="+ Strands Decider 2B evidence-grounding gate" b={committed} i={idx(committed)} tone="border-ok/50" />
      </div>
    </section>
  );
}
