# AGENTS.md

Instructions for coding agents working on **Sewer SAM2 Annotator v2**.

This file is the portable agent brief ([AGENTS.md](https://agents.md/), Cursor, Codex). Cursor also loads project rules from `.cursor/rules/*.mdc`. Read `doc/architecture.md` before changing data flow, SAM2, tracking, or persistence.

## What this repo is

Standalone sewer CCTV annotation: React + TypeScript UI, FastAPI backend, SQLite, Docker, SAM2.1 Hiera Small. It does **not** require CVAT at runtime. Exports (COCO instance, YOLO seg, Pascal VOC masks, native backup) are the interchange path.

## Layout

- `frontend/` — Vite + React 19 + TypeScript. Production image is nginx, which proxies `/api` to the backend.
- `backend/app/` — FastAPI app. Routes under `app/api/routes/`, logic in `app/services/`.
- `compose.yaml` — `backend` on host **8091**, `frontend` on host **8092**.
- `doc/architecture.md` — system design, data model, request flows.

## Commands

Prefer Docker; the backend needs CUDA and the SAM2 package cloned in the image.

```bash
docker compose build
docker compose up -d
docker logs -f sewer-annotator-backend
```

Wait for `SAM2 MODEL LOADED SUCCESSFULLY`. UI: `http://localhost:8092`. API docs: `http://localhost:8091/docs`.

Backend Python deps are `backend/pyproject.toml` + `backend/uv.lock`. After changing dependencies:

```bash
cd backend
uv lock
```

Rebuild the backend image so Docker picks up the lockfile. Local tests (no GPU / no SAM2):

```bash
cd backend
uv sync --group dev
uv run pytest
```

Frontend-only (proxies `/api` to `http://localhost:8091`):

```bash
cd frontend
npm install
npm run dev
npm run build
```

When you add behavior, add tests next to the change and run them before claiming done. Frontend typecheck is `npm run build` (`tsc --noEmit` then Vite).

## Non-negotiables

- Do not introduce a CVAT runtime dependency. Leftover files (`backend/app/services/cvat_service.py`, `backend/app/api/routes/tasks.py`, `backend/app/api/routes/health.py`, unused models in `backend/app/schemas/models.py`) are **not** on the live router. Do not wire them in unless the user asks.
- Do not delete Docker volumes `annotator-data` or `sam2-models`.
- Do not rewrite source videos. Frame “delete” is `excluded_frames`; annotations are removed only when `delete_annotations` is true.
- SAM2 GPU work is serialized (`Sam2Runtime.lock` + tracking `ThreadPoolExecutor(max_workers=1)`). Do not add parallel CUDA jobs.
- Tracking stride persists masks on seed/step/end frames only; SAM2 still processes intermediate frames for memory. `source='manual'` frames are not overwritten by auto tracking.
- Match the style of the file you edit. New modules should follow the clearer layout in `backend/app/services/export_service.py`, not the densely packed one-liners.
- Keep business logic in services. Routes validate, call a service, map errors to HTTP.
- Frontend API calls go through `frontend/src/api/client.ts`. Types live in `frontend/src/types.ts`.

## Persistence

All app data is under `DATA_ROOT` (Docker: `/data` → volume `annotator-data`): `annotator.db`, `media/`, `masks/`, `exports/`. Hugging Face / SAM2 weights cache in `sam2-models`. Never commit `.env`, masks, media, or model caches.

## Source control

Use Mercurial (`hg`) by default. Do not commit unless the user asks. Do not push unless the user asks.

## Role split

Codex is used for architecture, planning, review, and verification. This Cursor agent implements the agreed plan without silently redesigning it. If the plan is impossible, stop and report the blocker with evidence.
