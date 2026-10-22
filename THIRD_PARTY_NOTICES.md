# Third-party notices

This repository's own code is MIT-licensed (see `LICENSE`). It depends on, but does not
redistribute, the following components:

| Component | Use | License |
|---|---|---|
| [strands-decider](https://github.com/strands-labs/strands-decider) (git `930e6d5`) | Decider server/CLI, installed at setup time | Apache-2.0 |
| `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` checkpoint and its base `Qwen/Qwen3.5-2B-Base` | Downloaded from Hugging Face at runtime; **not included in this repository** | see the respective model cards |
| [Strands Agents SDK](https://github.com/strands-agents/sdk-python) | agent framework | Apache-2.0 |
| Amazon Bedrock, Anthropic Claude Haiku 4.5 | LLM via AWS | AWS service terms |
| FastAPI, Uvicorn, Pydantic, boto3, psutil | backend | MIT / BSD / Apache-2.0 (see each package) |
| React, Vite, Tailwind CSS, three.js, @react-three/fiber, @react-three/drei | frontend | MIT |
| IBM Plex Sans / Mono (Google Fonts, loaded at runtime) | typography | SIL Open Font License 1.1 |

The lunar-base scenario, telemetry and benchmark cases are synthetic and were written for this
project. No real mission, customer or employer data is used.
