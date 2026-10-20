import type { MissionEvent } from "../types";

const LABEL: Record<string, [string, string]> = {
  "mission.started": ["INCIDENT", "text-alert"],
  "agent.started": ["AGENT", "text-cyan"],
  "agent.proposals": ["PROPOSALS", "text-cyan"],
  "fork.created": ["FORK", "text-amber"],
  "fork.screened": ["SCREENED", "text-amber"],
  "agent.explanation": ["EXPLAIN", "text-cyan"],
  "gate.decision": ["DECIDER", "text-ink"],
  "action.committed": ["COMMIT", "text-ok"],
  "action.rejected": ["REFUSED", "text-alert"],
  "mission.advanced": ["TIME", "text-dim"],
  "mission.abstained": ["ABSTAIN", "text-amber"],
  "agent.finished": ["BRIEFING", "text-cyan"],
  "run.status": ["RUN", "text-dim"],
  "review.requested": ["REVIEW", "text-amber"],
  "review.approved": ["APPROVED", "text-ok"],
  "review.rejected": ["REJECTED", "text-alert"],
};

function describe(e: MissionEvent): string {
  const p = e.payload;
  switch (e.type) {
    case "mission.started": return p.title;
    case "agent.proposals": return `${p.proposals.length} candidate action(s) from ${p.proposer === "bedrock" ? "Amazon Bedrock" : p.proposer === "external" ? "automated subsystem (unvalidated)" : "fixed fixture set"}`;
    case "fork.created": return `${p.branches.length} futures × ${p.horizon} ticks; ranked ${p.ranked.join(" > ")}`;
    case "gate.decision": {
      const g = p.answers?.evidence_grounded?.value;
      return `${p.action} → ${p.verdict}${g !== undefined ? ` (grounded ${Number(g).toFixed(2)})` : ` (${p.decider_status})`}`;
    }
    case "action.committed": return `${p.proposal.tool}(${JSON.stringify(p.proposal.args)}) committed → rev ${e.revision}${p.approved_by ? ` (approved by ${p.approved_by})` : ""}`;
    case "action.rejected": return p.reasons?.join("; ");
    case "mission.advanced": return `+${p.ticks} ticks`;
    case "fork.screened": return `every future gated: ${Object.values(p.verdicts).join(" / ")}`;
    case "agent.explanation": return p.error ? `failed: ${p.error}` : p.grounded ? "explanation verified against simulation packet" : `explanation withheld (${p.unsupported_claims.length} unsupported claims)`;
    case "mission.abstained": return "no candidate approved; nothing committed";
    case "review.requested": return `human review requested for ${p.branches.join(", ")}`;
    case "review.approved": return `${p.branch_id} approved by ${p.operator}`;
    case "review.rejected": return `${p.branch_id} rejected by ${p.operator}`;
    case "run.status": return p.status + (p.error ? `: ${p.error}` : "");
    default: return "";
  }
}

export function Timeline({ events }: { events: MissionEvent[] }) {
  return (
    <section className="panel p-4" aria-label="Timeline">
      <h2 className="panel-title mb-2">F · Timeline</h2>
      <ol className="space-y-1 max-h-[260px] overflow-auto pr-1">
        {events.filter(e => LABEL[e.type]).map(e => {
          const [l, c] = LABEL[e.type];
          return (
            <li key={e.seq} className="grid grid-cols-[52px_78px_1fr] gap-2 text-[12px] items-baseline">
              <span className="mono text-dim">T+{String(e.tick).padStart(3, "0")}</span>
              <span className={`mono text-[10px] tracking-wider ${c}`}>{l}</span>
              <span className="text-ink/90 [overflow-wrap:anywhere]">{describe(e)}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
