from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, Text, Index, UniqueConstraint, ForeignKey, CheckConstraint, Boolean
from typing import Optional

class Base(DeclarativeBase):
    pass

class Settings(Base):
    __tablename__ = "settings"
    
    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    morning_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="07:00")
    evening_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/Moscow")
    ical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # iCal can be explicitly disabled per chat. When enabled and ical_url is NULL/empty,
    # resolve_ical_url() may fall back to the global env default.
    ical_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    last_ical_sync_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coverage_end_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sent_morning_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sent_evening_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sent_manual_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("mode IN (0, 1, 2)", name="ck_settings_mode"),
    )


class SetupToken(Base):
    __tablename__ = "setup_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    used_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("token", name="uq_setup_token"),
        Index("idx_setup_tokens_chat_id", "chat_id"),
        Index("idx_setup_tokens_expires_at", "expires_at"),
    )


class Upload(Base):
    __tablename__ = "uploads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey("settings.chat_id"), nullable=False)
    filename: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_from: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_to: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rows_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ScheduleItem(Base):
    __tablename__ = "schedule_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey("settings.chat_id"), nullable=False)
    date: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[str] = mapped_column(Text, nullable=False)
    end_time: Mapped[str] = mapped_column(Text, nullable=False)
    room: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    teacher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ical_uid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ical_dtstart: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_upload_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("uploads.id"), nullable=True)
    
    __table_args__ = (
        Index("idx_schedule_date", "chat_id", "date"),
        Index("idx_schedule_date_start", "chat_id", "date", "start_time"),
        Index("idx_schedule_ical_key", "chat_id", "ical_uid", "ical_dtstart"),
        UniqueConstraint("chat_id", "ical_uid", "ical_dtstart", name="uq_schedule_ical_key"),
    )


class SendLog(Base):
    __tablename__ = "send_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_date: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    reserved_at: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    __table_args__ = (
        UniqueConstraint("chat_id", "target_date", "kind", name="uq_send_log"),
    )
