from fastapi import Header, HTTPException

from .schemas import User


# PoC identities. Replace X-Demo-User with verified JWT/OIDC claims in production.
DEMO_USERS = {
    "public": User(id="public", name="Public visitor", role="public"),
    "sales-jkt-1": User(id="sales-jkt-1", name="Ayu (Sales Jakarta)", role="sales", region="jakarta"),
    "sales-jkt-2": User(id="sales-jkt-2", name="Bima (Sales Jakarta)", role="sales", region="jakarta"),
    "sales-sby-1": User(id="sales-sby-1", name="Citra (Sales Surabaya)", role="sales", region="surabaya"),
    "manager-jkt": User(id="manager-jkt", name="Doni (Manager Jakarta)", role="manager", region="jakarta"),
    "manager-sby": User(id="manager-sby", name="Eka (Manager Surabaya)", role="manager", region="surabaya"),
    "admin": User(id="admin", name="Admin", role="admin"),
}


def current_user(x_demo_user: str = Header(default="public")) -> User:
    user = DEMO_USERS.get(x_demo_user)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown demo identity")
    return user

