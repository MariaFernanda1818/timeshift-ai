import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Suspense, useMemo, useRef, useState } from "react";
import type * as THREE from "three";
import type { MissionStateSnap, ModuleState } from "../types";

const LAYOUT: Record<string, { x: number; z: number; shape: "dome" | "box" | "cyl" | "solar" | "dish" }> = {
  HAB: { x: 0, z: 0, shape: "dome" },
  LAB: { x: 2.4, z: 0.4, shape: "box" },
  GREENHOUSE: { x: -2.4, z: 0.4, shape: "dome" },
  LIFE_SUPPORT: { x: 0, z: 2.2, shape: "cyl" },
  REACTOR: { x: 4.2, z: -2.6, shape: "cyl" },
  COMMS: { x: -1.6, z: -2.2, shape: "dish" },
  SOLAR: { x: -4.6, z: -1.8, shape: "solar" },
};

export function statusColor(m: ModuleState): string {
  if (m.status === "destroyed") return "#3a3f4b";
  if (m.status === "isolated") return "#55627a";
  if (m.status === "breached") return "#ff4d4f";
  if (m.status === "damaged") return "#f2a93b";
  return m.powered ? "#47d4e8" : "#2a5560";
}

function ModuleMesh({ m, selected, onSelect }: { m: ModuleState; selected: boolean; onSelect: () => void }) {
  const pos = LAYOUT[m.module_id] ?? { x: 0, z: 0, shape: "box" as const };
  const ref = useRef<THREE.Mesh>(null);
  const color = statusColor(m);
  const alarm = m.status === "breached" || m.status === "damaged";
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const mat = ref.current.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = alarm ? 0.35 + 0.35 * Math.sin(clock.elapsedTime * 4) : m.powered ? 0.25 : 0.02;
  });
  const common = { ref, onClick: (e: any) => { e.stopPropagation(); onSelect(); } };
  const mat = <meshStandardMaterial color={color} emissive={color} roughness={0.55} metalness={0.25} transparent opacity={m.status === "isolated" ? 0.45 : 1} />;
  return (
    <group position={[pos.x, 0, pos.z]}>
      {pos.shape === "dome" && <mesh {...common} position={[0, 0, 0]}><sphereGeometry args={[0.9, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />{mat}</mesh>}
      {pos.shape === "box" && <mesh {...common} position={[0, 0.4, 0]}><boxGeometry args={[1.5, 0.8, 1]} />{mat}</mesh>}
      {pos.shape === "cyl" && <mesh {...common} position={[0, 0.5, 0]}><cylinderGeometry args={[0.55, 0.65, 1, 24]} />{mat}</mesh>}
      {pos.shape === "dish" && <mesh {...common} position={[0, 0.6, 0]} rotation={[0.6, 0, 0]}><coneGeometry args={[0.6, 0.35, 24, 1, true]} />{mat}</mesh>}
      {pos.shape === "solar" && (
        <group>
          {[-0.9, 0, 0.9].map(dx => (
            <mesh key={dx} {...(dx === 0 ? common : { onClick: common.onClick })} position={[dx, 0.35, 0]} rotation={[-0.9, 0, 0]}>
              <boxGeometry args={[0.8, 1.1, 0.05]} />{mat}
            </mesh>
          ))}
        </group>
      )}
      {selected && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}><ringGeometry args={[1.05, 1.15, 48]} /><meshBasicMaterial color="#f2a93b" /></mesh>}
    </group>
  );
}

function Corridors() {
  const pairs: [string, string][] = [["HAB", "LAB"], ["HAB", "GREENHOUSE"], ["HAB", "LIFE_SUPPORT"], ["HAB", "COMMS"], ["LAB", "REACTOR"], ["COMMS", "SOLAR"]];
  return (
    <>
      {pairs.map(([a, b]) => {
        const A = LAYOUT[a], B = LAYOUT[b];
        const dx = B.x - A.x, dz = B.z - A.z, len = Math.hypot(dx, dz);
        return (
          <mesh key={a + b} position={[(A.x + B.x) / 2, 0.08, (A.z + B.z) / 2]} rotation={[0, -Math.atan2(dz, dx), 0]}>
            <boxGeometry args={[len, 0.12, 0.18]} />
            <meshStandardMaterial color="#1c2a44" />
          </mesh>
        );
      })}
    </>
  );
}

function canWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

export function LunarBase({ s, ghost }: { s: MissionStateSnap | null; ghost?: string | null }) {
  const [mode, setMode] = useState<"3d" | "2d">(() => (canWebGL() ? "3d" : "2d"));
  const [sel, setSel] = useState<string | null>(null);
  const selected = useMemo(() => s?.modules.find(m => m.module_id === sel) ?? null, [s, sel]);
  return (
    <section className="panel p-3 flex flex-col min-h-[300px]" aria-label="Lunar base">
      <div className="flex items-center justify-between mb-2 gap-2">
        <h2 className="panel-title">B · Lunar base {ghost && <span className="text-amber normal-case tracking-normal">· viewing {ghost}</span>}</h2>
        <button className="mono text-[11px] px-2 py-0.5 rounded border border-line hover:border-cyan" onClick={() => setMode(mode === "3d" ? "2d" : "3d")}>
          {mode === "3d" ? "2D view" : "3D view"}
        </button>
      </div>
      <div className="relative flex-1 min-h-[240px] rounded overflow-hidden bg-[radial-gradient(ellipse_at_top,#101a33,#05080f)]">
        {!s ? <div className="absolute inset-0 grid place-items-center text-dim text-sm">Awaiting telemetry</div> :
          mode === "3d" ? (
            <Canvas camera={{ position: [0, 5.2, 7.2], fov: 50 }} dpr={[1, 1.75]} onPointerMissed={() => setSel(null)}>
              <Suspense fallback={null}>
                <ambientLight intensity={0.35} />
                <directionalLight position={[-6, 8, 4]} intensity={1.1} />
                <mesh rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[8, 64]} /><meshStandardMaterial color="#1a1f2b" roughness={1} /></mesh>
                <Corridors />
                {s.modules.map(m => <ModuleMesh key={m.module_id} m={m} selected={sel === m.module_id} onSelect={() => setSel(m.module_id)} />)}
                <OrbitControls enablePan={false} minDistance={6} maxDistance={18} maxPolarAngle={1.35} autoRotate autoRotateSpeed={0.25} />
              </Suspense>
            </Canvas>
          ) : <Schematic s={s} sel={sel} onSelect={setSel} />}
        <div className="absolute left-2 bottom-2 right-2 flex flex-wrap gap-1.5">
          {s?.modules.map(m => (
            <button key={m.module_id} onClick={() => setSel(m.module_id)}
              className="mono text-[10px] px-1.5 py-0.5 rounded bg-void/80 border"
              style={{ borderColor: statusColor(m), color: statusColor(m) }}>
              {m.module_id} {m.status !== "nominal" ? m.status.toUpperCase() : m.powered ? "" : "OFF"}
            </button>
          ))}
        </div>
      </div>
      {selected && s && (
        <div className="mt-2 mono text-[11px] text-dim grid grid-cols-2 gap-x-3">
          <span className="text-ink col-span-2">{selected.name}</span>
          <span>status {selected.status}</span><span>integrity {selected.integrity_pct.toFixed(0)}%</span>
          <span>powered {selected.powered ? "yes" : "no"}</span><span>load {selected.load_kw} kW</span>
          <span className="col-span-2">crew: {s.crew.filter(c => c.location === selected.module_id && !c.on_eva).map(c => c.name).join(", ") || "none"}</span>
        </div>
      )}
    </section>
  );
}

function Schematic({ s, sel, onSelect }: { s: MissionStateSnap; sel: string | null; onSelect: (id: string) => void }) {
  const X = (x: number) => 50 + x * 9, Y = (z: number) => 50 + z * 9;
  return (
    <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" role="img" aria-label="Base schematic">
      {s.modules.map(m => {
        const p = LAYOUT[m.module_id];
        if (!p) return null;
        return (
          <g key={m.module_id} onClick={() => onSelect(m.module_id)} className="cursor-pointer">
            <circle cx={X(p.x)} cy={Y(p.z)} r={sel === m.module_id ? 6.5 : 5.5} fill="none" stroke={statusColor(m)} strokeWidth={0.8} />
            <text x={X(p.x)} y={Y(p.z) + 1} textAnchor="middle" fontSize="2.6" fill={statusColor(m)} fontFamily="IBM Plex Mono">{m.module_id.slice(0, 5)}</text>
          </g>
        );
      })}
    </svg>
  );
}
