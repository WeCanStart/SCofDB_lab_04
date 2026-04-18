"""
LAB 04: Демонстрация проблемы retry без идемпотентности.

Сценарий:
1) Клиент отправил запрос на оплату.
2) До получения ответа "сеть оборвалась" (моделируем повтором запроса).
3) Клиент повторил запрос БЕЗ Idempotency-Key.
4) В unsafe-режиме возможна двойная оплата.
"""

import asyncio
import pytest
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.application.payment_service import PaymentService


# TODO: Настроить подключение к тестовой БД
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/marketplace"


@pytest.fixture
async def db_session():
    """Создать сессию БД для тестов."""
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_order(db_session):
    """Создать тестовый заказ со статусом 'created'."""
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO users (id, name, email) VALUES (:id, :name, :email)"),
        {"id": user_id, "name": "Test User", "email": "test@example.com"}
    )

    await db_session.execute(
        text("INSERT INTO orders (id, user_id, status, created_at) VALUES (:id, :user_id, 'created', NOW())"),
        {"id": order_id, "user_id": user_id}
    )

    await db_session.commit()

    yield order_id

    await db_session.execute(
        text("DELETE FROM order_status_history WHERE order_id = :order_id"),
        {"order_id": order_id}
    )
    await db_session.execute(
        text("DELETE FROM orders WHERE id = :order_id"),
        {"order_id": order_id}
    )
    await db_session.execute(
        text("DELETE FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_retry_without_idempotency_can_double_pay(db_session, test_order):
    """
    TODO: Реализовать тест.

    Рекомендуемые шаги:
    1) Создать заказ в статусе created.
    2) Выполнить две параллельные попытки POST /api/payments/retry-demo
       с mode='unsafe' и БЕЗ заголовка Idempotency-Key.
    3) Проверить историю order_status_history:
       - paid-событий больше 1 (или иная метрика двойного списания).
    4) Вывести понятный отчёт в stdout:
       - сколько попыток
       - сколько paid в истории
       - почему это проблема.
    """
    order_id = test_order

    engine = create_async_engine(DATABASE_URL, echo=True, future=True)
    async_session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session1, async_session_maker() as session2:

        async def payment_attempt_1():
            service1 = PaymentService(session1)
            return await service1.pay_order_unsafe(order_id)

        async def payment_attempt_2():
            service2 = PaymentService(session2)
            return await service2.pay_order_unsafe(order_id)

        results = await asyncio.gather(
            payment_attempt_1(),
            payment_attempt_2(),
            return_exceptions=True
        )

    service = PaymentService(db_session)
    history = await service.get_payment_history(order_id)

    assert len(history) == 2, "Ожидалось 2 записи об оплате (RACE CONDITION!)"

    print(f"\n--- REPORT: Retry without Idempotency Key ---")
    print(f"Order ID: {order_id}")
    print(f"Total attempts: 2")
    print(f"Paid events in history: {len(history)}")
    print(f"RACE CONDITION DETECTED! Order was paid {len(history)} times!")
    for record in history:
        print(f"  - {record['changed_at']}: status = {record['status']}")