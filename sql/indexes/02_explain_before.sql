\timing on
\echo '=== BEFORE OPTIMIZATION ==='

-- Рекомендуемые настройки для сравнимых замеров
SET max_parallel_workers_per_gather = 0;
SET work_mem = '32MB';
ANALYZE;

-- ============================================
-- TODO: Добавьте не менее 3 запросов
-- Для каждого обязательно: EXPLAIN (ANALYZE, BUFFERS)
-- ============================================

\echo '--- Q1: Фильтрация + сортировка (пример класса запроса) ---'
-- TODO: Подставьте свой запрос
-- Пример класса:
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT user_id FROM (
  SELECT user_id, created_at
  FROM orders
  WHERE total_amount > 500
  ORDER BY created_at DESC
  LIMIT 10000
) t;

\echo '--- Q2: Фильтрация по статусу + диапазону дат ---'
-- TODO: Подставьте свой запрос
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE status = 'paid'
  AND created_at >= timestamp '2025-01-01'
  AND created_at < timestamp '2025-04-01';

\echo '--- Q3: JOIN + GROUP BY ---'
-- TODO: Подставьте свой запрос
EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(oi.price * oi.quantity) AS total_revenue, o.status
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.created_at >= timestamp '2025-01-01'
  AND o.created_at < timestamp '2025-04-01'
  AND oi.price < 100
GROUP BY status
ORDER BY total_revenue DESC
LIMIT 2;

-- (Опционально) Q4: полный агрегат по периоду, который сложно ускорить индексами
