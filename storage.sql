-- Пользователи
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(50) UNIQUE NOT NULL,
    role VARCHAR(10) NOT NULL CHECK (role IN ('USER', 'ADMIN')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Торговые инструменты
CREATE TABLE instruments (
    ticker VARCHAR(10) PRIMARY KEY CHECK (ticker ~ '^[A-Z]{2,10}$'),
    name VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Балансы пользователей
CREATE TABLE balances (
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ticker VARCHAR(10) NOT NULL REFERENCES instruments(ticker) ON DELETE RESTRICT,
    amount BIGINT NOT NULL CHECK (amount >= 0),
    PRIMARY KEY (user_id, ticker)
);

-- Ордера
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ticker VARCHAR(10) NOT NULL REFERENCES instruments(ticker) ON DELETE RESTRICT,
    direction CHAR(4) NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    order_type VARCHAR(6) NOT NULL CHECK (order_type IN ('LIMIT', 'MARKET')),
    price BIGINT CHECK (
        (order_type = 'LIMIT' AND price IS NOT NULL AND price > 0) OR
        (order_type = 'MARKET' AND price IS NULL)
    ),
    qty BIGINT NOT NULL CHECK (qty >= 1),
    filled_qty BIGINT NOT NULL DEFAULT 0 CHECK (filled_qty <= qty),
    status VARCHAR(20) NOT NULL CHECK (
        status IN ('NEW', 'PARTIALLY_EXECUTED', 'EXECUTED', 'CANCELLED', 'SYSTEM_CANCELLED')
    ),
    currency VARCHAR(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Сделки
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buy_order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
    sell_order_id UUID REFERENCES orders(id) ON DELETE SET NULL,
    ticker VARCHAR(10) NOT NULL REFERENCES instruments(ticker) ON DELETE RESTRICT,
    price BIGINT NOT NULL CHECK (price > 0),
    qty BIGINT NOT NULL CHECK (qty > 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Стакан заявок
CREATE TABLE orderbook (
    ticker VARCHAR(10) NOT NULL REFERENCES instruments(ticker) ON DELETE CASCADE,
    price BIGINT NOT NULL CHECK (price > 0),
    qty BIGINT NOT NULL CHECK (qty > 0),
    side CHAR(1) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    currency VARCHAR(3) NOT NULL DEFAULT 'RUB' CHECK (currency ~ '^[A-Z]{3}$'),
    PRIMARY KEY (ticker, price, side, currency)
);

-- Индексы для оптимизации производительности
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_ticker ON orders(ticker);
CREATE INDEX idx_transactions_ticker_created ON transactions(ticker, created_at);
CREATE INDEX idx_transactions_buy_order ON transactions(buy_order_id);
CREATE INDEX idx_transactions_sell_order ON transactions(sell_order_id);
CREATE INDEX idx_orderbook_ticker_side_price ON orderbook(ticker, side, price);
CREATE INDEX idx_balances_user_id ON balances(user_id);
CREATE INDEX idx_balances_ticker ON balances(ticker);