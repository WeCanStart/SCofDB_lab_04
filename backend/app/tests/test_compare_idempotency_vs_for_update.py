"""
LAB 04: Сравнение подходов
1) FOR UPDATE (решение из lab_02)
2) Idempotency-Key + middleware (lab_04)
"""

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
            user_result = await session.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": user_email}
            )
            user_row = user_result.fetchone()
            if user_row:
                await session.execute(
                    text("DELETE FROM users WHERE id = :user_id"),
                    {"user_id": user_row[0]}
                )


async def cleanup_idempotency_keys(engine):
    """Очистить таблицу idempotency_keys."""
    async with AsyncSession(engine) as session:
        await session.execute(text("DELETE FROM idempotency_keys"))
        await session.commit()


@pytest.mark.asyncio
async def test_compare_for_update_and_idempotency_behaviour(pg_engine):
    """
    Сравнительный тест двух подходов:
    
    1) FOR UPDATE (pay_order_safe / mode='for_update'):
       - Защита от гонки на уровне БД
       - Второй повторный вызов вернёт бизнес-ошибку "already paid"
       
    2) Idempotency-Key + middleware (mode='unsafe' + Idempotency-Key):
       - Второй вызов возвращает кэшированный успешный ответ
       - Без повторного списания
    
    Вывод:
    - FOR UPDATE решает проблему race condition на уровне БД
    - Idempotency-Key решает проблему повторного запроса от клиента
    - Эти подходы НЕ взаимоисключающие - они решают РАЗНЫЕ проблемы
    """
    user_email_1 = f"compare1_{uuid.uuid4()}@example.com"
    user_email_2 = f"compare2_{uuid.uuid4()}@example.com"
    order_id_1 = await create_order(pg_engine, user_email_1)
    order_id_2 = await create_order(pg_engine, user_email_2)

    try:
        await cleanup_idempotency_keys(pg_engine)

        async with AsyncClient(app=app, base_url="http://test") as client:
            print("\n" + "="*60)
            print("ЧАСТЬ 1: FOR UPDATE (lab_02)")
            print("="*60)
            
            response1 = await client.post(
                "/api/payments/retry-demo",
                json={"order_id": str(order_id_1), "mode": "for_update"}
            )
            print(f"Первый запрос (for_update): {response1.status_code} - {response1.json()}")
            
            response2 = await client.post(
                "/api/payments/retry-demo",
                json={"order_id": str(order_id_1), "mode": "for_update"}
            )
            print(f"Повторный запрос (for_update): {response2.status_code} - {response2.json()}")
            
            print("\n--- Анализ FOR UPDATE ---")
            if response2.status_code == 200:
                print("⚠️ Оба запроса прошли успешно (неожиданно для FOR UPDATE)")
            else:
                print(f"✅ Второй запрос отклонён: {response2.json()['detail']}")
            
            await cleanup_idempotency_keys(pg_engine)
            
            print("\n" + "="*60)
            print("ЧАСТЬ 2: Idempotency-Key (lab_04)")
            print("="*60)
            
            headers = {"Idempotency-Key": "compare-test-key-123"}
            payload = {"order_id": str(order_id_2), "mode": "unsafe"}
            
            response3 = await client.post(
                "/api/payments/retry-demo",
                json=payload,
                headers=headers
            )
            print(f"Первый запрос (unsafe + Idempotency-Key): {response3.status_code} - {response3.json()}")
            
            response4 = await client.post(
                "/api/payments/retry-demo",
                json=payload,
                headers=headers
            )
            print(f"Повторный запрос (unsafe + Idempotency-Key): {response4.status_code}")
            print(f"  X-Idempotency-Replayed: {response4.headers.get('X-Idempotency-Replayed')}")
            print(f"  Body: {response4.json()}")
            
            print("\n--- Анализ Idempotency-Key ---")
            if response4.headers.get("X-Idempotency-Replayed") == "true":
                print("✅ Второй запрос вернул кэшированный ответ!")
            
            service = PaymentService(AsyncSession(pg_engine))
            history = await service.get_payment_history(order_id_2)
            print(f"  История оплат для order_id_2: {len(history)} записей")

        print("\n" + "="*60)
        print("ВЫВОД: ЧЕМ ОТЛИЧАЮТСЯ ПОДХОДЫ")
        print("="*60)
        print("""
FOR UPDATE (lab_02):
  - Цель: Защита от race condition (двух одновременных запросов)
  - Как работает: Блокировка строки в БД
  - Результат повтора: Бизнес-ошибка "already paid" или аналогичная
  - Уровень: База данных

Idempotency-Key (lab_04):
  - Цель: Защита от повторного запроса клиента (retry after network error)
  - Как работает: Кэширование ответа по ключу
  - Результат повтора: Кэшированный успешный ответ
  - Уровень: Приложение (middleware)

ПОЧЕМУ ОНИ НЕ ВЗАИМОИСКЛЮЧАЮЩИЕ:
  1) FOR UPDATE не защищает от клиентского retry (клиент может повторить)
  2) Idempotency-Key не защищает от race condition (два клиента одновременно)
  3) Вместе они обеспечивают полную защиту:
     - Idempotency-Key обрабатывает retry
     - FOR UPDATE обрабатывает race condition
""")
        print("="*60)

    finally:
        await cleanup_order(pg_engine, order_id_1, user_email_1)
        await cleanup_order(pg_engine, order_id_2, user_email_2)
        await cleanup_idempotency_keys(pg_engine)