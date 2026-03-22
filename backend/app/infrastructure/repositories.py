"""Реализация репозиториев с использованием SQLAlchemy."""

import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, List, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import User
from app.domain.order import Order, OrderItem, OrderStatus, OrderStatusChange


class UserRepository:
    """Репозиторий для User."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # TODO: Реализовать save(user: User) -> None
    # Используйте INSERT ... ON CONFLICT DO UPDATE
    async def save(self, user: User) -> None:
        sql = text(
            """
            INSERT INTO users (id, email, name, created_at)
            VALUES (:id, :email, :name, :created_at)
            ON CONFLICT (id) DO UPDATE
              SET email = EXCLUDED.email,
                  name = EXCLUDED.name,
                  created_at = EXCLUDED.created_at
            """
        )
        params = {
            "id": str(user.id) if user.id is not None else str(uuid.uuid4()),
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at if getattr(user, "created_at", None) is not None else datetime.now(UTC),
        }
        await self.session.execute(sql, params)
        await self.session.commit()

    # TODO: Реализовать find_by_id(user_id: UUID) -> Optional[User]
    async def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        sql = text(
            """
            SELECT id, email, name, created_at
            FROM users
            WHERE id = :id
            """
        )
        result = await self.session.execute(sql, {"id": str(user_id)})
        row = result.mappings().first()
        if not row:
            return None

        return User(
            email=row["email"],
            name=row["name"],
            id=row["id"],
            created_at=row["created_at"],
        )

    # TODO: Реализовать find_by_email(email: str) -> Optional[User]
    async def find_by_email(self, email: str) -> Optional[User]:
        sql = text(
            """
            SELECT id, email, name, created_at
            FROM users
            WHERE email = :email
            """
        )
        result = await self.session.execute(sql, {"email": email})
        row = result.mappings().first()
        if not row:
            return None

        return User(
            email=row["email"],
            name=row["name"],
            id=row["id"],
            created_at=row["created_at"],
        )

    # TODO: Реализовать find_all() -> List[User]
    async def find_all(self) -> List[User]:
        sql = text(
            """
            SELECT id, email, name, created_at
            FROM users
            ORDER BY created_at
            """
        )
        result = await self.session.execute(sql)
        rows = result.mappings().all()
        users: List[User] = []
        for row in rows:
            users.append(
                User(
                    email=row["email"],
                    name=row["name"],
                    id=row["id"],
                    created_at=row["created_at"],
                )
            )
        return users


class OrderRepository:
    """Репозиторий для Order."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # TODO: Реализовать save(order: Order) -> None
    # Сохранить заказ, товары и историю статусов
    async def save(self, order: Order) -> None:
        sql_order = text(
            """
            INSERT INTO orders (id, user_id, status, total_amount, created_at)
            VALUES (:id, :user_id, :status, :total_amount, :created_at)
            ON CONFLICT (id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                status = EXCLUDED.status,
                total_amount = EXCLUDED.total_amount,
                created_at = EXCLUDED.created_at
            """
        )
        order_id = str(order.id) if getattr(order, "id", None) is not None else str(uuid.uuid4())
        params_order = {
            "id": order_id,
            "user_id": str(getattr(order, "user_id", getattr(order, "user", None))),
            "status": (getattr(order, "status").value if hasattr(getattr(order, "status", None), "value") else getattr(order, "status")),
            "total_amount": float(getattr(order, "total_amount", 0)),
            "created_at": getattr(order, "created_at", datetime.now(UTC)),
        }
        await self.session.execute(sql_order, params_order)

        sql_delete_items = text("DELETE FROM order_items WHERE order_id = :order_id")
        await self.session.execute(sql_delete_items, {"order_id": order_id})

        items: Iterable = getattr(order, "items", []) or []
        for item in items:
            item_id = str(getattr(item, "id", uuid.uuid4()))
            sql_insert_item = text(
                """
                INSERT INTO order_items (id, order_id, product_name, price, quantity)
                VALUES (:id, :order_id, :product_name, :price, :quantity)
                """
            )
            params_item = {
                "id": item_id,
                "order_id": order_id,
                "product_name": getattr(item, "product_name"),
                "price": float(getattr(item, "price", 0)),
                "quantity": int(getattr(item, "quantity", 0)),
            }
            await self.session.execute(sql_insert_item, params_item)

        sql_delete_history = text("DELETE FROM order_status_history WHERE order_id = :order_id")
        await self.session.execute(sql_delete_history, {"order_id": order_id})

        history: Iterable = getattr(order, "history", []) or getattr(order, "status_history", []) or []
        for h in history:
            hist_id = str(getattr(h, "id", uuid.uuid4()))
            status_val = (getattr(h, "status").value if hasattr(getattr(h, "status", None), "value") else getattr(h, "status"))
            changed_at = getattr(h, "changed_at", datetime.now(UTC))
            sql_insert_hist = text(
                """
                INSERT INTO order_status_history (id, order_id, status, changed_at)
                VALUES (:id, :order_id, :status, :changed_at)
                """
            )
            params_hist = {
                "id": hist_id,
                "order_id": order_id,
                "status": status_val,
                "changed_at": changed_at,
            }
            await self.session.execute(sql_insert_hist, params_hist)

        await self.session.commit()

    # TODO: Реализовать find_by_id(order_id: UUID) -> Optional[Order]
    # Загрузить заказ со всеми товарами и историей
    # Используйте object.__new__(Order) чтобы избежать __post_init__
    async def find_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        sql_order = text(
            """
            SELECT id, user_id, status, total_amount, created_at
            FROM orders
            WHERE id = :id
            """
        )
        result = await self.session.execute(sql_order, {"id": str(order_id)})
        row = result.mappings().first()
        if not row:
            return None

        order_obj: Order = object.__new__(Order)

        order_obj.id = row["id"]
        order_obj.user_id = row["user_id"]
        order_obj.status = OrderStatus(row["status"])
        order_obj.total_amount = row["total_amount"]
        order_obj.created_at = row["created_at"]

        sql_items = text(
            """
            SELECT id, product_name, price, quantity
            FROM order_items
            WHERE order_id = :order_id
            ORDER BY id
            """
        )
        res_items = await self.session.execute(sql_items, {"order_id": str(order_id)})
        items_rows = res_items.mappings().all()
        item_objs: List[OrderItem] = []
        for r in items_rows:
            item_obj: OrderItem = object.__new__(OrderItem)
            item_obj.id = r["id"]
            item_obj.order_id = order_id
            item_obj.product_name = r["product_name"]
            item_obj.price = r["price"]
            item_obj.quantity = int(r["quantity"])
            item_objs.append(item_obj)
        order_obj.items = item_objs

        sql_history = text(
            """
            SELECT id, status, changed_at
            FROM order_status_history
            WHERE order_id = :order_id
            ORDER BY changed_at
            """
        )
        res_hist = await self.session.execute(sql_history, {"order_id": str(order_id)})
        hist_rows = res_hist.mappings().all()
        hist_objs: List[OrderStatusChange] = []
        for r in hist_rows:
            h_obj: OrderStatusChange = object.__new__(OrderStatusChange)
            h_obj.id = r["id"]
            h_obj.order_id = order_id
            h_obj.status = OrderStatus(r["status"])
            h_obj.changed_at = r["changed_at"]
            hist_objs.append(h_obj)
        order_obj.status_history = hist_objs

        return order_obj

    # TODO: Реализовать find_by_user(user_id: UUID) -> List[Order]
    async def find_by_user(self, user_id: uuid.UUID) -> List[Order]:
        sql = text(
            """
            SELECT id
            FROM orders
            WHERE user_id = :user_id
            ORDER BY created_at
            """
        )
        result = await self.session.execute(sql, {"user_id": str(user_id)})
        rows = result.mappings().all()
        orders: List[Order] = []
        for r in rows:
            oid = r["id"]
            order = await self.find_by_id(oid)
            if order is not None:
                orders.append(order)
        return orders

    # TODO: Реализовать find_all() -> List[Order]
    async def find_all(self) -> List[Order]:
        sql = text(
            """
            SELECT id
            FROM orders
            ORDER BY created_at
            """
        )
        result = await self.session.execute(sql)
        rows = result.mappings().all()
        orders: List[Order] = []
        for r in rows:
            oid = r["id"]
            order = await self.find_by_id(oid)
            if order is not None:
                orders.append(order)
        return orders
