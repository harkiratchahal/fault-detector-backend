from pydantic import BaseModel, field_validator, validator
import pydantic as _p
try:  # Detect Pydantic major version
    _V = tuple(int(x) for x in getattr(_p, "__version__", "2.0.0").split(".")[:1])
    IS_PYDANTIC_V2 = _V and _V[0] >= 2
except Exception:
    IS_PYDANTIC_V2 = False
if IS_PYDANTIC_V2:
    from pydantic import ConfigDict  # type: ignore
from typing import Optional, Any, Literal
from datetime import datetime


class DeviceRegister(BaseModel):
    fcm_token: str
    role: Literal["citizen", "staff"]


class Device(BaseModel):
    id: int
    fcm_token: str
    role: Literal["citizen", "staff"]
    created_at: datetime

    if IS_PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)  # type: ignore[name-defined]
    else:
        class Config:  # type: ignore
            orm_mode = True


class NodeStatusUpdate(BaseModel):
    node_id: int
    status: Literal["normal", "faulty"]
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    if IS_PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)  # type: ignore[name-defined]
    else:
        class Config:  # type: ignore
            orm_mode = True


class Node(BaseModel):
    id: int
    latitude: float
    longitude: float
    status: str
    last_updated: datetime

    if IS_PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True


class FaultReport(BaseModel):
    node_id: int
    description: str
    confidence: float
    image_url: Optional[str] = None

    # Pydantic v1 support
    if not IS_PYDANTIC_V2:
        @validator("confidence")  # type: ignore[misc]
        def confidence_range_v1(cls, v: float) -> float:  # noqa: N805
            if v < 0 or v > 100:
                raise ValueError("confidence must be between 0 and 100")
            return v

    # Pydantic v2 support
    if IS_PYDANTIC_V2:
        @field_validator("confidence")  # type: ignore[misc]
        @classmethod
        def confidence_range_v2(cls, v: float) -> float:
            if v < 0 or v > 100:
                raise ValueError("confidence must be between 0 and 100")
            return v


class Fault(BaseModel):
    id: int
    node_id: int
    description: str
    confidence: float
    image_url: Optional[str]
    reported_at: datetime

    if IS_PYDANTIC_V2:
        model_config = ConfigDict(from_attributes=True)  # type: ignore[name-defined]
    else:
        class Config:  # type: ignore
            orm_mode = True


class ResponseSchema(BaseModel):
    status: str
    message: str
    data: Any = None
