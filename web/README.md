# SynthPost Studio frontend

The Studio is a React/Vite client for the local FastAPI backend. Cross-runtime domain types come from `contracts/typescript`; all HTTP calls go through `src/api/client.ts` and shared transport/error handling in `src/api/http.ts`.

`useStudio` owns only app selection, shared server snapshots, and refresh orchestration. `useJobEvents` owns EventSource parsing and notifications. Workspace panels own feature-specific fetch/edit state. Presentation components must not call `fetch` or access SQLite/files directly. Preserve the existing workflow and responsive design when refactoring.

```bash
npm install
npm run dev
npm run typecheck
npm run build
```
