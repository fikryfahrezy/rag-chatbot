from fastapi import HTTPException
from sqlalchemy import Select

from .models import Commission, Document, Order
from .schemas import User


def require_internal(user: User) -> None:
    if user.role == "public":
        raise HTTPException(status_code=403, detail="Internal workspace requires authentication")


def scope_orders(stmt: Select, user: User) -> Select:
    require_internal(user)
    if user.role == "sales":
        return stmt.where(Order.sales_id == user.id)
    if user.role == "manager":
        return stmt.where(Order.region == user.region)
    return stmt


def scope_commissions(stmt: Select, user: User) -> Select:
    require_internal(user)
    if user.role == "sales":
        return stmt.where(Commission.sales_id == user.id)
    if user.role == "manager":
        return stmt.where(Commission.region == user.region)
    return stmt


def scope_documents(stmt: Select, user: User, public_only: bool = False) -> Select:
    if public_only or user.role == "public":
        return stmt.where(Document.visibility == "public")
    if user.role in {"sales", "manager"}:
        return stmt.where(
            (Document.visibility == "public")
            | (Document.visibility == "internal")
            | ((Document.visibility == "region") & (Document.region == user.region))
        )
    return stmt

