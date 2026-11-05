import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from learning.core.constants import UserStatus
from learning.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from learning.models.role import Role


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.PENDING,
        nullable=False,
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    role: Mapped["Role | None"] = relationship(back_populates="users", lazy="joined")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
