"""Сервис для демонстрации конкурентных оплат.

Этот модуль содержит два метода оплаты:
1. pay_order_unsafe() - небезопасная реализация (READ COMMITTED без блокирово2. pay_order_safe() - безопасная реализация (READ COMMITTED с FOR UPDATE)
"""

import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError

from app.domain.exceptions import OrderAlreadyPaidError, OrderNotFoundError


class PaymentService:
    """Сервис для обработки платежей с разными уровнями изоляции."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def pay_order_unsafe(self, order_id: uuid.UUID) -> dict:
        """
        НЕБЕЗОПАСНАЯ реализация оплаты заказа.
        
        Использует READ COMMITTED (по умолчанию) без блокировок.
        ЛОМАЕТСЯ при конкурентных запросах - может привести к двойной оплате!
        
        TODO: Реализовать метод следующим образом:
        
        1. Прочитать текущий статус заказа:
           SELECT status FROM orders WHERE id = :order_id
           
        2. Проверить, что статус = 'created'
           Если нет - выбросить OrderAlreadyPaidError
           
        3. Изменить статус на 'paid':
           UPDATE orders SET status = 'paid' 
           WHERE id = :order_id AND status = 'created'
           
        4. Записать изменение в историю:
           INSERT INTO order_status_history (id, order_id, status, changed_at)
           VALUES (gen_random_uuid(), :order_id, 'paid', NOW())
           
        5. Сделать commit
        
        ВАЖНО: НЕ используйте FOR UPDATE!
        ВАЖНО: НЕ меняйте уровень изоляции (оставьте READ COMMITTED по умолчанию)!
        
        Args:
            order_id: ID заказа для оплаты
            
        Returns:
            dict с информацией о заказе после оплаты
            
        Raises:
            OrderNotFoundError: если заказ не найден
            OrderAlreadyPaidError: если заказ уже оплачен
        """
        # TODO: Реализовать логику оплаты БЕЗ блокировок
        async with self.session.begin():
            res = await self.session.execute(
                text("SELECT status FROM orders WHERE id = :order_id"),
                {"order_id": order_id}
            )
            row = res.fetchone()
            if not row:
                raise OrderNotFoundError(order_id)
            
            current_status = row[0]
            if current_status != "created":
                raise OrderAlreadyPaidError(order_id)
            
            # ВАЖНО: Нет проверки rowcount, чтобы разрешить гонку данных
            await self.session.execute(
                text("UPDATE orders SET status = 'paid' WHERE id = :order_id AND status = 'created'"),
                {"order_id": str(order_id)}
            )
            
            await self.session.execute(
                text(
                    "INSERT INTO order_status_history (id, order_id, status, changed_at) "
                    "VALUES (gen_random_uuid(), :order_id, 'paid', NOW())"
                ),
                {"order_id": str(order_id)}
            )
        
        final = await self.session.execute(
            text("SELECT id, user_id, status, total_amount, created_at FROM orders WHERE id = :order_id"),
            {"order_id": order_id}
        )
        final_row = final.fetchone()
        if not final_row:
            raise OrderNotFoundError(order_id)
        return dict(final_row._mapping)

    async def pay_order_safe(self, order_id: uuid.UUID) -> dict:
        """
        БЕЗОПАСНАЯ реализация оплаты заказа.
        
        Использует REPEATABLE READ + FOR UPDATE для предотвращения race condition.
        Корректно работает при конкурентных запросах.
        
        TODO: Реализовать метод следующим образом:
        
        1. Установить уровень изоляции REPEATABLE READ:
           await self.session.execute(
               text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
           )
           
        2. Заблокировать строку заказа для обновления:
           SELECT status FROM orders WHERE id = :order_id FOR UPDATE
           
           ВАЖНО: FOR UPDATE гарантирует, что другие транзакции будут ЖДАТЬ
           освобождения блокировки. Это предотвращает race condition.
           
        3. Проверить, что статус = 'created'
           Если нет - выбросить OrderAlreadyPaidError
           
        4. Изменить статус на 'paid':
           UPDATE orders SET status = 'paid' 
           WHERE id = :order_id AND status = 'created'
           
        5. Записать изменение в историю:
           INSERT INTO order_status_history (id, order_id, status, changed_at)
           VALUES (gen_random_uuid(), :order_id, 'paid', NOW())
           
        6. Сделать commit
        
        ВАЖНО: Обязательно используйте FOR UPDATE!
        ВАЖНО: Обязательно установите REPEATABLE READ!
        
        Args:
            order_id: ID заказа для оплаты
            
        Returns:
            dict с информацией о заказе после оплаты
            
        Raises:
            OrderNotFoundError: если заказ не найден
            OrderAlreadyPaidError: если заказ уже оплачен
        """
        # TODO: Реализовать логику оплаты С блокировками
        try:
            await self.session.execute(
               text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            )
            res = await self.session.execute(
                text("SELECT status FROM orders WHERE id = :order_id FOR UPDATE"),
                {"order_id": order_id}
            )
            row = res.fetchone()

            if not row:
                raise OrderNotFoundError(order_id)

            if row[0] != "created":
                raise OrderAlreadyPaidError(order_id)

            upd = await self.session.execute(
                text("UPDATE orders SET status = 'paid' WHERE id = :order_id AND status = 'created'"),
                {"order_id": str(order_id)}
            )
            if getattr(upd, "rowcount", 0) == 0:
                raise OrderAlreadyPaidError(order_id)
            
            await self.session.execute(
                text(
                    "INSERT INTO order_status_history (id, order_id, status, changed_at) "
                    "VALUES (gen_random_uuid(), :order_id, 'paid', NOW())"
                ),
                {"order_id": str(order_id)}
            )
            await self.session.commit()
        
            final = await self.session.execute(
                text("SELECT id, user_id, status, total_amount, created_at FROM orders WHERE id = :order_id"),
                {"order_id": order_id}
            )
            final_row = final.fetchone()
            if not final_row:
                raise OrderNotFoundError(order_id)
            return dict(final_row._mapping)

        except DBAPIError as e:
            if e.orig is not None and hasattr(e.orig, 'sqlstate'):
                sqlstate = getattr(e.orig, 'sqlstate', None)
            if sqlstate == '40001':
                await self.session.rollback()
                raise OrderAlreadyPaidError(order_id) from e
            raise
    async def get_payment_history(self, order_id: uuid.UUID) -> list[dict]:
        """
        Получить историю оплат для заказа.
        
        Используется для проверки, сколько раз был оплачен заказ.
        
        TODO: Реализовать метод:
        
        SELECT id, order_id, status, changed_at
        FROM order_status_history
        WHERE order_id = :order_id AND status = 'paid'
        ORDER BY changed_at
        
        Args:
            order_id: ID заказа
            
        Returns:
            Список словарей с записями об оплате
        """
        # TODO: Реализовать получение истории оплат
        res = await self.session.execute(
            text(
                "SELECT id, order_id, status, changed_at "
                "FROM order_status_history "
                "WHERE order_id = :order_id AND status = 'paid' "
                "ORDER BY changed_at"
            ),
            {"order_id": str(order_id)}
        )
        return [dict(row._mapping) for row in res.fetchall()]