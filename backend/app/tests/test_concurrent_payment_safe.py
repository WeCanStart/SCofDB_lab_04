"""
Тест для демонстрации РЕШЕНИЯ проблемы race condition.

Этот тест должен ПРОХОДИТЬ, подтверждая, что при использовании
pay_order_safe() заказ оплачивается только один раз.
"""

import asyncio
import pytest
import uuid
import time
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.application.payment_service import PaymentService
from app.domain.exceptions import OrderAlreadyPaidError


# TODO: Настроить подключение к тестовой БД
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/marketplace"


@pytest.fixture
async def db_session():
    """
    Создать сессию БД для тестов.
    
    TODO: Реализовать фикстуру:
    1. Создать engine
    2. Создать session maker
    3. Открыть сессию
    4. Yield сессию
    5. Закрыть сессию после теста
    """
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
    """
    Создать тестовый заказ со статусом 'created'.
    
    TODO: Реализовать фикстуру (см. test_concurrent_payment_unsafe.py)
    """
    async with db_session.begin():
        user_id = uuid.uuid4()
        await db_session.execute(
            text("INSERT INTO users (id, name, email) VALUES (:id, :name, :email)"),
            {"id": user_id, "name": "Test User", "email": "test@example.com"},
        )

        order_id = uuid.uuid4()
        await db_session.execute(
            text("INSERT INTO orders (id, user_id, status, created_at) VALUES (:id, :user_id, 'created', NOW())"),
            {"id": order_id, "user_id": user_id}
        )

    yield order_id

    async with db_session.begin():
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


@pytest.mark.asyncio
async def test_concurrent_payment_safe_prevents_race_condition(db_session, test_order):
    """
    Тест демонстрирует решение проблемы race condition с помощью pay_order_safe().
    
    ОЖИДАЕМЫЙ РЕЗУЛЬТАТ: Тест ПРОХОДИТ, подтверждая, что заказ был оплачен только один раз.
    Это показывает, что метод pay_order_safe() защищен от конкурентных запросов.
    
    TODO: Реализовать тест следующим образом:
    
    1. Создать два экземпляра PaymentService с РАЗНЫМИ сессиями
       (это имитирует два независимых HTTP-запроса)
       
    2. Запустить два параллельных вызова pay_order_safe():
       
       async def payment_attempt_1():
           service1 = PaymentService(session1)
           return await service1.pay_order_safe(order_id)
           
       async def payment_attempt_2():
           service2 = PaymentService(session2)
           return await service2.pay_order_safe(order_id)
           
       results = await asyncio.gather(
           payment_attempt_1(),
           payment_attempt_2(),
           return_exceptions=True
       )
       
    3. Проверить результаты:
       - Одна попытка должна УСПЕШНО завершиться
       - Вторая попытка должна выбросить OrderAlreadyPaidError ИЛИ вернуть ошибку
       
       success_count = sum(1 for r in results if not isinstance(r, Exception))
       error_count = sum(1 for r in results if isinstance(r, Exception))
       
       assert success_count == 1, "Ожидалась одна успешная оплата"
       assert error_count == 1, "Ожидалась одна неудачная попытка"
       
    4. Проверить историю оплат:
       
       service = PaymentService(session)
       history = await service.get_payment_history(order_id)
       
       # ОЖИДАЕМ ОДНУ ЗАПИСЬ 'paid' - проблема решена!
       assert len(history) == 1, "Ожидалась 1 запись об оплате (БЕЗ RACE CONDITION!)"
       
    5. Вывести информацию об успешном решении:
       
       print(f"✅ RACE CONDITION PREVENTED!")
       print(f"Order {order_id} was paid only ONCE:")
       print(f"  - {history[0]['changed_at']}: status = {history[0]['status']}")
       print(f"Second attempt was rejected: {results[1]}")
    """
    order_id = test_order

    engine = create_async_engine(DATABASE_URL, echo=True, future=True)
    async_session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session1, async_session_maker() as session2:

        async def payment_attempt_1():
            service1 = PaymentService(session1)
            return await service1.pay_order_safe(order_id)

        async def payment_attempt_2():
            service2 = PaymentService(session2)
            return await service2.pay_order_safe(order_id)

        results = await asyncio.gather(
            payment_attempt_1(),
            payment_attempt_2(),
            return_exceptions=True
        )

    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = sum(1 for r in results if isinstance(r, Exception))

    assert success_count == 1, "Ожидалась одна успешная оплата"
    assert error_count == 1, "Ожидалась одна неудачная попытка"

    service = PaymentService(db_session)
    history = await service.get_payment_history(test_order)
    
    # ОЖИДАЕМ ОДНУ ЗАПИСЬ 'paid' - проблема решена!
    assert len(history) == 1, "Ожидалась 1 запись об оплате (БЕЗ RACE CONDITION!)"

    print(f"✅ RACE CONDITION PREVENTED!")
    print(f"Order {test_order} was paid only ONCE:")
    print(f"  - {history[0]['changed_at']}: status = {history[0]['status']}")
    print(f"Second attempt was rejected: {results[0]}")
    await db_session.commit()


@pytest.mark.asyncio
async def test_concurrent_payment_safe_with_explicit_timing(test_order):
    """
    Дополнительный тест: проверить работу блокировок с явной задержкой.
    
    TODO: Реализовать тест с добавлением задержки в первой транзакции:
    
    1. Первая транзакция:
       - Начать транзакцию
       - Заблокировать заказ (FOR UPDATE)
       - Добавить задержку (asyncio.sleep(1))
       - Оплатить
       - Commit
       
    2. Вторая транзакция (запустить через 0.1 секунды после первой):
       - Начать транзакцию
       - Попытаться заблокировать заказ (FOR UPDATE)
       - ДОЛЖНА ЖДАТЬ освобождения блокировки от первой транзакции
       - После освобождения - увидеть обновленный статус 'paid'
       - Выбросить OrderAlreadyPaidError
       
    3. Проверить временные метки:
       - Вторая транзакция должна завершиться ПОЗЖЕ первой
       - Разница должна быть >= 1 секунды (время задержки)
       
    Это подтверждает, что FOR UPDATE действительно блокирует строку.
    """
    order_id = test_order

    # локальный engine специально для теста: pool_size >= 2 и READ COMMITTED для предсказуемых блокировок
    engine = create_async_engine(
        DATABASE_URL,
        echo=True,
        pool_size=5,
        max_overflow=5,
        future=True,
    )
    SessionMaker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    session1 = SessionMaker()
    session2 = SessionMaker()

    times = {
        "t1_start": None, "t1_acquired": None, "t1_end": None,
        "t2_start": None, "t2_acquired": None, "t2_end": None,
    }
    pids = {"t1_pid": None, "t2_pid": None}

    async def dump_locks(label):
        """Diagnostics: print pg_locks and pg_blocking_pids snapshot via a fresh connection."""
        async with engine.connect() as inspect_conn:
            locks_q = text("""
                SELECT a.pid, a.usename, a.query, l.mode, l.granted, c.relname
                FROM pg_locks l
                JOIN pg_class c ON c.oid = l.relation
                LEFT JOIN pg_stat_activity a ON a.pid = l.pid
                WHERE c.relname = 'orders'
                ORDER BY a.pid NULLS LAST, l.granted DESC;
            """)
            res = await inspect_conn.execute(locks_q)
            rows = res.fetchall()
            print(f"--- LOCKS SNAPSHOT ({label}) ---")
            if not rows:
                print("(no locks rows)")
            for r in rows:
                print(r)

            # blocking relationships for our two pids (if known)
            if pids["t1_pid"] or pids["t2_pid"]:
                bq = text("""
                    SELECT pid, pg_blocking_pids(pid) AS blockers, state, query
                    FROM pg_stat_activity
                    WHERE pid = ANY(:pids)
                    ORDER BY pid;
                """)
                p_list = [x for x in (pids["t1_pid"], pids["t2_pid"]) if x is not None]
                res2 = await inspect_conn.execute(bq, {"pids": p_list})
                print("--- BLOCKING INFO ---")
                for r in res2.fetchall():
                    print(r)
            print(f"--- END LOCKS ({label}) ---")

    async def attempt1():
        """Первая транзакция: берет FOR UPDATE, держит 1s, делает UPDATE+history, коммит."""
        times["t1_start"] = time.time()
        # BEGIN
        async with session1.begin():
            # backend pid & isolation
            pid = (await session1.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            iso = (await session1.execute(text("SELECT current_setting('transaction_isolation')"))).scalar_one()
            pids["t1_pid"] = pid
            print(f"[T1] pid={pid} isolation={iso} t={time.time():.6f}")

            # SELECT FOR UPDATE (we record time AFTER fetchone())
            print(f"[T1] before SELECT FOR UPDATE {time.time():.6f}")
            res = await session1.execute(
                text("SELECT status FROM orders WHERE id = :order_id FOR UPDATE"),
                {"order_id": order_id}
            )
            row = res.fetchone()
            times["t1_acquired"] = time.time()
            print(f"[T1] after fetch (lock acquired?) {times['t1_acquired']:.6f} row={row}")
            # dump locks snapshot while holding lock
            await dump_locks("after T1 acquired")

            # hold lock for 1 second (simulate long processing)
            await asyncio.sleep(1.0)

            print(f"[T1] before UPDATE {time.time():.6f}")
            await session1.execute(
                text("UPDATE orders SET status = 'paid' WHERE id = :order_id AND status = 'created'"),
                {"order_id": order_id}
            )
            await session1.execute(
                text(
                    "INSERT INTO order_status_history (id, order_id, status, changed_at) "
                    "VALUES (gen_random_uuid(), :order_id, 'paid', NOW())"
                ),
                {"order_id": order_id}
            )
            print(f"[T1] ready to commit {time.time():.6f}")
        # COMMIT happens when exiting async with
        times["t1_end"] = time.time()
        print(f"[T1] committed at {times['t1_end']:.6f}")

        # dump locks after commit
        await dump_locks("after T1 commit")
        return "OK-1"

    async def attempt2():
        """Вторая транзакция: старт через 0.1s, пытается FOR UPDATE и должна ждать."""
        await asyncio.sleep(0.1)
        times["t2_start"] = time.time()
        try:
            async with session2.begin():
                pid = (await session2.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                iso = (await session2.execute(text("SELECT current_setting('transaction_isolation')"))).scalar_one()
                pids["t2_pid"] = pid
                print(f"[T2] pid={pid} isolation={iso} t={time.time():.6f}")

                # dump locks BEFORE issuing second SELECT (snapshot)
                await dump_locks("before T2 SELECT")

                print(f"[T2] before SELECT FOR UPDATE {time.time():.6f}")
                res = await session2.execute(
                    text("SELECT status FROM orders WHERE id = :order_id FOR UPDATE"),
                    {"order_id": order_id}
                )
                row = res.fetchone()
                times["t2_acquired"] = time.time()
                print(f"[T2] after fetch (lock acquired?) {times['t2_acquired']:.6f} row={row}")

                # dump locks after T2 fetch
                await dump_locks("after T2 acquired")

                if not row:
                    raise AssertionError("order not found in attempt2")
                # if row shows paid already -> raise
                if row[0] != "created":
                    raise OrderAlreadyPaidError(order_id)
                # otherwise try to update (unexpected in this test)
                await session2.execute(
                    text("UPDATE orders SET status = 'paid' WHERE id = :order_id AND status = 'created'"),
                    {"order_id": order_id}
                )
        except Exception as e:
            times["t2_end"] = time.time()
            print(f"[T2] ended with exception at {times['t2_end']:.6f}: {type(e).__name__}: {e!r}")
            # return exception to caller to assert on it
            return e
        else:
            times["t2_end"] = time.time()
            print(f"[T2] finished normally at {times['t2_end']:.6f}")
            return "OK-2"

    # запустим обе задачи параллельно
    task1 = asyncio.create_task(attempt1())
    task2 = asyncio.create_task(attempt2())

    results = await asyncio.gather(task1, task2, return_exceptions=True)

    # clean up
    await session1.close()
    await session2.close()
    await engine.dispose()

    # распечатаем для удобства
    print("TIMES:", times)
    print("PIDS:", pids)
    print("Results:", results)

    res1, res2 = results

    # проверки
    assert res1 == "OK-1", f"attempt1 unexpected result: {res1!r}"
    # ожидаем, что вторая вернёт OrderAlreadyPaidError (или другое исключение означающее, что увидела paid)
    assert isinstance(res2, OrderAlreadyPaidError) or (isinstance(res2, Exception) and isinstance(res2, OrderAlreadyPaidError.__class__)), \
        f"attempt2 expected OrderAlreadyPaidError, got: {res2!r}"

    # тайминги: вторая должна завершиться позже первой и задержка >= 1s
    assert times["t1_end"] is not None and times["t2_end"] is not None, "timestamps missing"
    assert times["t2_end"] > times["t1_end"], "attempt2 finished before attempt1 (unexpected)"
    wait_time = times["t2_acquired"] - times["t2_start"]
    assert wait_time >= 1.0 - 0.05, f"T2 did not wait for lock, waited only {wait_time:.3f}s"


if __name__ == "__main__":
    """
    Запуск теста:
    
    cd backend
    export PYTHONPATH=$(pwd)
    pytest app/tests/test_concurrent_payment_safe.py -v -s
    
    ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
    ✅ test_concurrent_payment_safe_prevents_race_condition PASSED
    
    Вывод должен показывать:
    ✅ RACE CONDITION PREVENTED!
    Order XXX was paid only ONCE:
      - 2024-XX-XX: status = paid
    Second attempt was rejected: OrderAlreadyPaidError(...)
    """
    pytest.main([__file__, "-v", "-s"])
