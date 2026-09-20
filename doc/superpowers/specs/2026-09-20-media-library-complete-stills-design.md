# Media library: compact list, manual Done, stills album

## Problem

The project media library renders one large card per file. As stills and videos accumulate, the page becomes a long, noisy list. There is no way to mark a video or still set finished (empty frames are valid for sewer CCTV). Each still is its own Annotate target, so operators cannot work a photo batch the way they work video frames.

## Decision

Manual **Done** checkbox per video and one Done for the whole stills set. Library header tabs **All / Completed / Not annotated** (Done flag, not mask coverage). Videos remain individual rows. All `kind=image` media collapse into one **Pictures** row with Annotate, Done, and Delete. Annotate opens the existing editor with every still in the left column. SAM2, tracking, mask files, and exports stay per media id. Do not merge stills into one backend media item.

## Data model

Add `annotation_complete INTEGER NOT NULL DEFAULT 0` on `media` via the existing `MEDIA_COLUMNS` migration in `backend/app/core/db.py`. SQLite stores `0`/`1`. JSON APIs expose boolean `annotation_complete`.

`media_service.enrich` includes `annotation_complete: bool(...)`. New uploads stay `false`. Videos own their flag independently.

The Pictures row is complete if and only if the project has at least one still **and** every still has `annotation_complete === true`. Ticking Done on Pictures sets every still in the project to complete; unticking sets every still to incomplete. Uploading a new still inserts `annotation_complete = 0`, so the album becomes incomplete. There is no indeterminate checkbox: mixed flags render as not complete.

Do not add a project-level stills column. Do not infer Done from annotation counts.

## HTTP

Thin routes; logic in services.

`PATCH /api/media/{mid}` body `{ "annotation_complete": true|false }`

- 200: the updated media object (same shape as `GET /api/media/{mid}` plus existing enrich fields)
- 404 if media missing
- 400 if `kind` is `image` (`Use the project stills complete endpoint`)

`PATCH /api/projects/{pid}/images/complete` body `{ "annotation_complete": true|false }`

- Resolves project by id or slug like other project routes
- Updates every `kind=image` row for that project
- 200: `{ "annotation_complete": bool, "updated": <image count> }`
- 404 if project missing
- 400 if the project has no stills

`DELETE /api/projects/{pid}/images`

- Deletes every still in the project using the same file/mask cleanup as `media_service.delete`
- Does not delete videos
- 200: `{ "ok": true, "deleted": <count> }`
- 404 if project missing
- 200 with `deleted: 0` if there are no stills (idempotent)

Existing `DELETE /api/media/{mid}` still deletes one video or one leftover still. The library UI does not expose per-still delete.

`GET /api/projects/{pid}` already returns `media[]`; clients filter tabs from `annotation_complete`. No new list endpoint.

## Library UI

`ProjectWorkspace` media section:

- Header: title plus segmented tabs matching the annotator `filter-seg`: **All**, **Completed**, **Not annotated**. Counts on each tab. Tab state is component-local; it resets when leaving the project.
- **Not annotated** means `annotation_complete === false` (in-progress work is included).
- The table is compact (thumb about 96×60, single-line meta) and scrolls inside the panel (`max-height` ~ `min(60vh, 560px)`) so the hero and defect legend stay on screen.

Rows, in this order:

1. Optional **Pictures** row if `images.length > 0`: first-still thumb (lowest media id), label `Pictures`, still count, summed annotations/time, Done checkbox, Annotate, Delete.
2. Video rows (current project media order, `id DESC`): Done, Annotate or Extract, Delete.

Unextracted videos appear in All and Not annotated (unless marked Done). They show Extract, not Annotate. Done remains available so an operator can skip a clip.

Delete on Pictures opens `ConfirmDialog` (`Delete N stills?` / annotations on those files are removed). Video delete keeps the current per-file confirm.

Failed Done PATCH reverts the checkbox and sets the page error banner.

## Stills annotator

Pictures **Annotate** navigates to `/projects/{slug}/media/{id}` for `firstIncompleteStill(images)`: stills sorted by `id` ascending, first with `annotation_complete === false`, else the first still.

When the open media `kind === 'image'`:

- Left rail title **Pictures**. The list is every project still (`id` ascending): thumb of frame 0, filename, annotation count, active state. Click navigates to that still’s media URL. Unsaved editor state follows today’s frame-change path (prompt session closed, editor reset). Autosave still runs on its interval while the still is open and dirty.
- Header: `{filename}` and `{project} · Pictures · {index} of {count}`. Header **Done** toggles the album endpoint (same flag as the library row).
- ← / → and the footer prev/next step one still. Shift+arrow steps 10 stills, clamped. The video timeline, frame-number jump, and SAM2 tracker card are hidden. Tracking is not started from stills.
- Prompt, brush, save, exclude, and per-still masks keep using that still’s `media_id` and frame `0`.

Opening an image URL directly uses the same playlist. Opening a video is unchanged (frames, tracker, timeline).

## Frontend modules

- Types: `Media.annotation_complete?: boolean`
- API wrappers in `frontend/src/api/client.ts` only
- Pure helpers in `frontend/src/mediaLibrary.ts` (tested): build library rows, tab filter, album complete, first incomplete still, still playlist index, next/previous still
- `ProjectWorkspace` consumes those helpers; `App.tsx` wires playlist navigation and Done PATCH
- CSS stays in `frontend/src/styles.css`; match existing dark compact controls

## Out of scope

- Inferring Done from mask coverage
- Merging stills into one media row or new `kind`
- Changing export, SAM2 prompt, or video tracking persistence
- Dashboard stats for completed media
- Per-still Done checkboxes in the library
- Rewriting source videos or deleting Docker volumes

## Tests

Backend (`backend/tests/test_media_complete.py`):

- New media defaults to incomplete
- Video PATCH flips only that row
- Image PATCH via `/media/{id}` raises / 400
- Project stills PATCH updates every image and none of the videos
- New still upload leaves the album incomplete after a previous complete
- Delete project images removes stills and leaves videos
- Missing ids are 404; stills complete with zero images is 400

Frontend (`frontend/src/mediaLibrary.test.ts`):

- Tabs keep all / completed / not-complete rows (Pictures counts as one row)
- Album complete only when every still is flagged
- `firstIncompleteStill` prefers the lowest incomplete id
- Playlist next/previous clamps and steps by 10

Run from `backend`: `python -m unittest tests.test_media_complete`. From `frontend`: `npm run build`.

## Architecture note

Update `doc/architecture.md` data model (`annotation_complete`) and API map (`PATCH` media complete, project stills complete/delete). Do not introduce a CVAT dependency. GPU work stays serialized; stills must not call tracking.
