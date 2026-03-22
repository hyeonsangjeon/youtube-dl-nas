"""Download ORM model."""

import uuid

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func

from app.database import Base


class Download(Base):
    """Represents a download job in the queue or history."""

    __tablename__ = "downloads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(Text, nullable=False)
    title = Column(String, nullable=True)
    channel = Column(String, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    resolution = Column(String, nullable=True)
    status = Column(String, default="queued")
    progress = Column(Float, default=0.0)
    filepath = Column(Text, nullable=True)
    filename = Column(String, nullable=True)
    filesize = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
