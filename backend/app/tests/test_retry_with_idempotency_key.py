"""
LAB 04: Проверка идемпотентного повтора запроса.

Цель:
При повторном запросе с тем же Idempotency-Key вернуть
кэшированный результат без повторного списания.
"""

import os
import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

from app.main import app
from app.application.payment_service import PaymentService


DATABASE_URL = "postgresql+asyncpg://postgres:postgres@db:5432/marketplace"


@pytest.fixture(scope="module")
async def pg_engine():
    import os
    print(f"\n=== ENV: {os.environ.get('DATABASE_URL')} ===")
    print(f"\n=== HARD: {DATABASE_URL} ===")
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
    yield engine
    await engine.dispose()


async def create_order(engine, user_email):
    """Создать тестовый заказ со статусом 'created'."""
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    
    async with AsyncSession(engine) as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO users (id, email, name, created_at)
                    VALUES (:user_id, :email, :name, NOW())
                """),
                {"user_id": user_id, "email": user_email, "name": "Test"}
            )
            await session.execute(
                text("""
                    INSERT INTO orders (id, user_id, status, total_amount, created_at)
                    VALUES (:order_id, :user_id, 'created', 100.00, NOW())
                """),
                {"order_id": order_id, "user_id": user_id}
            )
    
    return order_id


async def cleanup_order(engine, order_id, user_email):
    """Очистить тестовые данные."""
    async with AsyncSession(engine) as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM order_status_history WHERE order_id = :order_id"),
                {"order_id": order_id}
            )
            await session.execute(
                text("DELETE FROM orders WHERE id = :order_id"),
                {"order_id": order_id}
            )
            await session.execute(
                text("DELETE FROM users WHERE email = :email"),
                {"email": user_email}
            )


async def cleanup_idempotency_keys(engine):
    """Очистить таблицу idempotency_keys."""
    async with AsyncSession(engine) as session:
        await session.execute(text("DELETE FROM idempotency_keys"))
        await session.commit()


@pytest.mark.asyncio
async def test_retry_with_same_key_returns_cached_response(pg_engine):
    """
    TODO: Реализовать тест.

    Рекомендуемые шаги:
    1) Создать заказ в статусе created.
    2) Сделать первый POST /api/payments/retry-demo (mode='unsafe')
       с заголовком Idempotency-Key: fixed-key-123.
    3) Повторить тот же POST с тем же ключом и тем же payload.
    4) Проверить:
       - второй ответ пришёл из кэша (через признак, который вы добавите,
         например header X-Idempotency-Replayed=true),
       - в order_status_history только одно событие paid,
       - в idempotency_keys есть запись completed с response_body/status_code.
    """
    print(f"\n=== TEST: DATABASE_URL = {DATABASE_URL} ===")
    user_email = f"test_{uuid.uuid4()}@example.com"
    order_id = await create_order(pg_engine, user_email)

    try:
        await cleanup_idempotency_keys(pg_engine)

        async with AsyncClient(app=app, base_url="http://test") as client:
            headers = {"Idempotency-Key": "fixed-key-123"}
            payload = {"order_id": str(order_id), "mode": "unsafe"}

            response1 = await client.post(
                "/api/payments/retry-demo",
                json=payload,
                headers=headers
            )
            assert response1.status_code == 200

            response2 = await client.post(
                "/api/payments/retry-demo",
                json=payload,
                headers=headers
            )
            assert response2.status_code == 200
            assert response2.headers.get("X-Idempotency-Replayed") == "true"

        async with AsyncSession(pg_engine) as session:
            service = PaymentService(session)
            history = await service.get_payment_history(order_id)

        assert len(history) == 1, "Оплата должна произойти только один раз"

        async with AsyncSession(pg_engine) as session:
            result = await session.execute(
                text("""
                    SELECT status, status_code, response_body
                    FROM idempotency_keys
                    WHERE idempotency_key = 'fixed-key-123'
                """)
            )
            row = result.fetchone()
            assert row is not None, "Запись в idempotency_keys не найдена"
            assert row.status == "completed"

        print("\n--- TEST PASSED: Idempotency Key works correctly ---")
        print(f"First response: {response1.json()}")
        print(f"Second response from cache: {response2.headers.get('X-Idempotency-Replayed')}")
        print(f"Paid events: {len(history)}")

    finally:
        await cleanup_order(pg_engine, order_id, user_email)
        await cleanup_idempotency_keys(pg_engine)


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_conflict(pg_engine):
    """
    TODO: Реализовать негативный тест.

    Один и тот же Idempotency-Key нельзя использовать с другим payload.
    Ожидается 409 Conflict (или эквивалентная бизнес-ошибка).
    """
    user_email = f"test_{uuid.uuid4()}@example.com"
    order_id = await create_order(pg_engine, user_email)

    try:
        await cleanup_idempotency_keys(pg_engine)

        async with AsyncClient(app=app, base_url="http://test") as client:
            headers = {"Idempotency-Key": "same-key"}

            payload1 = {"order_id": str(order_id), "mode": "unsafe"}

            response1 = await client.post(
                "/api/payments/retry-demo",
                json=payload1,
                headers=headers
            )
            assert response1.status_code == 200

            # Попытка использовать тот же ключ с другим payload
            payload2 = {"order_id": str(order_id), "mode": "safe"}

            response2 = await client.post(
                "/api/payments/retry-demo",
                json=payload2,
                headers=headers
            )

            assert response2.status_code == 409

        print("\n--- TEST PASSED: Conflict on different payload ---")
        print(f"First status: {response1.status_code}")
        print(f"Second status (expected 409): {response2.status_code}")

    finally:
        await cleanup_order(pg_engine, order_id, user_email)
        await cleanup_idempotency_keys(pg_engine)