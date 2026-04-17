import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    url = DATABASE_URL
    if "sslmode" not in url:
        url += "?sslmode=require"
    return psycopg2.connect(url)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS comparisons (
            id SERIAL PRIMARY KEY,
            branch_name TEXT,
            file_date TEXT,
            status TEXT,
            seq TEXT,
            name TEXT,
            barcode TEXT,
            po_qty INTEGER,
            inv_no TEXT,
            inv_qty INTEGER,
            qty_diff INTEGER
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS branches (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path_po TEXT,
            path_inv TEXT
        )
    ''')

    cur.execute("SELECT COUNT(*) FROM branches")
    if cur.fetchone()[0] == 0:
        default_branches = [
            ('b_gangnam', '강남점', '', ''),
            ('b_hongdae', '홍대점', '', ''),
            ('b_pangyo', '판교아지트점', '', ''),
            ('b_yongsan', '용산점', '', ''),
            ('b_yeongdp', '영등포점', '', ''),
            ('b_lotte', '롯데월드몰점', '', ''),
            ('b_jeonju', '전주한옥마을', '', ''),
        ]
        cur.executemany(
            "INSERT INTO branches (id, name, path_po, path_inv) VALUES (%s, %s, %s, %s)",
            default_branches
        )

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialized (Supabase PostgreSQL)")

if __name__ == "__main__":
    init_db()
