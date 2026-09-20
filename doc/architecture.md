# Architecture

Sewer SAM2 Annotator v2 is a two-container annotation product: a React UI and a FastAPI + SAM2 backend. CVAT is not part of the runtime. Dataset interchange is export ZIPs.

## Runtime topology

```text
Browser :8092
   |
   +-- frontend (nginx :80)
   |      static Vite build
   |      /api  -->  backend:8090/api
   |
   +-- backend (uvicorn :8090, host-mapped 8091)
          FastAPI
          SQLite /data/annotator.db
          uploaded media, mask PNGs, export ZIPs
          SAM2.1 Hiera Small on CUDA
```

`compose.yaml` services:

| Service    | Image role                         | Host port | Container port | GPU |
|------------|------------------------------------|-----------|----------------|-----|
| `backend`  | PyTorch CUDA runtime + SAM2 + app  | 8091      | 8090           | all |
| `frontend` | nginx serving `frontend/dist`      | 8092      | 80             | no  |

Volumes:

- `annotator-data` → `/data` (database, media, masks, exports)
- `sam2-models` → `/models` (Hugging Face / SAM2 cache via `HF_HOME=/models/huggingface`)

Local Vite (`frontend/vite.config.ts`) proxies `/api` to `http://localhost:8091` so `frontend/src/api/client.ts` can use a relative `/api` prefix in both Docker and `npm run dev`.

## Process layout

```text
annotator/
  compose.yaml
  frontend/                 React 19 + Vite 6 + TypeScript
    src/App.tsx             views: projects, project, annotate
    src/api/client.ts       fetch wrappers
    src/types.ts            shared UI types
    src/components/AnnotationCanvas.tsx
    nginx.conf              /api reverse proxy, 20G uploads, 3600s timeouts
  backend/
    Dockerfile              pytorch/pytorch:2.5.1-cuda12.1 + cloned facebookresearch/sam2
    app/main.py             FastAPI, CORS, lifespan: DB + SAM2 init
    app/core/settings.py    DATA_ROOT, model id, JPEG quality, tracking default step
    app/core/db.py          SQLite WAL schema
    app/api/router.py       mounts live /api routers
    app/api/routes/         HTTP adapters
    app/services/           domain logic
    app/utils/images.py     mask PNG / overlay helpers
```

Live routers (from `app/api/router.py`): `projects`, `media`, `annotations`, `prompts`, `tracking`, `exports`. Plus `GET /health` on the app (not under `/api`).

## Layers

1. **UI** — `App.tsx` holds view and editor state. The canvas is a mask overlay; SAM2 returns PNG overlays; brush/eraser paint locally; save posts a PNG data URL.
2. **HTTP** — FastAPI routes parse Pydantic bodies, call one service, return JSON, JPEG, PNG, or ZIP.
3. **Services** — singleton objects (`project_service`, `media_service`, `annotation_service`, `tracking_service`, `sam2_runtime`, `export_service`).
4. **Store** — SQLite rows + files on disk. Annotation rows point at mask PNGs; they do not store polygons as the source of truth.

Do not put SAM2 or OpenCV work in route modules. Do not have the UI talk to SQLite or the filesystem.

## Data model

SQLite path: `{DATA_ROOT}/annotator.db`. Foreign keys on. Schema in `backend/app/core/db.py`.

```text
projects 1──* labels
    │
    └──* media 1──* annotations
              └──* excluded_frames
```

| Table              | Role |
|--------------------|------|
| `projects`         | Named annotation job |
| `labels`           | Per-project defect class + color. Unique `(project_id, name)`. Cannot delete a label that still has annotations. |
| `media`            | `kind` is `video` or `image`. Videos stay as original files; frames decode on demand. `annotation_complete` is a manual Done flag (`0`/`1`). Stills stay separate rows; the UI groups them as one Pictures album that is complete only when every still is flagged. |
| `annotations`      | One binary mask PNG per instance. `source` is `manual` or `auto`. `track_group` groups a tracking run. |
| `excluded_frames`  | Soft-delete of a frame from UI dataset/export. Source video is never rewritten. |

Default labels on project create: Root, Crack, Obstacle, Deposits, Deformed, Broken, Joint Displaced, Surface Damage.

Disk layout under `/data`:

```text
annotator.db
media/{project_id}/{uuid}{ext}
masks/{media_id}/{uuid}.png
exports/{project-name}-{fmt}-{token}.zip
```

## API map

Base path `/api`.

| Area | Methods | Notes |
|------|---------|--------|
| Projects | `GET/POST /projects`, `GET/DELETE /projects/{pid}` | Create seeds default labels |
| Labels | `POST /projects/{pid}/labels`, `DELETE .../labels/{lid}` | 409 if label in use |
| Upload | `POST /projects/{pid}/media` | `multipart/form-data` field `files` |
| Media | `GET/PATCH/DELETE /media/{mid}` | PATCH `{annotation_complete}` is videos only |
| Frames | `GET /media/{mid}/frame/{n}`, `GET /media/{mid}/frames` | Optional `thumb=` for JPEG thumbs |
| Project stills | `PATCH /projects/{pid}/images/complete`, `DELETE /projects/{pid}/images` | Album Done flag; delete stills only |
| Exclude | `POST /media/{mid}/frames/{n}/exclude` | `{excluded, delete_annotations}` |
| Annotations | `GET /annotations/media/{mid}`, `POST /annotations/masks`, `DELETE /annotations/{id}` | Mask PNG and thumbnail JPEG endpoints |
| Prompts | `POST /prompts/sessions`, `POST .../predict`, `DELETE .../{sid}` | SAM2 interactive mask |
| Tracking | `POST /tracking`, `GET /tracking/{jid}`, `DELETE /tracking/{jid}` | Async job, poll ~700ms from UI |
| Exports | `POST /exports`, `GET /exports/{jid}`, `GET /exports/{jid}/download`, `GET /exports/projects/{pid}/{fmt}` | Job-based ZIP with progress. Formats: `coco`, `yolo`, `voc`, `native` |

`POST /annotations/masks` body: `media_id`, `frame`, `label_id`, `mask_png_data_url`, optional `replace_annotation_id`, `source` (UI always sends `manual`).

## SAM2

Model: `facebook/sam2.1-hiera-small` via `SAM2VideoPredictor.from_pretrained`. CUDA is required at backend startup.

VRAM policy (8 GB class GPUs such as RTX 3070 Ti):

- `offload_video_to_cpu=True` and `offload_state_to_cpu=True` on `init_state`
- `torch.bfloat16` autocast
- one `threading.RLock` around predictor use
- tracking pool `max_workers=1`

### Interactive prompt

1. UI `createPrompt(mediaId, frame, annotationId?)`.
2. Backend writes that frame as `000000.jpg` in a temp dir and `init_state`s a one-frame “video”.
3. Optional existing mask is `add_new_mask`.
4. Points (normalized) and/or box go through `add_new_points_or_box`.
5. Response is an RGBA overlay PNG, not a boolean array.
6. Session lives until the UI deletes it (frame change, clear, unmount).

### Video tracking

1. UI requires a **saved** seed annotation, a different target frame, and `frame_step` (default 5).
2. Backend extracts JPEG frames for the inclusive range into a temp dir.
3. Seed mask is added on the local seed index; `propagate_in_video` runs forward or reverse.
4. Every frame is processed. Only frames matching `abs(f-start) % step == 0`, plus the end frame, are kept (seed itself is skipped in the result set).
5. If `replace_auto_masks`, auto annotations in that range for the same label are deleted; **manual** frames are never replaced (`bulk_save` skips frames that already have non-auto annotations).
6. New rows get `source='auto'` and a `track_group` like `sam2-{jobid}`.

Editing a tracked mask and saving it sets `source='manual'`, so later tracks preserve that keyframe.

## Frontend

Views are in-memory (`projects` | `project` | `annotate`); there is no client router.

- Autosave (default on, 3s) posts only when the mask is dirty.
- Nearby frame strip requests a window around the current frame (`start = frame-10`, limit 28).
- Brush default 15 px; canvas coordinates are image pixels, not CSS pixels.
- Autosave interval is stored in `localStorage`.

## Exports

`ExportService.start` runs on a one-worker thread pool and reports percent + “Preparing the export”. `build_many` writes a work dir, then a ZIP. Excluded frames are always omitted. The UI asks which rows to keep:

- unannotated frames (negative samples; on by default)
- manual masks
- auto-tracked masks

`project_ids: null` merges every project into one dataset. Categories / YOLO class names merge by label name. The home page (`/`) and each project page both open the same export dialog.

| Format | Contents |
|--------|----------|
| `coco` | `images/*.jpg`, `annotations/instances_default.json` (COCO instance segmentation: polygons or RLE, bbox `[x,y,w,h]`, area, `iscrowd`) |
| `yolo` | `images/`, `labels/*.txt` (including empty files for negatives), `classes.txt`, `data.yaml` with `train` and `val` |
| `voc` | Pascal VOC-style `JPEGImages/`, `SegmentationClass/`, `SegmentationObject/`, `ImageSets/Segmentation/default.txt`, `labelmap.txt` |
| `native` | frames + `masks/ann_{id}.png` + `project.json` (`format: sewer-annotator-v2`) |

YOLO polygons come from OpenCV external contours of the binary mask. COCO uses CCOMP contours (holes) and falls back to uncompressed RLE. Native export is the lossless mask backup.

## Settings

`backend/app/core/settings.py` (`pydantic-settings`, extra env ignored):

- `model_id` default `facebook/sam2.1-hiera-small`
- `data_root` default `/data`
- `frontend_origin` default `http://localhost:8092`
- `default_tracking_step` `5`
- `jpeg_quality` `92`

Compose also sets `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` and `HF_HOME`.

## Leftover CVAT-era code

These exist on disk but are **not** included from `app/api/router.py`:

- `backend/app/services/cvat_service.py`
- `backend/app/api/routes/tasks.py`
- `backend/app/api/routes/health.py` (includes `/cvat/me`)
- `backend/app/schemas/models.py` (still uses `task_id` / `shape_id`)

Treat them as dead unless a task explicitly revives CVAT import/review. Live request bodies are declared next to the route modules.

## Constraints to preserve

- Serialize GPU inference.
- Empty masks are rejected on save.
- Label delete is blocked while annotations exist.
- Uploads allow large media (`client_max_body_size 20G`; tracking/prompt proxy timeouts 3600s).
- Backend image sets `SAM2_BUILD_CUDA=0` and installs SAM2 with `--no-build-isolation`.
