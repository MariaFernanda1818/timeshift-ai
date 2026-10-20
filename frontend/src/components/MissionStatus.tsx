import type { MissionStateSnap } from "../types";

function Gauge({ label, value, max, unit, warnBelow, alertBelow, invert = false, decimals = 1 }: {
  label: string; value: number; max: number; unit: string;
  warnBelow?: number; alertBelow?: number; invert?: boolean; decimals?: number;
}) {
  const pct = Math.max(0, Math.min(1, value / max));
  let tone = "var(--color-cyan)";
  const v = invert ? max - value : value;
  if (alertBelow !== undefined && v < alertBelow) tone = "var(--color-alert)";
  else if (warnBelow !== undefined && v < warnBelow) tone = "var(--color-amber)";
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="panel-title truncate">{label}</span>
        <span className="mono text-sm tabular-nums" style={{ color: tone }}>
          {value.toFixed(decimals)}<span className="text-dim text-xs"> {unit}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1.5 rounded bg-line overflow-hidden">
        <div className="h-full transition-[width] duration-700" style={{ width: `${pct * 100}%`, background: tone }} />
      </div>
    </div>
  );
}

export function MissionStatus({ s, emergency }: { s: MissionStateSnap | null; emergency: string }) {
  if (!s) return <div className="panel p-4 text-dim text-sm">No mission loaded.</div>;
  const alive = s.crew.filter(c => c.health_pct > 0).length;
  const health = s.crew.reduce((a, c) => a + c.health_pct, 0) / s.crew.length;
  const minutes = s.tick * 5;
  return (
    <section className="panel p-4" aria-label="Mission status">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="panel-title">A · Mission status</h2>
        <span className="mono text-xs text-dim">
          T+{String(Math.floor(minutes / 60)).padStart(2, "0")}:{String(minutes % 60).padStart(2, "0")} · tick {s.tick} · rev {s.revision}
        </span>
      </div>
      <div className="mb-3 rounded border border-alert/40 bg-alert/10 px-3 py-2 text-sm flex gap-2 items-center">
        <span className="h-2 w-2 rounded-full bg-alert pulse-alert shrink-0" aria-hidden />
        <span className="truncate">{emergency}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-5 gap-y-3">
        <Gauge label="Oxygen" value={s.oxygen_reserve_kg} max={s.oxygen_capacity_kg} unit="kg" warnBelow={15} alertBelow={9} />
        <Gauge label="Power reserve" value={s.power_reserve_kwh} max={s.power_capacity_kwh} unit="kWh" warnBelow={6} alertBelow={2} />
        <Gauge label="Reactor" value={s.reactor_temp_c} max={1100} unit="°C" invert warnBelow={300} alertBelow={200} decimals={0} />
        <Gauge label="Crew health" value={health} max={100} unit="%" warnBelow={80} alertBelow={50} decimals={0} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 mono text-[11px] text-dim">
        <span>CREW <b className="text-ink">{alive}/{s.crew.length}</b></span>
        <span>REACTOR <b className={s.reactor_online ? "text-ok" : "text-alert"}>{s.reactor_online ? "ONLINE" : "SCRAM"}</b></span>
        <span>BACKUP <b className={s.backup_active ? "text-amber" : "text-ink"}>{s.backup_active ? "ACTIVE" : "STBY"}</b></span>
      </div>
    </section>
  );
}
