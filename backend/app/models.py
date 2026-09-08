from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer: Mapped[str] = mapped_column(String(120))
    product: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Float)
    sales_id: Mapped[str] = mapped_column(String(40), index=True)
    region: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Commission(Base):
    __tablename__ = "commissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    sales_id: Mapped[str] = mapped_column(String(40), index=True)
    region: Mapped[str] = mapped_column(String(40), index=True)
    period: Mapped[str] = mapped_column(String(10), index=True)
    amount: Mapped[float] = mapped_column(Float)


class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(120))
    stock: Mapped[int] = mapped_column(Integer)
    warehouse_region: Mapped[str] = mapped_column(String(40), index=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    visibility: Mapped[str] = mapped_column(String(20), default="internal")
    region: Mapped[str | None] = mapped_column(String(40), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)


class ModelSetting(Base):
    __tablename__ = "model_settings"
    task: Mapped[str] = mapped_column(String(40), primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))


class RegisteredModel(Base):
    __tablename__ = "registered_models"
    __table_args__ = (UniqueConstraint("provider", "model", name="uq_registered_model_provider_model"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
