from typing import Optional, Literal, Union, List
from pydantic import BaseModel


class Vec3(BaseModel):
    x: float; y: float; z: float


class SetView(BaseModel):
    center: Vec3
    zoom: Union[Literal["fit"], float] = "fit"
    orientation: Literal["xy","yz","xz","3d"] = "xy"


class SetLUT(BaseModel):
    layer: str
    vmin: float
    vmax: float


class Annotation(BaseModel):
    id: Optional[str] = None
    type: Literal["point","box","ellipsoid"]
    center: Vec3
    size: Optional[Vec3] = None # for box/ellipsoid


class AddAnnotations(BaseModel):
    layer: str
    items: List[Annotation]


class HistogramReq(BaseModel):
    layer: str
    roi: Optional[dict] = None # {bbox: [x0,y0,z0,x1,y1,z1]} or similar


class IngestCSV(BaseModel):
    file_id: str # uploaded handle or S3 key


class SaveState(BaseModel):
    pass


# Chat
class ChatMessage(BaseModel):
    role: Literal["user","assistant","tool"]
    content: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage]