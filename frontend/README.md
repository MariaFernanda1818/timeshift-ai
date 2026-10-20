# TIME//SHIFT dashboard

React + TypeScript + Vite + Tailwind + React Three Fiber. Event-driven: every panel is derived
from the mission event stream (live SSE from `/api/missions/{id}/events`, or a recorded run from
`/api/replays/{name}`).

```bash
npm ci
npm run dev      # proxies /api to http://127.0.0.1:8080
npm run build    # served by the FastAPI app from frontend/dist
```
