from pydantic import BaseModel, Field, EmailStr, field_validator, StrictBool
from typing import Optional, Literal
from uuid import UUID
from datetime import date
import re


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=72)
    full_name: str = Field(..., min_length=1, max_length=255)
    agency_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned):
            raise ValueError("Invalid email format")
        return cleaned

    @field_validator("full_name", "agency_name")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank")
        return cleaned


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Email cannot be blank")
        return cleaned


class ClientCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Client name cannot be blank")
        return cleaned


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    client_id: UUID
    description: Optional[str] = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Project name cannot be blank")
        return cleaned


class TaskCreateRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., min_length=1, max_length=240)
    status: Literal["todo", "in_progress", "review", "done"] = "todo"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    assignee_id: Optional[UUID] = None
    due_date: Optional[date] = None
    is_internal: StrictBool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Task title is required")
        return cleaned


class TaskStatusUpdateRequest(BaseModel):
    status: Literal["todo", "in_progress", "review", "done"]


class TaskVisibilityUpdateRequest(BaseModel):
    is_internal: StrictBool


class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    is_internal: StrictBool = False

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Comment must contain 1 to 5000 characters")
        return cleaned


class FileUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_url: str = Field(..., min_length=1, max_length=2000)
    is_internal: StrictBool = False

    @field_validator("file_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Provide a valid file name")
        return cleaned

    @field_validator("file_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("Provide a valid http(s) URL")
        return cleaned


class FileApprovalRequest(BaseModel):
    approval_status: Literal["approved", "needs_changes"]


class TimeLogRequest(BaseModel):
    duration_minutes: int = Field(..., ge=1, le=1440)
    note: Optional[str] = ""
    entry_date: Optional[date] = None


class InviteCreateRequest(BaseModel):
    email: str
    role: Literal["agency_admin", "agency_member", "client_user"]
    client_id: Optional[UUID] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned):
            raise ValueError("Provide a valid email")
        return cleaned


class InviteAcceptRequest(BaseModel):
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    full_name: Optional[str] = None


class AutomationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    trigger_event: Literal["file_needs_changes", "file_approved", "task_done", "comment_created"]
    action_type: Literal["update_task_status", "notify_assignee", "notify_admins"]
    action_config: dict = Field(default_factory=dict)
    is_enabled: StrictBool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Automation name is required")
        return cleaned


class AutomationUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_enabled: Optional[StrictBool] = None
    action_config: Optional[dict] = None
