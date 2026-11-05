"""Generic data-access layer. Concrete repositories subclass BaseRepository."""

from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from learning.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from learning.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """CRUD and query helpers shared by every repository.

    Subclasses set ``model`` and add queries specific to that table:

        class UserRepository(BaseRepository[User]):
            model = User

            def find_by_email(self, email: str) -> User | None:
                return self.find_one(email=email)

    Write methods flush but never commit — committing is the caller's decision,
    so a service can group several repository calls into one transaction.
    """

    model: type[ModelType]

    def __init__(self, session: Session) -> None:
        if not getattr(self, "model", None):
            raise TypeError(f"{type(self).__name__} must set a 'model' class attribute")
        self.session = session

    # ---------------------------------------------------------------- queries

    def _select(self, **filters: Any) -> Select:
        stmt = select(self.model)
        return stmt.filter_by(**filters) if filters else stmt

    def _order(self, stmt: Select, order_by: str | InstrumentedAttribute | None) -> Select:
        """Apply ordering. Strings may be prefixed with '-' for descending."""
        if order_by is None:
            return stmt
        if isinstance(order_by, str):
            descending = order_by.startswith("-")
            column = getattr(self.model, order_by.lstrip("-"), None)
            if column is None:
                raise AttributeError(f"{self.model.__name__} has no column {order_by.lstrip('-')!r}")
            order_by = column.desc() if descending else column.asc()
        return stmt.order_by(order_by)

    # ------------------------------------------------------------------ reads

    def find_by_id(self, record_id: Any) -> ModelType | None:
        """Fetch by primary key. Returns None if absent.

        Uses Session.get, which checks the identity map before hitting the DB.
        """
        return self.session.get(self.model, record_id)

    def find_one(self, **filters: Any) -> ModelType | None:
        """First record matching the filters, or None.

        repo.find_one(email="a@b.com")
        """
        return self.session.scalars(self._select(**filters).limit(1)).first()

    def find_all(
        self,
        *,
        offset: int = 0,
        limit: int | None = DEFAULT_PAGE_SIZE,
        order_by: str | InstrumentedAttribute | None = None,
        **filters: Any,
    ) -> Sequence[ModelType]:
        """Records matching the filters, paginated.

        repo.find_all(status=UserStatus.ACTIVE, order_by="-created_at", limit=50)

        limit=None returns everything — only for small tables you control.
        """
        stmt = self._order(self._select(**filters), order_by)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(min(limit, MAX_PAGE_SIZE))
        return self.session.scalars(stmt).all()

    def count(self, **filters: Any) -> int:
        """Number of records matching the filters."""
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        return self.session.scalar(stmt) or 0

    def exists(self, **filters: Any) -> bool:
        """Whether any record matches — cheaper than count() for a yes/no."""
        stmt = select(self.model.id).filter_by(**filters).limit(1)
        return self.session.scalar(stmt) is not None

    # ----------------------------------------------------------------- writes

    def create(self, **values: Any) -> ModelType:
        """Build, persist and return an instance (flushed, not committed)."""
        instance = self.model(**values)
        self.session.add(instance)
        self.session.flush()
        return instance

    def update(self, instance: ModelType, **values: Any) -> ModelType:
        """Apply field updates to an existing instance."""
        for field, value in values.items():
            if not hasattr(instance, field):
                raise AttributeError(f"{self.model.__name__} has no attribute {field!r}")
            setattr(instance, field, value)
        self.session.flush()
        return instance

    def delete(self, instance: ModelType) -> None:
        """Remove an instance."""
        self.session.delete(instance)
        self.session.flush()
