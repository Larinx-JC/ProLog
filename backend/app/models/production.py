"""Persistent accuracy versions, current operational settings and safe request retries."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.session import Base
from app.models.mixins import PRECISE_TIME


class AccuracyVersion(Base):
    """An immutable accuracy policy referenced by every new production run."""

    __tablename__ = "accuracy_versions"
    __table_args__ = (
        *(
            CheckConstraint(f"{name}_places BETWEEN 0 AND 6", name=f"ck_accuracy_{name}")
            for name in ("resistance", "thickness", "speed", "length", "result")
        ),
        CheckConstraint("rounding IN ('half_up', 'half_even')", name="ck_accuracy_rounding"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resistance_places: Mapped[int] = mapped_column()
    thickness_places: Mapped[int] = mapped_column()
    speed_places: Mapped[int] = mapped_column()
    length_places: Mapped[int] = mapped_column()
    result_places: Mapped[int] = mapped_column()
    rounding: Mapped[str] = mapped_column(String(16))
    calculation_version: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(PRECISE_TIME)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ProductionSettings(Base):
    """Current defaults plus immediate operational authority; serialized with AuthState."""

    __tablename__ = "production_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_production_settings_singleton"),
        CheckConstraint("revision > 0", name="ck_production_settings_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    accuracy_version_id: Mapped[int] = mapped_column(ForeignKey("accuracy_versions.id"))
    operator_abnormal_allowed: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    revision: Mapped[int] = mapped_column(default=1, server_default="1")


class ProductionRequest(Base):
    """Committed mutation receipt, scoped to an actor and a client request UUID."""

    __tablename__ = "production_requests"

    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation: Mapped[str] = mapped_column(String(40))
    payload_digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(PRECISE_TIME)


class DisplaySettings(Base):
    """Current factory-wide presentation, never referenced as a run's recording policy."""

    __tablename__ = "display_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_display_settings_singleton"),
        CheckConstraint("revision > 0", name="ck_display_settings_revision"),
        *(
            CheckConstraint(f"{name}_places BETWEEN 0 AND 6", name=f"ck_display_{name}")
            for name in ("resistance", "thickness", "speed", "length", "result")
        ),
        CheckConstraint("rounding IN ('half_up', 'half_even')", name="ck_display_rounding"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    resistance_places: Mapped[int] = mapped_column(default=2, server_default="2")
    thickness_places: Mapped[int] = mapped_column(default=3, server_default="3")
    speed_places: Mapped[int] = mapped_column(default=2, server_default="2")
    length_places: Mapped[int] = mapped_column(default=2, server_default="2")
    result_places: Mapped[int] = mapped_column(default=2, server_default="2")
    rounding: Mapped[str] = mapped_column(String(16), default="half_up", server_default="half_up")
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(PRECISE_TIME, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
