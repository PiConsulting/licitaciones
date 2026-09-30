import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from infra.business_units import normalize_business_unit
from users.roles import UserRole

PASSWORD_RULE_MESSAGE = "La contraseña debe tener al menos 8 caracteres y un número"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    name: str
    email: str
    role: str
    business_unit: str | None = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo es obligatorio")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8 or re.search(r"\d", value) is None:
            raise ValueError(PASSWORD_RULE_MESSAGE)
        return value


class RegisterResponse(BaseModel):
    id: str
    email: str
    name: str


def _validate_password_rule(value: str) -> str:
    if len(value) < 8 or re.search(r"\d", value) is None:
        raise ValueError(PASSWORD_RULE_MESSAGE)
    return value


def _validate_business_unit(value: str) -> str:
    resolved = normalize_business_unit(value)
    if resolved is None:
        raise ValueError("La unidad de negocio no es válida")
    return resolved


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: UserRole
    business_unit: str | None
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    business_unit: str
    role: UserRole
    is_active: bool = True
    password: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo es obligatorio")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("business_unit")
    @classmethod
    def validate_business_unit(cls, value: str) -> str:
        return _validate_business_unit(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_rule(value)


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    business_unit: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo es obligatorio")
        return normalized

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        if value is None:
            return None
        return str(value).strip().lower()

    @field_validator("business_unit")
    @classmethod
    def validate_business_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_business_unit(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return _validate_password_rule(value)
