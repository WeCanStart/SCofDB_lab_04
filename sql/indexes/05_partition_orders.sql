\timing on
\echo '=== PARTITION ORDERS BY DATE ==='

-- ============================================
-- TODO: Реализуйте партиционирование orders по дате
-- ============================================

-- Вариант A (рекомендуется): RANGE по created_at (месяц/квартал)
-- Вариант B: альтернативная разумная стратегия

DROP TABLE IF EXISTS orders_partitioned CASCADE;

-- Шаг 1: Подготовка структуры
-- TODO:
-- - создайте partitioned table (или shadow-таблицу для безопасной миграции)
-- - определите partition key = created_at
CREATE TABLE IF NOT EXISTS orders_partitioned (
    id UUID DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    total_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_orders_status FOREIGN KEY (status) REFERENCES order_statuses(status)
) PARTITION BY RANGE (created_at);

-- Шаг 2: Создание партиций
-- TODO:
-- - создайте набор партиций по диапазонам дат
-- - добавьте DEFAULT partition (опционально)
CREATE TABLE IF NOT EXISTS orders_2024_q1 PARTITION OF orders_partitioned
FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');

CREATE TABLE IF NOT EXISTS orders_2024_q2 PARTITION OF orders_partitioned
FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');

CREATE TABLE IF NOT EXISTS orders_2024_q3 PARTITION OF orders_partitioned
FOR VALUES FROM ('2024-07-01') TO ('2024-10-01');

CREATE TABLE IF NOT EXISTS orders_2024_q4 PARTITION OF orders_partitioned
FOR VALUES FROM ('2024-10-01') TO ('2025-01-01');

CREATE TABLE IF NOT EXISTS orders_2025_q1 PARTITION OF orders_partitioned
FOR VALUES FROM ('2025-01-01') TO ('2025-04-01');

CREATE TABLE IF NOT EXISTS orders_2025_q2 PARTITION OF orders_partitioned
FOR VALUES FROM ('2025-04-01') TO ('2025-07-01');

CREATE TABLE IF NOT EXISTS orders_2025_q3 PARTITION OF orders_partitioned
FOR VALUES FROM ('2025-07-01') TO ('2025-10-01');

CREATE TABLE IF NOT EXISTS orders_2025_q4 PARTITION OF orders_partitioned
FOR VALUES FROM ('2025-10-01') TO ('2026-01-01');

-- Шаг 3: Перенос данных
-- TODO:
-- - перенесите данные из исходной таблицы
-- - проверьте количество строк до/после
INSERT INTO orders_partitioned (id, user_id, status, total_amount, created_at)
SELECT id, user_id, status, total_amount, created_at
FROM orders;

-- Шаг 4: Индексы на партиционированной таблице
-- TODO:
-- - создайте нужные индексы (если требуется)
CREATE INDEX IF NOT EXISTS idx_orders_amt_gt_500
ON orders_partitioned (created_at DESC)
INCLUDE (user_id)
WHERE total_amount > 500;

-- Шаг 5: Проверка
-- TODO:
-- - ANALYZE
-- - проверка partition pruning на запросах по диапазону дат
ANALYZE orders_partitioned;
