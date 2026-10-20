"""Fixed candidate sets ("scripted proposer").

These are HAND-WRITTEN proposals, not Bedrock output. They exist so that the benchmark and
offline replays use identical candidates across configurations, and so the signature
scenario can be exercised while Bedrock is unavailable. Every run that uses them records
`proposer = "fixture"` in its events. Live runs use the Bedrock proposer instead.
"""

from __future__ import annotations

from typing import Any

FIXTURE_PROPOSALS: dict[str, list[dict[str, Any]]] = {
    "solar_cascade": [
        {"tool": "activate_backup_power", "args": {},
         "rationale": "Generation is below load and the reserve is draining (E000-PWR); the "
                      "backup bank (E000-BKP) adds 6 kW and prevents brownout.",
         "cited_evidence": ["E000-PWR", "E000-BKP"]},
        {"tool": "repair_solar_array", "args": {"crew_id": "C3"},
         "rationale": "SOLAR is damaged at 45% integrity (E000-MOD-SOLAR); Eng. Ramos is "
                      "healthy (E000-CREW-C3) and a repair kit is available (E000-KITS).",
         "cited_evidence": ["E000-MOD-SOLAR", "E000-CREW-C3", "E000-KITS"]},
        {"tool": "isolate_module", "args": {"module_id": "HAB"},
         "rationale": "HAB has a hull micro-fracture causing excess heater load (R-HAB-01); "
                      "isolating it removes 4.5 kW of load and stops the drain.",
         "cited_evidence": ["R-HAB-01"], "proposer": "anomaly-classifier v0.3 (unvalidated)"},
    ],
    "oxygen_leak": [
        {"tool": "isolate_module", "args": {"module_id": "GREENHOUSE"},
         "rationale": "GREENHOUSE is breached at 40% integrity (E000-MOD-GREENHOUSE) and O2 "
                      "is falling (E000-O2); sealing it stops the leak.",
         "cited_evidence": ["E000-MOD-GREENHOUSE", "E000-O2"]},
        {"tool": "isolate_module", "args": {"module_id": "LAB"},
         "rationale": "The leak is probably in the LAB ventilation ducting.",
         "cited_evidence": []},
        {"tool": "activate_backup_power", "args": {},
         "rationale": "More power lets life support produce more oxygen (E000-O2).",
         "cited_evidence": ["E000-O2"]},
    ],
    "reactor_overheat": [
        {"tool": "reroute_power", "args": {"source_module": "LAB", "target_module": "REACTOR"},
         "rationale": "REACTOR coolant pumps are unpowered (E000-MOD-REACTOR) and the core is "
                      "at 790 C (E000-RX); shedding LAB restores pump power.",
         "cited_evidence": ["E000-MOD-REACTOR", "E000-RX", "E000-MOD-LAB"]},
        {"tool": "vent_reactor", "args": {},
         "rationale": "The core is at 790 C (E000-RX); an emergency vent drops it 160 C now.",
         "cited_evidence": ["E000-RX"]},
        {"tool": "activate_backup_power", "args": {},
         "rationale": "Backup power will cool the reactor.",
         "cited_evidence": ["E000-BKP"]},
    ],
}
