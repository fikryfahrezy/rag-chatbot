from fastapi import Header, HTTPException

from .schemas import User


# PoC identities. Replace X-Demo-User with verified JWT/OIDC claims in production.
DEMO_REGIONS = ("jakarta", "surabaya")


DEMO_USERS = {
    "sales-jkt-1": User(id="sales-jkt-1", name="Sales 1 — Jakarta", group="A", role="sales", region="jakarta"),
    "sales-jkt-2": User(id="sales-jkt-2", name="Sales 2 — Jakarta", group="A", role="sales", region="jakarta"),
    "sales-sby-1": User(id="sales-sby-1", name="Sales 1 — Surabaya", group="A", role="sales", region="surabaya"),
    "manager-jkt": User(id="manager-jkt", name="Sales Manager — Jakarta", group="A", role="manager", region="jakarta"),
    "manager-sby": User(id="manager-sby", name="Sales Manager — Surabaya", group="A", role="manager", region="surabaya"),
    "public": User(id="public", name="Public visitor", group="B", role="public"),
    "employee-jkt": User(id="employee-jkt", name="Employee — Jakarta", group="C", role="employee", region="jakarta"),
    "employee-sby": User(id="employee-sby", name="Employee — Surabaya", group="C", role="employee", region="surabaya"),
    "admin": User(id="admin", name="Administrator", group="ALL", role="admin"),
}


def current_user(x_demo_user: str = Header(default="public")) -> User:
    user = DEMO_USERS.get(x_demo_user)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown demo identity")
    return user
