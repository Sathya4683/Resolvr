"""request / response models shared by the routers"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["support_agent", "admin", "analyst"]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


#---------------- auth / users ----------------

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    #the login page has a tab per role, we check the account really has that role
    role: Role | None = None


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9_.]+$")
    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=EMAIL_PATTERN)
    role: Role
    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=EMAIL_PATTERN)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
