# Sewer SAM2 Annotator v2

A standalone sewer CCTV annotation application built with **React + TypeScript**, **FastAPI**, **SQLite**, **Docker**, and **SAM2.1 Hiera Small**.

It does **not require CVAT** to run. CVAT can still be used later as a review/import destination through standard dataset exports.

## What is included

- Project creation and project dashboard
- Upload multiple videos and images per project
- Project-specific defect labels and add-new-label action
- SAM2 positive point prompts
- SAM2 negative/exclusion point prompts
- SAM2 rectangle/box prompt
- Brush and eraser mask correction
- Working brush-size slider, default **15 px**
- Edit an existing mask with points, box, brush, or eraser
- Autosave, enabled by default every **3 seconds**, with configurable interval
- CVAT-style nearby frame thumbnails with annotation counts
- Left-side annotation thumbnail gallery; click any tracked mask to inspect/edit it
- SAM2 video tracking forward or backward
- Tracking result stride, default **every 5 frames**
- SAM2 still processes intermediate frames for temporal memory; only requested stride frames are persisted
- Preserve manual correction frames when re-running tracking
- Replace previous automatic masks in a range
- Delete/exclude a frame with or without deleting its annotations
- Restore excluded frames
- Delete a whole uploaded video/image
- Standard exports with frame images:
  - COCO Instance Segmentation
  - YOLO Segmentation
  - Native project backup (JSON + mask PNGs)

## Architecture

```text
Browser :8092
   |
   +-- React + TypeScript annotation UI
   |
   +-- FastAPI :8091
          |
          +-- SQLite /data/annotator.db
          +-- uploaded videos and images
          +-- saved mask PNGs
          +-- export ZIPs
          +-- SAM2.1 Hiera Small
                 |
                 +-- RTX 3070 Ti / CUDA
```

All persistent application data is stored in the Docker volume `annotator-data`.
SAM2/Hugging Face model files are cached in `sam2-models`.

## Windows + WSL installation

You already verified Docker GPU support with `nvidia-smi`, so from Ubuntu/WSL:

```bash
cd ~
unzip sewer-sam2-annotator-v2.zip
cd sewer-sam2-annotator-v2
```

If the old SAM2/CVAT helper is still using port 8091, stop it first:

```bash
cd ~/cvat-sam2-tracker
docker compose down
cd ~/sewer-sam2-annotator-v2
```

Build and start:

```bash
docker compose build
docker compose up -d
```

Watch the backend:

```bash
docker logs -f sewer-annotator-backend
```

Wait until the logs include:

```text
SAM2 MODEL LOADED SUCCESSFULLY
```

Open:

```text
http://localhost:8092
```

FastAPI docs:

```text
http://localhost:8091/docs
```

## Normal workflow

### 1. Create a project

Open the application and choose **New project**.

A new project starts with sewer defect labels such as Root, Crack, Obstacle, Deposits, Deformed, Broken, Joint Displaced, and Surface Damage. Add or remove labels from the project page.

### 2. Upload media

Use **Upload media** and select multiple files at once.

Supported input includes common image and video formats. Videos remain as their original files; frames are decoded on demand.

### 3. Create the first mask

Open a video/image and choose a label.

Use one of these tools:

- **+ Point**: click inside the defect.
- **− Exclude**: click areas that should not belong to the mask.
- **Box**: drag a rectangle around the defect and let SAM2 segment it.
- **Brush**: manually add mask pixels.
- **Eraser**: manually remove mask pixels.

The brush starts at **15 px**. Change it with the toolbar slider; the circular cursor preview reflects the selected size.

You can mix point and box prompts. For example, first draw a box, then add one negative point to remove a pipe-wall region.

### 4. Modify a saved or tracked mask

Click any annotation thumbnail in the left panel.

The saved mask is loaded into the editor. You can:

- refine it with positive / negative points
- draw a new SAM2 box
- use Brush / Eraser
- change its defect label
- delete it

When an automatically tracked mask is edited and saved, it is stored as `manual`, making it a correction/keyframe that is preserved on future re-tracking.

### 5. Autosave

Autosave is on by default:

```text
Every 3 seconds
```

The interval can be changed in the right panel or autosave can be disabled.

Autosave runs only when the current mask is dirty/changed.

### 6. Video tracking

Save the first mask, select it, choose the target frame and choose the save stride.

Default:

```text
Save every 5 frames
```

Example:

```text
Seed: frame 72
Target: frame 172
Step: 5

Saved masks:
72 (seed)
77
82
87
...
172
```

SAM2 processes the frames between those saved results as part of temporal video tracking; the stride controls which predicted masks are written to the annotation database.

Tracking can run forward or backward.

### 7. Review tracked results

After tracking completes, new annotation thumbnails appear in the **Annotations** section on the left.

Click any thumbnail to:

- jump to that frame
- inspect the generated mask
- delete it
- correct it
- change the label
- use it as a new tracking seed

This supports the recommended workflow:

```text
manual seed
  -> track
  -> inspect generated thumbnails
  -> correct a bad frame
  -> save it as manual
  -> continue tracking from the corrected frame
```

## Frame deletion / exclusion

For a video, the application does not physically rewrite the original video.

**Delete / exclude frame** means the frame is excluded from the annotation dataset and from exports.

There is a checkbox:

```text
Also delete annotations
```

- Off: exclude the frame but keep its annotations in the database.
- On: exclude the frame and permanently delete its annotations.

Excluded frames can be restored.

This is safer than destructively rewriting a source inspection video.

## Exports

Exports include the decoded frame JPG files so the result is a usable dataset, not annotation metadata alone.

### COCO Instance Segmentation

Project page or annotation page -> **COCO Instance + frames**.

Output contains:

```text
images/
annotations.json
```

Good for instance-segmentation training and interchange with tools that support COCO.

### YOLO Segmentation

Output contains:

```text
images/
labels/
classes.txt
data.yaml
```

Masks are converted to normalized segmentation polygons.

### Native backup

Output contains the frame dataset plus original binary mask PNGs and `project.json`. This preserves the application's mask data most directly.

## Data persistence

Do not remove the `annotator-data` Docker volume unless you want to delete all projects and annotations.

See volumes:

```bash
docker volume ls | grep annotator
```

Stop without deleting data:

```bash
docker compose down
```

Start again:

```bash
docker compose up -d
```

## Ports

```text
8091  FastAPI / SAM2 backend
8092  React annotation UI
```

Your CVAT installation can remain on 8090, but this application no longer depends on it.

## Notes for RTX 3070 Ti 8 GB

The backend uses SAM2.1 Hiera Small and initializes video tracking with CPU offload for frames and tracking state. Heavy GPU operations are serialized so multiple tracking jobs do not compete for the 8 GB VRAM.
# Mask-Annotator-VideoImageTracker
