# Sewer SAM2 Annotator

A **mask detection annotator** built around [SAM 2](https://github.com/facebookresearch/sam2). It is made for instance masks on **videos** (prompt once, track through the clip) and on **still images**.

Prompt a frame or photo, refine the mask, export a training dataset. No CVAT at runtime.

## Features

- Projects, custom labels, and multi-file **video and image** upload
- SAM 2 mask prompts: positive/negative points and boxes
- Brush and eraser, with autosave
- Video tracking forward and backward (stride save; manual frames are kept)
- Exclude frames without rewriting the source video
- Exports: COCO instance, YOLO segmentation, Pascal VOC, native ZIP

## Quick start

NVIDIA GPU + [Docker](https://docs.docker.com/compose/) with NVIDIA Container Toolkit.

```bash
docker compose up --build -d
docker logs -f sewer-annotator-backend
```

Wait for `SAM2 MODEL LOADED SUCCESSFULLY`, then open:

- **UI** — http://localhost:8092
- **API** — http://localhost:8091/docs

Stop without deleting data:

```bash
docker compose down
```

Projects, masks, and media live in the `annotator-data` volume. Weights cache in `sam2-models`. Do not delete those volumes.

## Workflow

1. Create a project and upload media.
2. Pick a label. Click a defect (`+`), exclude background (`−`), draw a box, or paint with brush/eraser.
3. Track forward or backward. Default stride is every 5 frames.
4. Open a generated thumbnail to inspect or correct it. Saved edits are `manual` and survive re-tracking.
5. Export COCO, YOLO, VOC, or a native backup.

## Stack

React 19 · TypeScript · FastAPI · SQLite · SAM 2.1 Hiera Small · CUDA

See [doc/architecture.md](doc/architecture.md) for the data model and request flow.

## Development

Backend tests (no GPU):

```bash
cd backend
uv sync --group dev
uv run pytest
```

Frontend (proxies `/api` to `:8091`):

```bash
cd frontend
npm install
npm run dev
```
