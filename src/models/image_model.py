from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Image(SQLModel, table=True):
    """Referencia a una imagen guardada en S3 (el archivo vive en S3, aquí solo guardamos dónde está)."""

    __tablename__ = "app_images"

    id: int | None = Field(primary_key=True, default=None)
    original_filename: str
    s3_bucket: str
    s3_key: str = Field(unique=True)
    content_type: str
    size_bytes: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
