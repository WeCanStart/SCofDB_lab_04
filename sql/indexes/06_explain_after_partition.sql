\timing on
\echo '=== AFTER PARTITIONING ==='

SET max_parallel_workers_per_gather = 0;
SET work_mem = '32MB';

-- TODO:
-- Выполните ANALYZE для партиционированной таблицы/таблиц
-- Пример:
ANALYZE orders_partitioned;

-- ============================================
-- TODO:
-- Скопируйте сюда те же запросы, что в:
--   02_explain_before.sql
--   04_explain_after_indexes.sql
-- и выполните EXPLAIN (ANALYZE, BUFFERS) после партиционирования.
-- ============================================

-- TODO: EXPLAIN (ANALYZE, BUFFERS)
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT user_id FROM (
  SELECT user_id, created_at
  FROM orders_partitioned
  WHERE total_amount > 500
  ORDER BY created_at DESC
  LIMIT 10000
) t;

-- TODO: EXPLAIN (ANALYZE, BUFFERS)
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders_partitioned
WHERE status = 'paid'
  AND created_at >= timestamp '2025-01-01'
  AND created_at < timestamp '2025-04-01';

-- TODO: EXPLAIN (ANALYZE, BUFFERS)
EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(oi.price * oi.quantity) AS total_revenue, o.status
FROM orders_partitioned o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.created_at >= timestamp '2025-01-01'
  AND o.created_at < timestamp '2025-04-01'
  AND oi.price < 100
GROUP BY status
ORDER BY total_revenue DESC
LIMIT 2;

-- (Опционально) Q4
-- TODO
