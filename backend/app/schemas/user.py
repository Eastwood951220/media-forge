import uuid
from datetime import datetime

from pydantic import BaseModel


class UserBase(BaseModel):
    username: str
    role: str = "user"


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
