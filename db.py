# -*- coding: utf-8 -*-
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "gacha.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # 상품 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cha_su      INTEGER NOT NULL,
            seq         INTEGER NOT NULL,
            name        TEXT    NOT NULL,
            code        TEXT    UNIQUE NOT NULL,
            stock_total INTEGER DEFAULT 0,
            stock_avail INTEGER DEFAULT 0,
            pop_name    TEXT,
            image_path  TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 매장 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            pin        TEXT DEFAULT '0000',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 배치 레이아웃 테이블 (매장별 × 차수별 드래그앤드롭 위치)
    c.execute("""
        CREATE TABLE IF NOT EXISTS layouts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id   INTEGER NOT NULL REFERENCES stores(id),
            cha_su     INTEGER NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            pos_x      REAL DEFAULT 0,
            pos_y      REAL DEFAULT 0,
            width      REAL DEFAULT 120,
            height     REAL DEFAULT 120,
            z_index    INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(store_id, cha_su, product_id)
        )
    """)

    # 발주 그룹 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS order_groups (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id   INTEGER NOT NULL REFERENCES stores(id),
            cha_su     INTEGER NOT NULL,
            file_name  TEXT,
            status     TEXT DEFAULT 'pending',
            note       TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 발주 상세 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            order_group_id INTEGER NOT NULL REFERENCES order_groups(id),
            product_id     INTEGER REFERENCES products(id),
            product_code   TEXT,
            product_name   TEXT,
            qty            INTEGER DEFAULT 0,
            note           TEXT
        )
    """)

    # 매장별 상품 재고 테이블
    c.execute("""
        CREATE TABLE IF NOT EXISTS store_stock (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id   INTEGER NOT NULL REFERENCES stores(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            qty_in     INTEGER DEFAULT 0,
            qty_out    INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(store_id, product_id)
        )
    """)

    # 기본 매장 데이터 (없을 때만 삽입)
    default_stores = [
        ('강남점',      '0000'),
        ('홍대점',      '0000'),
        ('판교아지트점', '0000'),
        ('용산점',      '0000'),
        ('영등포점',    '0000'),
        ('롯데월드몰점', '0000'),
        ('전주한옥마을', '0000'),
    ]
    for name, pin in default_stores:
        c.execute(
            "INSERT OR IGNORE INTO stores (name, pin) VALUES (?, ?)",
            (name, pin)
        )

    conn.commit()
    conn.close()
    print("DB 초기화 완료:", DB_PATH)


if __name__ == "__main__":
    init_db()
