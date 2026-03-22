\timing on
\echo '=== APPLY INDEXES ==='

-- ============================================
-- TODO: Создайте индексы на основе ваших EXPLAIN ANALYZE
-- ============================================

-- Индекс 1
-- TODO:
-- CREATE INDEX ... ON ... USING BTREE (...);
CREATE INDEX IF NOT EXISTS idx_orders_amt_gt_500_created_at_desc
  ON orders (created_at DESC)
  INCLUDE (user_id)
  WHERE total_amount > 500;
-- Обоснование:
-- - какой запрос ускоряет
-- - почему выбран именно этот тип индекса

-- Индекс 2
-- TODO:
-- CREATE INDEX ... ON ... USING ... (...);
CREATE INDEX IF NOT EXISTS idx_orders_status_created_at_desc
  ON orders (status, created_at DESC);
-- Обоснование:
-- - какой запрос ускоряет
-- - почему выбран именно этот тип индекса

-- Индекс 3
-- TODO:
-- CREATE INDEX ... ON ... USING ... (...);
CREATE INDEX IF NOT EXISTS idx_order_items_price_gt_100_orderid_include
  ON order_items (order_id)
  INCLUDE (price, quantity)
  WHERE price < 100;
-- Обоснование:
-- - какой запрос ускоряет
-- - почему выбран именно этот тип индекса

-- (Опционально) Частичный индекс / BRIN / составной индекс
-- TODO

-- Не забудьте обновить статистику после создания индексов
-- TODO:
ANALYZE orders;
ANALYZE order_items;
