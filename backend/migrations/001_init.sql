-- ============================================
-- Схема базы данных маркетплейса
-- ============================================

-- Включаем расширение UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- TODO: Создать таблицу order_statuses
-- Столбцы: status (PK), description

CREATE TABLE IF NOT EXISTS order_statuses (
    status TEXT PRIMARY KEY,
    description TEXT
);


-- TODO: Вставить значения статусов
-- created, paid, cancelled, shipped, completed

INSERT INTO order_statuses (status, description)
VALUES
  ('created',   'Создан, ожидает оплаты'),
  ('paid',      'Оплачен'),
  ('cancelled', 'Отменён'),
  ('shipped',   'Отправлен'),
  ('completed', 'Завершён')
ON CONFLICT (status) DO NOTHING;


-- TODO: Создать таблицу users
-- Столбцы: id (UUID PK), email, name, created_at
-- Ограничения:
--   - email UNIQUE
--   - email NOT NULL и не пустой
--   - email валидный (regex через CHECK)

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_email_not_empty CHECK (char_length(trim(email)) > 0),
    CONSTRAINT users_email_valid CHECK (
        email ~ '^[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9-]{1,}$'
    )
);


-- TODO: Создать таблицу orders
-- Столбцы: id (UUID PK), user_id (FK), status (FK), total_amount, created_at
-- Ограничения:
--   - user_id -> users(id)
--   - status -> order_statuses(status)
--   - total_amount >= 0

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    total_amount NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_orders_status FOREIGN KEY (status) REFERENCES order_statuses(status)
);


-- TODO: Создать таблицу order_items
-- Столбцы: id (UUID PK), order_id (FK), product_name, price, quantity
-- Ограничения:
--   - order_id -> orders(id) CASCADE
--   - price >= 0
--   - quantity > 0
--   - product_name не пустой

CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT order_items_product_name_not_empty CHECK (char_length(trim(product_name)) > 0)
);


-- TODO: Создать таблицу order_status_history
-- Столбцы: id (UUID PK), order_id (FK), status (FK), changed_at
-- Ограничения:
--   - order_id -> orders(id) CASCADE
--   - status -> order_statuses(status)

CREATE TABLE IF NOT EXISTS order_status_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL,
    status TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_history_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT fk_history_status FOREIGN KEY (status) REFERENCES order_statuses(status)
);


-- ============================================
-- КРИТИЧЕСКИЙ ИНВАРИАНТ: Нельзя оплатить заказ дважды
-- ============================================
-- TODO: Создать функцию триггера check_order_not_already_paid()
-- При изменении статуса на 'paid' проверить что его нет в истории
-- Если есть - RAISE EXCEPTION

CREATE OR REPLACE FUNCTION check_order_not_already_paid()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    IF (NEW.status = 'paid') AND (OLD.status IS DISTINCT FROM 'paid') THEN
        SELECT EXISTS (
            SELECT 1 FROM order_status_history
            WHERE order_id = NEW.id
                AND status = 'paid'
            LIMIT 1
        ) INTO v_exists;

        IF v_exists THEN
            RAISE EXCEPTION 'Order % has already been paid (history contains paid)', NEW.id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;


-- TODO: Создать триггер trigger_check_order_not_already_paid
-- BEFORE UPDATE ON orders FOR EACH ROW

DROP TRIGGER IF EXISTS trigger_check_order_not_already_paid ON orders;
CREATE TRIGGER trigger_check_order_not_already_paid
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE PROCEDURE check_order_not_already_paid();


-- ============================================
-- БОНУС (опционально)
-- ============================================
-- TODO: Триггер автоматического пересчета total_amount

-- CREATE OR REPLACE FUNCTION update_order_total_on_item_change()
-- RETURNS TRIGGER
-- LANGUAGE plpgsql
-- AS $$
-- DECLARE
--     target_order UUID;
--     new_total NUMERIC(12,2);
-- BEGIN
--     IF TG_OP = 'INSERT' THEN
--         target_order := NEW.order_id;
--     ELSIF TG_OP = 'UPDATE' THEN
--         target_order := NEW.order_id;
--         IF OLD.order_id IS DISTINCT FROM NEW.order_id THEN
--             UPDATE orders
--             SET total_amount = COALESCE((
--                 SELECT SUM(price * quantity)::NUMERIC(12,2) FROM order_items WHERE order_id = OLD.order_id
--             ), 0)
--             WHERE id = OLD.order_id;
--         END IF;
--     ELSIF TG_OP = 'DELETE' THEN
--         target_order := OLD.order_id;
--     END IF;

--     UPDATE orders
--     SET total_amount = COALESCE((
--         SELECT SUM(price * quantity)::NUMERIC(12,2) FROM order_items WHERE order_id = target_order
--     ), 0)
--     WHERE id = target_order;

--     RETURN NULL;
-- END;
-- $$;

-- DROP TRIGGER IF EXISTS trigger_update_order_total_on_item_change ON order_items;
-- CREATE TRIGGER trigger_update_order_total_on_item_change
-- AFTER INSERT OR UPDATE OR DELETE ON order_items
-- FOR EACH ROW
-- EXECUTE PROCEDURE update_order_total_on_item_change();


-- TODO: Триггер автоматической записи в историю при изменении статуса

-- CREATE OR REPLACE FUNCTION insert_order_status_history_on_change()
-- RETURNS TRIGGER
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     IF NEW.status IS DISTINCT FROM OLD.status THEN
--         INSERT INTO order_status_history (order_id, status, changed_at)
--         VALUES (NEW.id, NEW.status, now());
--     END IF;

--     RETURN NEW;
-- END;
-- $$;

-- DROP TRIGGER IF EXISTS trigger_insert_order_status_history_on_change ON orders;
-- CREATE TRIGGER trigger_insert_order_status_history_on_change
-- AFTER UPDATE ON orders
-- FOR EACH ROW
-- EXECUTE PROCEDURE insert_order_status_history_on_change();


-- TODO: Триггер записи начального статуса при создании заказа

-- CREATE OR REPLACE FUNCTION insert_initial_order_status_on_create()
-- RETURNS TRIGGER
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     INSERT INTO order_status_history (order_id, status, changed_at)
--     VALUES (NEW.id, NEW.status, now());
--     RETURN NEW;
-- END;
-- $$;

-- DROP TRIGGER IF EXISTS trigger_insert_initial_order_status_on_create ON orders;
-- CREATE TRIGGER trigger_insert_initial_order_status_on_create
-- AFTER INSERT ON orders
-- FOR EACH ROW
-- EXECUTE PROCEDURE insert_initial_order_status_on_create();
