# SAM 2.1 model Settings

Approved 21 Sep 2026. Site-wide SAM 2.1 size picker with cache-aware download and GPU swap.

## Catalog

| Label | Key | Hugging Face id | Checkpoint file |
|---|---|---|---|
| Tiny | `tiny` | `facebook/sam2.1-hiera-tiny` | `sam2.1_hiera_tiny.pt` |
| Small | `small` | `facebook/sam2.1-hiera-small` | `sam2.1_hiera_small.pt` |
| Balanced | `balanced` | `facebook/sam2.1-hiera-base-plus` | `sam2.1_hiera_base_plus.pt` |
| Large | `large` | `facebook/sam2.1-hiera-large` | `sam2.1_hiera_large.pt` |

Default remains Small. SAM 3.1 and SAM 2.0 are out of scope.

## UI

Settings nav link beside Dashboard and Projects. Four cards: label, Hugging Face id, **Downloaded** / **Not downloaded**, active mark. Large notes it may not fit 8 GB GPUs. Clicking a different size starts a switch job. Progress bar matches export/tracking:

- Waiting for tracker to finish…
- Downloading N%
- Already downloaded — loading onto GPU…
- Ready

Failure keeps the previous model and shows the error on this page.

## Persistence

SQLite `app_settings` (`key` / `value`) under `/data`. Key `sam_model` is written only after a successful GPU load. First boot with no row uses env / Small. Cached weights stay in `sam2-models` (`HF_HOME`). Switching never deletes checkpoints.

## API

- `GET /api/settings/model` — catalog, active key, cache flags, SAM2 status, in-flight job
- `POST /api/settings/model` `{ "key": "balanced" }` — start switch job
- `GET /api/settings/model/jobs/{id}` — poll percent + message

One switch at a time. A second POST while queued/running is **409**. Unknown key is **400**.

## Switch job

1. Wait until no tracking job is queued or running.
2. If the `.pt` is already in the Hugging Face cache, skip download.
3. Otherwise download with byte progress (map to ~5–80%).
4. Wait again if tracking started during download.
5. Take `Sam2Runtime.lock`, close prompt sessions, unload the current predictor, load the new one (~80–100%).
6. Persist `sam_model` only on success.
7. On download or load failure, reload the previous checkpoint from cache, do not change `sam_model`, set job `failed` + error.

GPU work stays serialized. Tracking pool stays `max_workers=1`.

## Tests

No GPU and no real Hugging Face download. Fake cache, download, load, and tracking busy.

- Catalog keys map to the four ids; unknown key rejected
- Cached checkpoint must not call download
- Missing checkpoint calls download then load
- Failed load reloads previous model and does not persist
- Switch waits while tracking is running
- Second in-flight switch is 409
- Frontend: four sizes, Downloaded vs not, progress message
