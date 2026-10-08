from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from infra.business_units import MAX_BUSINESS_UNIT_LENGTH
from infra.database import Base
from users.roles import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("idx_users_email", "email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), default=UserRole.MIEMBRO.value, nullable=False, index=True
    )
    business_unit: Mapped[str | None] = mapped_column(
        String(MAX_BUSINESS_UNIT_LENGTH), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
