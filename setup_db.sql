-- Supabase SQL Editor에서 한 번만 실행하세요
-- Dashboard → SQL Editor → New Query → 붙여넣기 → Run

-- 매장 테이블
CREATE TABLE IF NOT EXISTS stores (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT UNIQUE NOT NULL,
    pin        TEXT DEFAULT '0000',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 상품 테이블
CREATE TABLE IF NOT EXISTS products (
    id          BIGSERIAL PRIMARY KEY,
    cha_su      INTEGER NOT NULL,
    seq         INTEGER NOT NULL,
    name        TEXT NOT NULL,
    code        TEXT UNIQUE NOT NULL,
    stock_total INTEGER DEFAULT 0,
    stock_avail INTEGER DEFAULT 0,
    pop_name    TEXT,
    image_path  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 배치 레이아웃 테이블
CREATE TABLE IF NOT EXISTS layouts (
    id         BIGSERIAL PRIMARY KEY,
    store_id   BIGINT NOT NULL REFERENCES stores(id),
    cha_su     INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES products(id),
    pos_x      REAL DEFAULT 0,
    pos_y      REAL DEFAULT 0,
    width      REAL DEFAULT 120,
    height     REAL DEFAULT 120,
    z_index    INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(store_id, cha_su, product_id)
);

-- 발주 그룹 테이블
CREATE TABLE IF NOT EXISTS order_groups (
    id         BIGSERIAL PRIMARY KEY,
    store_id   BIGINT NOT NULL REFERENCES stores(id),
    cha_su     INTEGER NOT NULL,
    file_name  TEXT,
    status     TEXT DEFAULT 'pending',
    note       TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 발주 상세 테이블
CREATE TABLE IF NOT EXISTS order_items (
    id             BIGSERIAL PRIMARY KEY,
    order_group_id BIGINT NOT NULL REFERENCES order_groups(id),
    product_id     BIGINT REFERENCES products(id),
    product_code   TEXT,
    product_name   TEXT,
    qty            INTEGER DEFAULT 0,
    note           TEXT
);

-- 매장별 재고 테이블
CREATE TABLE IF NOT EXISTS store_stock (
    id         BIGSERIAL PRIMARY KEY,
    store_id   BIGINT NOT NULL REFERENCES stores(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    qty_in     INTEGER DEFAULT 0,
    qty_out    INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(store_id, product_id)
);

-- 기본 매장 데이터
INSERT INTO stores (name, pin) VALUES
    ('강남점',      '0000'),
    ('홍대점',      '0000'),
    ('판교아지트점', '0000'),
    ('용산점',      '0000'),
    ('영등포점',    '0000'),
    ('롯데월드몰점', '0000'),
    ('전주한옥마을', '0000')
ON CONFLICT (name) DO NOTHING;
