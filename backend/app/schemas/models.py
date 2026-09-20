from typing import Literal

from pydantic import BaseModel, Field


class PointPrompt(BaseModel):
    x: float
    y: float
    positive: bool = True


class PromptSessionCreate(BaseModel):
    task_id: int
    frame: int = Field(ge=0)
    shape_id: int | None = None


class PromptPointsRequest(BaseModel):
    points: list[PointPrompt]


class SaveMaskRequest(BaseModel):
    task_id: int
    frame: int = Field(ge=0)
    label_id: int
    mask_png_data_url: str
    replace_shape_id: int | None = None


class TrackRequest(BaseModel):
    task_id: int
    shape_id: int
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    replace_auto_masks: bool = True


class ImportedMask(BaseModel):
    frame: int = Field(ge=0)
    label_name: str
    points: list[float]
    group: int = 0
    occluded: bool = False
    z_order: int = 0


class ImportAnnotationsRequest(BaseModel):
    format: Literal["sewer-annotator-mask-v1"] = "sewer-annotator-mask-v1"
    masks: list[ImportedMask]
