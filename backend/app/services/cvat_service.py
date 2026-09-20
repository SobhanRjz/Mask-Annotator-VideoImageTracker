from __future__ import annotations

from typing import Any

import numpy as np
from cvat_sdk import make_client, models
from cvat_sdk.core.proxies.annotations import AnnotationUpdateAction
from cvat_sdk.masks import decode_mask, encode_mask

from app.core.settings import settings
from app.utils.images import frame_data_to_bytes, jpeg_from_frame_data


def enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


class CvatService:
    def _client(self):
        if not settings.cvat_access_token:
            raise RuntimeError("CVAT_ACCESS_TOKEN is not configured")
        return make_client(
            settings.cvat_host,
            access_token=settings.cvat_access_token,
        )

    def current_user(self) -> dict[str, Any]:
        with self._client() as client:
            me = client.users.retrieve_current_user()
            return {
                "id": me.id,
                "username": me.username,
            }

    def task_info(self, task_id: int) -> dict[str, Any]:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            meta = task.get_meta()
            labels = task.get_labels()

            start_frame = getattr(meta, "start_frame", None)
            if start_frame is None:
                start_frame = 0

            stop_frame = getattr(meta, "stop_frame", None)
            size = getattr(meta, "size", None)
            if stop_frame is None and size:
                stop_frame = start_frame + int(size) - 1

            return {
                "id": task_id,
                "name": getattr(task, "name", f"Task {task_id}"),
                "start_frame": int(start_frame),
                "stop_frame": int(stop_frame) if stop_frame is not None else None,
                "size": int(size) if size is not None else None,
                "labels": [
                    {
                        "id": int(label.id),
                        "name": label.name,
                        "color": getattr(label, "color", None),
                    }
                    for label in labels
                ],
            }

    def frame_jpeg(self, task_id: int, frame: int) -> tuple[bytes, int, int]:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            frame_data = task.get_frame(frame, quality="original")
            return jpeg_from_frame_data(frame_data)

    def frame_bytes(self, task_id: int, frame: int) -> bytes:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            return frame_data_to_bytes(task.get_frame(frame, quality="original"))

    def list_masks(self, task_id: int, frame: int | None = None) -> list[dict[str, Any]]:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            annotations = task.get_annotations()
            labels = task.get_labels()
            label_names = {int(label.id): label.name for label in labels}

            result: list[dict[str, Any]] = []
            for shape in annotations.shapes:
                if enum_value(shape.type) != "mask":
                    continue
                if frame is not None and int(shape.frame) != frame:
                    continue

                result.append(
                    {
                        "shape_id": int(shape.id),
                        "frame": int(shape.frame),
                        "label_id": int(shape.label_id),
                        "label_name": label_names.get(int(shape.label_id), "Unknown"),
                        "source": enum_value(getattr(shape, "source", "manual")),
                        "group": int(shape.group or 0),
                    }
                )

            result.sort(key=lambda item: (item["frame"], item["shape_id"]))
            return result

    def get_mask(self, task_id: int, shape_id: int) -> tuple[np.ndarray, dict[str, Any]]:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            annotations = task.get_annotations()
            labels = task.get_labels()
            label_names = {int(label.id): label.name for label in labels}

            selected = None
            for shape in annotations.shapes:
                if int(shape.id) == shape_id:
                    selected = shape
                    break

            if selected is None:
                raise KeyError(f"Shape {shape_id} was not found")
            if enum_value(selected.type) != "mask":
                raise ValueError(f"Shape {shape_id} is not a mask")

            frame_data = task.get_frame(int(selected.frame), quality="original")
            _, width, height = jpeg_from_frame_data(frame_data)
            mask = decode_mask(
                selected.points,
                image_width=width,
                image_height=height,
            )
            mask = np.asarray(mask, dtype=np.bool_)

            metadata = {
                "shape_id": int(selected.id),
                "frame": int(selected.frame),
                "label_id": int(selected.label_id),
                "label_name": label_names.get(int(selected.label_id), "Unknown"),
                "source": enum_value(getattr(selected, "source", "manual")),
                "group": int(selected.group or 0),
            }
            return mask, metadata

    def create_mask(
        self,
        *,
        task_id: int,
        frame: int,
        label_id: int,
        mask: np.ndarray,
        source: str = "manual",
        group: int = 0,
        replace_shape_id: int | None = None,
    ) -> dict[str, Any]:
        if mask.ndim != 2 or not mask.any():
            raise ValueError("Mask is empty")

        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            encoded = encode_mask(np.asarray(mask, dtype=np.bool_))
            shape = models.LabeledShapeRequest(
                type="mask",
                frame=frame,
                label_id=label_id,
                points=encoded,
                occluded=False,
                z_order=0,
                rotation=0.0,
                group=group,
                source=source,
                attributes=[],
            )

            task.update_annotations(
                models.PatchedLabeledDataRequest(shapes=[shape]),
                action=AnnotationUpdateAction.CREATE,
            )

            if replace_shape_id is not None:
                task.remove_annotations(ids=[replace_shape_id])

            # Find the newest matching mask after creation.
            annotations = task.get_annotations()
            candidates = [
                s
                for s in annotations.shapes
                if enum_value(s.type) == "mask"
                and int(s.frame) == frame
                and int(s.label_id) == label_id
            ]
            newest = max(candidates, key=lambda s: int(s.id)) if candidates else None

            return {
                "shape_id": int(newest.id) if newest is not None else None,
                "frame": frame,
                "label_id": label_id,
                "replaced_shape_id": replace_shape_id,
            }

    def delete_shape(self, task_id: int, shape_id: int) -> None:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            task.remove_annotations(ids=[shape_id])

    def remove_auto_masks_in_range(
        self,
        *,
        task_id: int,
        label_id: int,
        frame_a: int,
        frame_b: int,
        exclude_shape_id: int | None = None,
    ) -> int:
        low, high = sorted((frame_a, frame_b))
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            annotations = task.get_annotations()
            ids: list[int] = []

            for shape in annotations.shapes:
                if enum_value(shape.type) != "mask":
                    continue
                if int(shape.label_id) != label_id:
                    continue
                if not (low <= int(shape.frame) <= high):
                    continue
                if exclude_shape_id is not None and int(shape.id) == exclude_shape_id:
                    continue
                if enum_value(getattr(shape, "source", "manual")) != "auto":
                    continue
                ids.append(int(shape.id))

            if ids:
                task.remove_annotations(ids=ids)
            return len(ids)

    def create_masks_bulk(
        self,
        *,
        task_id: int,
        label_id: int,
        masks_by_frame: dict[int, np.ndarray],
        source: str = "auto",
        group: int = 0,
    ) -> int:
        shapes = []
        for frame, mask in sorted(masks_by_frame.items()):
            if not mask.any():
                continue
            shapes.append(
                models.LabeledShapeRequest(
                    type="mask",
                    frame=frame,
                    label_id=label_id,
                    points=encode_mask(np.asarray(mask, dtype=np.bool_)),
                    occluded=False,
                    z_order=0,
                    rotation=0.0,
                    group=group,
                    source=source,
                    attributes=[],
                )
            )

        if not shapes:
            return 0

        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            task.update_annotations(
                models.PatchedLabeledDataRequest(shapes=shapes),
                action=AnnotationUpdateAction.CREATE,
            )
        return len(shapes)

    def export_masks(self, task_id: int) -> dict[str, Any]:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            annotations = task.get_annotations()
            labels = task.get_labels()
            label_names = {int(label.id): label.name for label in labels}

            masks = []
            for shape in annotations.shapes:
                if enum_value(shape.type) != "mask":
                    continue
                masks.append(
                    {
                        "frame": int(shape.frame),
                        "label_name": label_names.get(int(shape.label_id), "Unknown"),
                        "points": list(shape.points),
                        "group": int(shape.group or 0),
                        "occluded": bool(shape.occluded),
                        "z_order": int(shape.z_order or 0),
                    }
                )

            return {
                "format": "sewer-annotator-mask-v1",
                "task_id": task_id,
                "task_name": getattr(task, "name", f"Task {task_id}"),
                "masks": masks,
            }

    def import_masks(self, task_id: int, masks: list[dict[str, Any]]) -> dict[str, Any]:
        with self._client() as client:
            task = client.tasks.retrieve(task_id)
            labels = task.get_labels()
            label_ids = {label.name: int(label.id) for label in labels}

            shapes = []
            skipped = []
            for item in masks:
                label_name = item["label_name"]
                label_id = label_ids.get(label_name)
                if label_id is None:
                    skipped.append({"frame": item["frame"], "label_name": label_name})
                    continue

                shapes.append(
                    models.LabeledShapeRequest(
                        type="mask",
                        frame=int(item["frame"]),
                        label_id=label_id,
                        points=list(item["points"]),
                        occluded=bool(item.get("occluded", False)),
                        z_order=int(item.get("z_order", 0)),
                        rotation=0.0,
                        group=int(item.get("group", 0)),
                        source="manual",
                        attributes=[],
                    )
                )

            if shapes:
                task.update_annotations(
                    models.PatchedLabeledDataRequest(shapes=shapes),
                    action=AnnotationUpdateAction.CREATE,
                )

            return {
                "created": len(shapes),
                "skipped": skipped,
            }


cvat_service = CvatService()
