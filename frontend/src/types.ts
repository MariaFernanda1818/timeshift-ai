// Mirrors timeshift.mission.Event and the payloads emitted by the orchestrator.

export interface MissionEvent {
  seq: number;
  ts: number;
  mission_id: string;
  tick: number;
  revision: number;
  type: string;
  payload: Record<string, any>;
}

export interface ModuleState {
  module_id: string;
  name: string;
  status: "nominal" | "damaged" | "breached" | "isolated" | "destroyed";
  integrity_pct: number;
  powered: boolean;
  load_kw: number;
  critical: boolean;
}

export interface CrewState {
  crew_id: string;
  name: string;
  location: string;
  health_pct: number;
  on_eva: boolean;
}

export interface MissionStateSnap {
  mission_id: string;
  scenario_id: string;
  seed: number;
  tick: number;
  revision: number;
  oxygen_reserve_kg: number;
  oxygen_capacity_kg: number;
  power_reserve_kwh: number;
  power_capacity_kwh: number;
  reactor_temp_c: number;
  reactor_online: boolean;
  backup_active: boolean;
  backup_charge_kwh: number;
  repair_kits: number;
  coolant_vents_remaining: number;
  modules: ModuleState[];
  crew: CrewState[];
  incident_log: string[];
  sim_version: string;
  state_hash?: string;
}

export interface SeriesPoint {
  tick: number;
  oxygen_kg: number;
  power_kwh: number;
  reactor_c: number;
  crew_health: number;
}

export interface Outcome {
  crew_alive: number;
  crew_total: number;
  mean_crew_health_pct: number;
  oxygen_kg: number;
  power_kwh: number;
  min_power_kwh: number;
  reactor_temp_c: number;
  peak_reactor_temp_c: number;
  reactor_online: boolean;
  brownout_events: number;
  resources_used: number;
  score: number;
  components: Record<string, number>;
}

export interface BranchView {
  branch_id: string;
  label: string;
  action: { tool: string; args: Record<string, unknown> } | null;
  proposal_id: string | null;
  proposer?: string | null;
  rationale: string;
  cited_evidence: string[];
  legal: boolean;
  violations: string[];
  outcome: Outcome | null;
  series: SeriesPoint[];
  events: string[];
  final_state: MissionStateSnap | null;
}

export interface ForkView {
  fork_id: string;
  origin_tick: number;
  origin_revision: number;
  origin_hash: string;
  seed: number;
  horizon: number;
  sim_version: string;
  weights: Record<string, number>;
  ranked: string[];
  branches: BranchView[];
}

export interface AnswerView {
  name: string;
  type: string;
  value: number | string;
  probabilities?: Record<string, number> | null;
  confidence?: number | null;
}

export interface DecisionView {
  mission_id: string;
  tick: number;
  revision: number;
  state_hash: string;
  fork_id: string | null;
  proposal: { proposal_id: string; tool: string; args: Record<string, unknown>; rationale: string; cited_evidence: string[] };
  action: string;
  trusted_evidence_refs: string[];
  untrusted_evidence_refs: string[];
  decider_model: string | null;
  decider_checkpoint: string | null;
  decider_status: string;
  questions: Record<string, { type: string; instructions: string; criteria: any }>;
  answers: Record<string, AnswerView>;
  thresholds: { proceed_at: number; deny_below: number; verdict_deny_conf: number };
  hard_violations: string[];
  verdict: "PROCEED" | "REVIEW" | "DENY";
  reasons: string[];
  decider_latency_ms: number | null;
  decider_input_tokens: number | null;
  wall_latency_ms: number | null;
}
