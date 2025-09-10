"""
Pydantic schemas for request and response bodies.

These classes define the shapes of JSON data sent to and returned from the API
endpoints.  Using Pydantic ensures data validation and automatic docs
generation with FastAPI.
"""
from __future__ import annotations

from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None


class LoginRequest(BaseModel):
    """Credentials supplied to the login endpoint."""

    email: EmailStr
    password: str


RoleType = Literal["user", "admin", "superadmin"]


class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: RoleType = "user"


class UserCreate(UserBase):
    password: str = Field(..., min_length=12)
    active: bool = True

    @field_validator("password")
    @classmethod
    def check_strength(cls, v: str) -> str:
        import re
        if not re.search(r"[A-Z]", v):
            raise ValueError("must include an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("must include a lowercase letter")
        if not (re.search(r"[0-9]", v) or re.search(r"[^A-Za-z0-9]", v)):
            raise ValueError("must include a digit or symbol")
        return v


class UserRead(UserBase):
    id: int
    active: bool
    created_at: datetime
    collection_count: int = 0

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Access token and user info returned after a successful login."""

    token: str
    user: UserRead


class UserUpdate(BaseModel):
    """Fields that can be updated for an existing user (excluding role)."""

    name: Optional[str] = None
    email: Optional[EmailStr] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=12)


class UserRoleUpdate(BaseModel):
    role: RoleType


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=12)


class DocumentBase(BaseModel):
    title: str
    status: str
    pages: Optional[int]
    sha256: Optional[str]


class DocumentRead(DocumentBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(DocumentRead):
    pass


class Citation(BaseModel):
    id: str
    filename: str
    page: int
    section: str | None = None
    url: str | None = None
    score: float
    collection_id: int
    collection_name: str
    snippet: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    top_k: Optional[int] = None
    temperature: Optional[float] = None
    mmr_lambda: Optional[float] = None
    session_id: int


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    followups: List[str] = []
    query_id: int


class ChatEntry(BaseModel):
    id: int
    query: str
    response: str
    created_at: datetime
    session_id: int
    query_id: Optional[int] = None
    feedback: Optional[str] = None

    model_config = {"from_attributes": True}


class ChatSessionBase(BaseModel):
    session_title: Optional[str] = None


class ChatSessionCreate(ChatSessionBase):
    pass


class ChatSessionUpdate(ChatSessionBase):
    session_title: str


class ChatSession(ChatSessionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UploadDocResponse(BaseModel):
    id: int
    title: str
    status: str
    pages: Optional[int]
    sha256: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionBase(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    visibility: str = "private"


class CollectionCreate(CollectionBase):
    pass


class CollectionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    visibility: Optional[str] = None


class CollectionRead(CollectionBase):
    id: int
    owner_id: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    doc_count: int

    model_config = {"from_attributes": True}


class UserPrefsRead(BaseModel):
    """Preferences returned to the client."""

    temperature: float
    top_k: int
    mmr_lambda: float
    theme: str


class UserPrefsUpdate(BaseModel):
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    mmr_lambda: Optional[float] = None
    theme: Optional[str] = None


class CollectionAssignment(BaseModel):
    assigned: List[int]
