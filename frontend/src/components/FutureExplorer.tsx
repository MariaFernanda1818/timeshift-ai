import { useMemo, useState } from "react";
import type { BranchView, DecisionView, ForkView, SeriesPoint } from "../types";

const METRICS: { key: keyof SeriesPoint; label: string; unit: string }[] = [
  { key: "power_kwh", label: "Power reserve", unit: "kWh" },
  { key: "oxygen_kg", label: "Oxygen", unit: "kg" },
  { key: "reactor_c", label: "Reactor", unit: "°C" },
  { key: "crew_health", label: "Crew health", unit: "%" },
];
export const BRANCH_COLORS = ["#6d7d99", "#47d4e8", "#f2a93b", "#c792ea"];

export function verdictFor(fork: ForkView, b: BranchView, decisions: DecisionView[]): DecisionView | undefined {
  if (!b.action) return undefined;
  return [...decisions].reverse().find(d => d.fork_id === fork.fork_id && d.proposal.tool === b.action!.tool &&
    JSON.stringify(d.proposal.args) === JSON.stringify(b.action!.args));
}

export function Stamp({ verdict, committed = false }: { verdict: string; committed?: boolean }) {
  const tone = committed || verdict === "PROCEED" ? "text-ok border-ok" : verdict === "DENY" ? "text-alert border-alert" : "text-amber border-amber";
  const text = committed ? "COMMITTED" : verdict === "PROCEED" ? "APPROVED" : verdict === "DENY" ? "REJECTED" : "REVIEW";
  return <span className={`stamp mono inline-block border-2 px-1.5 text-[11px] font-semibold tracking-widest ${tone}`}>{text}</span>;
}

export function FutureExplorer({ fork, decisions, committedKeys, selected, onSelect, scrub, setScrub }: {
  fork: ForkView | null; decisions: DecisionView[]; committedKeys: Set<string>;
  selected: string | null; onSelect: (id: string | null) => void; scrub: number; setScrub: (n: number) => void;
}) {
  const [metric, setMetric] = useState(0);
  const m = METRICS[metric];
  const legal = useMemo(() => fork?.branches.filter(b => b.series.length) ?? [], [fork]);
  if (!fork) {
    return (
      <section className="panel p-4 min-h-[260px]" aria-label="Future explorer">
        <h2 className="panel-title">D · Future explorer</h2>
        <p className="mt-6 text-sm text-dim">No fork yet. When the agent proposes candidate actions, TIME//SHIFT forks the simulation and every simulated future appears here.</p>
      </section>
    );
  }
  const all = legal.flatMap(b => b.series.map(p => Number(p[m.key])));
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.1 || 1;
  const yMin = lo - pad, yMax = hi + pad;
  const W = 600, H = 170, n = fork.horizon;
  const px = (t: number) => 34 + ((t - fork.origin_tick) / n) * (W - 44);
  const py = (v: number) => 10 + (1 - (v - yMin) / (yMax - yMin)) * (H - 30);

  return (
    <section className="panel p-4" aria-label="Future explorer">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="panel-title">D · Future explorer — fork {fork.fork_id}</h2>
        <span className="mono text-[11px] text-dim">from tick {fork.origin_tick} · rev {fork.origin_revision} · seed {fork.seed} · {fork.horizon} ticks · {fork.sim_version} · hash {fork.origin_hash}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {METRICS.map((mm, i) => (
          <button key={mm.key} onClick={() => setMetric(i)}
            className={`mono text-[11px] px-2 py-0.5 rounded border ${i === metric ? "border-cyan text-cyan" : "border-line text-dim"}`}>{mm.label}</button>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full h-[170px]" role="img" aria-label={`${m.label} per simulated branch`}>
        {[0, 0.5, 1].map(f => {
          const v = yMin + f * (yMax - yMin);
          return <g key={f}><line x1={34} x2={W - 10} y1={py(v)} y2={py(v)} stroke="#1c2a44" /><text x={30} y={py(v) + 3} fontSize="9" textAnchor="end" fill="#6d7d99" fontFamily="IBM Plex Mono">{v.toFixed(0)}</text></g>;
        })}
        <line x1={px(fork.origin_tick + scrub)} x2={px(fork.origin_tick + scrub)} y1={8} y2={H - 18} stroke="#f2a93b" strokeDasharray="3 3" />
        {legal.map(b => {
          const i = fork.branches.indexOf(b);
          const d = verdictFor(fork, b, decisions);
          const dim = selected && selected !== b.branch_id;
          const dash = d?.verdict === "DENY" ? "5 4" : undefined;
          const pts = b.series.map(p => `${px(p.tick)},${py(Number(p[m.key]))}`).join(" ");
          return <polyline key={b.branch_id} points={pts} fill="none" stroke={BRANCH_COLORS[i % 4]} strokeWidth={selected === b.branch_id ? 3 : 1.8} strokeDasharray={dash} opacity={dim ? 0.25 : 1} />;
        })}
        <text x={W - 10} y={H - 4} fontSize="9" textAnchor="end" fill="#6d7d99" fontFamily="IBM Plex Mono">{m.label} ({m.unit}) · simulated ticks →</text>
      </svg>
      <label className="flex items-center gap-2 mono text-[11px] text-dim">
        replay T+{scrub}
        <input type="range" min={1} max={fork.horizon} value={scrub} onChange={e => setScrub(Number(e.target.value))} className="flex-1 accent-amber" aria-label="Scrub simulated future" />
      </label>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {fork.branches.map((b, i) => {
          const d = verdictFor(fork, b, decisions);
          const committed = !!b.action && committedKeys.has(b.action.tool + JSON.stringify(b.action.args));
          const rank = fork.ranked.indexOf(b.branch_id);
          const pt = b.series[Math.min(scrub, b.series.length) - 1];
          return (
            <button key={b.branch_id} onClick={() => onSelect(selected === b.branch_id ? null : b.branch_id)}
              className={`text-left rounded border p-2.5 transition ${selected === b.branch_id ? "border-amber bg-amber/5" : "border-line hover:border-dim"} ${d?.verdict === "DENY" ? "bg-alert/5" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="mono text-xs font-semibold" style={{ color: BRANCH_COLORS[i % 4] }}>{b.branch_id}{rank >= 0 ? ` · #${rank + 1}` : ""}</span>
                {d ? <Stamp verdict={d.verdict} committed={committed} /> : !b.legal ? <span className="mono text-[10px] text-alert">ILLEGAL</span> : null}
              </div>
              <div className="mono text-[11px] mt-1 break-words">{b.label}</div>
              {b.proposer && b.proposer !== "agent" && (
                <div className={`mono text-[10px] mt-0.5 ${/classifier|unvalidated/.test(b.proposer) ? "text-amber" : "text-dim"}`}>
                  proposed by {b.proposer === "bedrock" ? "Bedrock agent" : b.proposer}
                </div>
              )}
              {b.rationale && <p className="text-[11px] text-dim mt-1 line-clamp-3">{b.rationale}</p>}
              {b.outcome && (
                <div className="mono text-[10px] text-dim mt-1.5 grid grid-cols-2 gap-x-2">
                  <span>score <b className="text-ink">{b.outcome.score.toFixed(3)}</b></span>
                  <span>brownouts <b className="text-ink">{b.outcome.brownout_events}</b></span>
                  {pt && <><span>pwr@T+{scrub} <b className="text-ink">{pt.power_kwh.toFixed(1)}</b></span><span>O₂ <b className="text-ink">{pt.oxygen_kg.toFixed(1)}</b></span></>}
                </div>
              )}
              {!b.legal && <p className="text-[10px] text-alert mt-1">{b.violations.join("; ")}</p>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
