from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Commission, Order
from app.operations import answer_operation
from app.schemas import User


def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_sales_cannot_read_another_sales_order():
    with db_session() as db:
        db.add_all([
            Order(order_no="ORD-1", customer="Mine", product="A", status="new", amount=1, sales_id="alice", region="west"),
            Order(order_no="ORD-2", customer="Other", product="B", status="secret", amount=2, sales_id="bob", region="west"),
        ])
        db.commit()
        alice = User(id="alice", name="Alice", role="sales", region="west")
        result = answer_operation(db, "status ORD-2", alice)
        assert "tidak ditemukan" in result.answer
        assert "secret" not in result.answer


def test_manager_only_sees_own_region_commission():
    with db_session() as db:
        db.add_all([
            Commission(sales_id="alice", region="west", period="2026-09", amount=100),
            Commission(sales_id="bob", region="east", period="2026-09", amount=900),
        ])
        db.commit()
        manager = User(id="m-west", name="Manager", role="manager", region="west")
        result = answer_operation(db, "berapa komisi?", manager)
        assert "100" in result.answer
        assert "900" not in result.answer

