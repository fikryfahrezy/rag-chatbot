import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Commission, Inventory, Order
from .policies import scope_commissions, scope_orders
from .schemas import Citation, User


@dataclass
class ToolResult:
    answer: str
    citations: list[Citation]
    route: str


def answer_operation(session: Session, question: str, user: User, route_hint: str | None = None) -> ToolResult:
    text = question.lower()
    order_match = re.search(r"ord-\d+", text, re.IGNORECASE)

    if route_hint == "inventory" or "stok" in text or "stock" in text:
        stmt = select(Inventory)
        if user.role in {"sales", "manager"}:
            stmt = stmt.where(Inventory.warehouse_region == user.region)
        rows = session.scalars(stmt.order_by(Inventory.product).limit(20)).all()
        answer = "Stok saat ini: " + "; ".join(f"{r.product} ({r.sku}) = {r.stock}" for r in rows)
        citations = [Citation(label=r.sku, detail=f"inventory row #{r.id}") for r in rows]
        return ToolResult(answer, citations, "inventory")

    if route_hint == "commission" or "komisi" in text or "pendapatan" in text:
        stmt = scope_commissions(select(Commission), user).order_by(Commission.period.desc()).limit(50)
        rows = session.scalars(stmt).all()
        total = sum(row.amount for row in rows)
        answer = f"Total komisi yang boleh Anda lihat: Rp{total:,.0f}.".replace(",", ".")
        if rows:
            answer += " Rincian: " + "; ".join(f"{r.sales_id} {r.period}: Rp{r.amount:,.0f}".replace(",", ".") for r in rows)
        return ToolResult(answer, [Citation(label="commission", detail=f"{len(rows)} authorized rows")], "commission")

    stmt = select(Order)
    if order_match:
        stmt = stmt.where(func.lower(Order.order_no) == order_match.group(0).lower())
    stmt = scope_orders(stmt, user).order_by(Order.created_at.desc()).limit(20)
    rows = session.scalars(stmt).all()
    if not rows:
        return ToolResult("Order tidak ditemukan atau Anda tidak memiliki akses ke order tersebut.", [], "order")
    answer = "Order yang boleh Anda lihat: " + "; ".join(
        f"{r.order_no} — {r.customer}, {r.product}, status {r.status}, Rp{r.amount:,.0f}".replace(",", ".") for r in rows
    )
    return ToolResult(answer, [Citation(label=r.order_no, detail=f"status={r.status}") for r in rows], "order")


def answer_public_catalog(session: Session, question: str) -> ToolResult | None:
    """Deliberately small public projection: never exposes counts or transactional rows."""
    text = question.lower()
    if not any(word in text for word in ("stok", "stock", "produk", "barang", "tersedia")):
        return None
    rows = session.scalars(select(Inventory).order_by(Inventory.product).limit(20)).all()
    answer = "Ketersediaan produk: " + "; ".join(
        f"{row.product} — {'tersedia' if row.stock > 0 else 'tidak tersedia'}" for row in rows
    )
    return ToolResult(answer, [Citation(label="Katalog publik", detail="status ketersediaan tanpa jumlah stok")], "public_catalog")
