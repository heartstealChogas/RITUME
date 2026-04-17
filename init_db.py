import sqlite3
from pathlib import Path

import os
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "database.sqlite"

def init_db():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Comparisons table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    
    # Branches table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS branches (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            path_po TEXT,
            path_inv TEXT
        )
    ''')
    
    # Insert default branches if empty
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
        cur.executemany("INSERT INTO branches (id, name, path_po, path_inv) VALUES (?, ?, ?, ?)", default_branches)
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
