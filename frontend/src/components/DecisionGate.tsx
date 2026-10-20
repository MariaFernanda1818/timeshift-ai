import type { DecisionView } from "../types";
import { Stamp } from "./FutureExplorer";

function ProbBar({ p, deny, proceed }: { p: number; deny: number; proceed: number }) {
  const tone = p >= proceed ? "var(--color-ok)" : p < deny ? "var(--color-alert)" : "var(--color-amber)";
  return (
    <div className="relative h-5 rounded bg-line/70 overflow-hidden" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={p} aria-label="P(evidence grounded)">
      <div className="absolute inset-y-0 left-0 transition-[width] duration-700" style={{ width: `${p * 100}%`, background: tone, opacity: 0.85 }} />
      <div className="absolute inset-y-0 border-l border-dashed border-alert" style={{ left: `${deny * 100}%` }} title={`deny below ${deny}`} />
      <div className="absolute inset-y-0 border-l border-dashed border-ok" style={{ left: `${proceed * 100}%` }} title={`proceed at ${proceed}`} />
      <span className="absolute right-1.5 top-0.5 mono text-[11px] text-ink">{p.toFixed(3)}</span>
    </div>
  );
}

export function DecisionGate({ d, all = [], onPick, pending, deciderHealth }: { d: DecisionView | null; all?: DecisionView[]; onPick?: (d: DecisionView) => void; pending: boolean; deciderHealth: any }) {
  const healthy = deciderHealth?.status === "ok";
  return (
    <section className="panel p-4" aria-label="Decision gate">
      <div className="flex items-center justify-between gap-2">
        <h2 className="panel-title">E · Decision gate · Strands Decider 2B</h2>
        <span className={`mono text-[10px] px-1.5 py-0.5 rounded border ${healthy ? "border-ok text-ok" : "border-alert text-alert"}`}>
          {healthy ? `LIVE · ${deciderHealth.device}` : deciderHealth ? `DECIDER ${String(deciderHealth.status).toUpperCase()}` : "CHECKING"}
        </span>
      </div>
      {all.length > 1 && (
        <div className="mt-2 flex flex-wrap gap-1.5" role="tablist" aria-label="Gate decisions">
          {all.map((x, i) => (
            <button key={i} role="tab" aria-selected={x === d} onClick={() => onPick?.(x)}
              className={`mono text-[10px] px-1.5 py-0.5 rounded border ${x === d ? "border-amber text-amber" : "border-line text-dim"}`}>
              #{i + 1} {x.proposal.tool} · <span className={x.verdict === "PROCEED" ? "text-ok" : x.verdict === "DENY" ? "text-alert" : "text-amber"}>{x.verdict}</span>
            </button>
          ))}
        </div>
      )}
      {!d && <p className="mt-4 text-sm text-dim">{pending ? "Decider is evaluating the proposed action… (CPU inference can take tens of seconds)" : "No decision yet."}</p>}
      {d && (() => {
        const g = d.answers.evidence_grounded;
        const v = d.answers.verdict;
        const q = d.questions.evidence_grounded;
        return (
          <div className="mt-3 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="mono text-xs text-dim">proposed action · tick {d.tick} · rev {d.revision}</div>
                <div className="mono text-sm break-words">{d.action}</div>
              </div>
              <Stamp verdict={d.verdict} />
            </div>
            <div className="text-[12px] text-dim">
              <span className="text-ink">Evidence cited:</span>{" "}
              {d.trusted_evidence_refs.map(e => <span key={e} className="mono text-ok mr-1">{e}✓</span>)}
              {d.untrusted_evidence_refs.map(e => <span key={e} className="mono text-amber mr-1">{e}⚠ unverified</span>)}
              {!d.trusted_evidence_refs.length && !d.untrusted_evidence_refs.length && <span className="mono">none</span>}
            </div>
            {g ? (
              <div>
                <div className="text-[12px] mb-1"><span className="mono text-cyan">noul</span> · {q?.instructions}</div>
                <ProbBar p={Number(g.value)} deny={d.thresholds.deny_below} proceed={d.thresholds.proceed_at} />
                <div className="mono text-[10px] text-dim mt-1 flex justify-between"><span>deny &lt; {d.thresholds.deny_below}</span><span>review</span><span>proceed ≥ {d.thresholds.proceed_at}</span></div>
              </div>
            ) : (
              <p className="text-sm text-amber">Decider not consulted ({d.decider_status}). The deterministic policy decided.</p>
            )}
            {v?.probabilities && (
              <div>
                <div className="text-[12px] mb-1"><span className="mono text-cyan">choice</span> · verdict question (model confidence {v.confidence?.toFixed(2)}; not a calibrated accuracy)</div>
                <div className="flex gap-1.5">
                  {Object.entries(v.probabilities).map(([k, p]) => (
                    <div key={k} className={`flex-1 rounded border px-1.5 py-1 mono text-[10px] ${k === v.value ? "border-cyan" : "border-line"}`}>
                      {k} <b>{(p as number).toFixed(2)}</b>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {d.hard_violations.length > 0 && (
              <div className="rounded border border-alert/50 bg-alert/10 p-2 text-[12px]">
                <div className="mono text-[10px] text-alert mb-1">DETERMINISTIC POLICY (authoritative)</div>
                {d.hard_violations.map(h => <div key={h}>{h}</div>)}
              </div>
            )}
            <ul className="text-[12px] text-dim list-disc pl-4">{d.reasons.map(r => <li key={r}>{r}</li>)}</ul>
            <div className="mono text-[10px] text-dim grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-line pt-2">
              <span>status {d.decider_status}</span>
              <span>latency {d.decider_latency_ms ? `${(d.decider_latency_ms / 1000).toFixed(1)} s` : "—"}</span>
              <span className="col-span-2 truncate">checkpoint {d.decider_checkpoint ?? "—"}</span>
              <span>input tokens {d.decider_input_tokens ?? "—"}</span>
              <span>state {d.state_hash}</span>
            </div>
          </div>
        );
      })()}
    </section>
  );
}
