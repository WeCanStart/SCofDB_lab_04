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
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.main import app
from app.application.payment_service import PaymentService


@pytest.mark.asyncio
async def test_retry_without_idempotency_can_double_pay(db_session):
   """
   Тест демонстрации проблемы retry без идемпотентности.

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
   user_id = uuid.uuid4()
   order_id = uuid.uuid4()
   
   await db_session.execute(
      text("INSERT INTO users (id, name, email, created_at) VALUES (:id, :name, :email, datetime('now'))"),
      {"id": str(user_id), "name": "Test User", "email": "test@example.com"}
   )
   
   await db_session.execute(
      text("INSERT INTO orders (id, user_id, status, total_amount, created_at) VALUES (:id, :user_id, 'created', 100.0, datetime('now'))"),
      {"id": str(order_id), "user_id": str(user_id)}
   )
   
   await db_session.commit()
   
   async with AsyncClient(
      transport=ASGITransport(app=app),
      base_url="http://test"
   ) as client:
      
      async def attempt_payment_1():
         """Первая попытка оплаты."""
         try:
               response = await client.post(
                  "/api/payments/retry-demo",
                  json={"order_id": str(order_id), "mode": "unsafe"}
               )
               return {"success": True, "status_code": response.status_code, "body": response.json()}
         except Exception as e:
               return {"success": False, "error": str(e)}
      
      async def attempt_payment_2():
         """Вторая попытка оплаты (повторный запрос)."""
         try:
               response = await client.post(
                  "/api/payments/retry-demo",
                  json={"order_id": str(order_id), "mode": "unsafe"}
               )
               return {"success": True, "status_code": response.status_code, "body": response.json()}
         except Exception as e:
               return {"success": False, "error": str(e)}
      
      results = await asyncio.gather(
         attempt_payment_1(),
         attempt_payment_2(),
         return_exceptions=True
      )
   
   service = PaymentService(db_session)
   history = await service.get_payment_history(order_id)
   
   print(f"\n--- REPORT: Retry without Idempotency Key ---")
   print(f"Order ID: {order_id}")
   print(f"Total attempts: 2")
   print(f"Successful attempts: {sum(1 for r in results if isinstance(r, dict) and r.get('success'))}")
   print(f"Failed attempts: {sum(1 for r in results if isinstance(r, dict) and not r.get('success'))}")
   print(f"Paid events in history: {len(history)}")
   
   if len(history) > 1:
      print(f"RACE CONDITION DETECTED! Order was paid {len(history)} times!")
      for record in history:
         print(f"  - {record['changed_at']}: status = {record['status']}")
   else:
      print(f"No race condition. Order was paid {len(history)} time(s).")
   
   assert len(history) > 1, f"Ожидалось больше 1 записи об оплате (двойная оплата), получено: {len(history)}"
   
   await db_session.execute(text("DELETE FROM order_status_history WHERE order_id = :order_id"), {"order_id": str(order_id)})
   await db_session.execute(text("DELETE FROM orders WHERE id = :order_id"), {"order_id": str(order_id)})
   await db_session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": str(user_id)})
   await db_session.commit()
