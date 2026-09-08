from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Commission, Inventory, ModelSetting, Order


def seed(session: Session) -> None:
    if session.scalar(select(func.count(Order.id))):
        return

    session.add_all(
        [
            Order(order_no="ORD-1001", customer="PT Maju", product="Router Pro", status="diproses", amount=12_500_000, sales_id="sales-jkt-1", region="jakarta"),
            Order(order_no="ORD-1002", customer="CV Terang", product="Switch 24P", status="dikirim", amount=8_750_000, sales_id="sales-jkt-2", region="jakarta"),
            Order(order_no="ORD-2001", customer="PT Timur", product="Access Point", status="selesai", amount=15_000_000, sales_id="sales-sby-1", region="surabaya"),
            Commission(sales_id="sales-jkt-1", region="jakarta", period="2026-09", amount=625_000),
            Commission(sales_id="sales-jkt-2", region="jakarta", period="2026-09", amount=437_500),
            Commission(sales_id="sales-sby-1", region="surabaya", period="2026-09", amount=750_000),
            Inventory(sku="RTR-PRO", product="Router Pro", stock=18, warehouse_region="jakarta"),
            Inventory(sku="SWT-24", product="Switch 24P", stock=7, warehouse_region="jakarta"),
            Inventory(sku="AP-01", product="Access Point", stock=31, warehouse_region="surabaya"),
            ModelSetting(task="database_planner", provider="demo", model="deterministic-router"),
            ModelSetting(task="database_answer", provider="demo", model="template-id"),
            ModelSetting(task="pdf_answer", provider="demo", model="extractive-id"),
        ]
    )
    session.commit()

