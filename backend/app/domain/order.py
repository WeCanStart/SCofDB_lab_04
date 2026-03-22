"""Доменные сущности заказа."""

import uuid
from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import List
from dataclasses import dataclass, field

from .exceptions import (
    OrderAlreadyPaidError,
    OrderCancelledError,
    InvalidQuantityError,
    InvalidPriceError,
    InvalidAmountError,
)


# TODO: Реализовать OrderStatus (str, Enum)
# Значения: CREATED, PAID, CANCELLED, SHIPPED, COMPLETED
class OrderStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    CANCELLED = "cancelled"
    SHIPPED = "shipped"
    COMPLETED = "completed"


# TODO: Реализовать OrderItem (dataclass)
# Поля: product_name, price, quantity, id, order_id
# Свойство: subtotal (price * quantity)
# Валидация: quantity > 0, price >= 0
@dataclass
class OrderItem:
    product_name: str
    price: Decimal
    quantity: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    order_id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def subtotal(self) -> Decimal:
        return self.price * self.quantity
    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise InvalidQuantityError(self.quantity)
        if self.price < 0:
            raise InvalidPriceError(self.price)

# TODO: Реализовать OrderStatusChange (dataclass)
# Поля: order_id, status, changed_at, id
@dataclass
class OrderStatusChange:
    order_id: uuid.UUID
    status: OrderStatus
    changed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: uuid.UUID = field(default_factory=uuid.uuid4)


# TODO: Реализовать Order (dataclass)
# Поля: user_id, id, status, total_amount, created_at, items, status_history
# Методы:
#   - add_item(product_name, price, quantity) -> OrderItem
#   - pay() -> None  [КРИТИЧНО: нельзя оплатить дважды!]
#   - cancel() -> None
#   - ship() -> None
#   - complete() -> None
@dataclass
class Order:
    user_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: OrderStatus = OrderStatus.CREATED
    total_amount: Decimal = Decimal("0.00")
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    items: List[OrderItem] = field(default_factory=list)
    status_history: List[OrderStatusChange] = field(default_factory=list)

    def __post_init__(self):
        self.status_history.append(
            OrderStatusChange(order_id=self.id, status=OrderStatus.CREATED)
        )

    def _change_status(self, new_status: OrderStatus) -> None:
        self.status = new_status
        self.status_history.append(
            OrderStatusChange(order_id=self.id, status=new_status)
        )

    def add_item(self, product_name: str, price: Decimal, quantity: int) -> OrderItem:
        item = OrderItem(product_name=product_name, price=price, quantity=quantity, order_id=self.id)
        self.items.append(item)
        self.total_amount += item.subtotal
        if self.total_amount < 0:
            raise InvalidAmountError(self.total_amount)
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(self.id)
        return item

    def pay(self) -> None:
        if self.status == OrderStatus.PAID:
            raise OrderAlreadyPaidError(self.id)
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(self.id)
        self._change_status(OrderStatus.PAID)

    def cancel(self) -> None:
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(self.id)
        if self.status == OrderStatus.PAID:
            raise OrderAlreadyPaidError(self.id)
        self._change_status(OrderStatus.CANCELLED)

    def ship(self) -> None:
        if self.status != OrderStatus.PAID:
            raise ValueError(f"Only paid orders can be shipped. Current status: {self.status}")
        self._change_status(OrderStatus.SHIPPED)

    def complete(self) -> None:
        if self.status != OrderStatus.SHIPPED:
            raise ValueError(f"Only shipped orders can be completed. Current status: {self.status}")
        self._change_status(OrderStatus.COMPLETED)
