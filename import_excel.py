# -*- coding: utf-8 -*-
"""총정리.xlsx → SQLite DB 임포트"""
import sys
import os
import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

from db import init_db, get_conn, DB_PATH

BASE_DIR = os.path.dirname(__file__)
EXCEL_PATH = os.path.join(BASE_DIR, "총정리.xlsx")
IMG_DIR = os.path.join(BASE_DIR, "static", "images")


def extract_images(ws):
    """엑셀 이미지를 row → 파일경로 맵으로 반환"""
    os.makedirs(IMG_DIR, exist_ok=True)
    image_map = {}
    for img in ws._images:
        try:
            row = img.anchor._from.row  # 0-based (header=0, data=1~)
            data = img._data()
            fmt = "png" if data[:4] == b"\x89PNG" else "jpg"
            fname = f"product_{row}.{fmt}"
            fpath = os.path.join(IMG_DIR, fname)
            with open(fpath, "wb") as f:
                f.write(data)
            image_map[row] = f"static/images/{fname}"
        except Exception as e:
            print(f"  이미지 추출 오류 row={row}: {e}")
    return image_map


def import_products():
    init_db()
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["총정리"]

    print("이미지 추출 중...")
    image_map = extract_images(ws)
    print(f"  {len(image_map)}개 추출 완료")

    rows = list(ws.iter_rows(values_only=True))
    # header: 이미지, 차수, 순번, 제품약어, 제품코드, 총재고수량, 가용재고수량, POP명

    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM products")

    inserted = 0
    for i, row in enumerate(rows[1:], start=1):  # i=1 corresponds to excel row 1
        _, cha_su, seq, name, code, stock_total, stock_avail, pop_name = row
        if not code:
            continue
        img_path = image_map.get(i)  # row i in 0-based = data row i
        c.execute("""
            INSERT INTO products (cha_su, seq, name, code, stock_total, stock_avail, pop_name, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (cha_su, seq, name, str(code), stock_total or 0, stock_avail or 0, pop_name, img_path))
        inserted += 1

    conn.commit()
    conn.close()
    print(f"상품 {inserted}개 DB 저장 완료 → {DB_PATH}")

    # 기본 매장 샘플 추가
    conn = get_conn()
    c = conn.cursor()
    sample_stores = ["본점", "강남점", "홍대점", "신촌점", "이태원점"]
    for s in sample_stores:
        c.execute("INSERT OR IGNORE INTO stores (name) VALUES (?)", (s,))
    conn.commit()
    conn.close()
    print(f"샘플 매장 {len(sample_stores)}개 추가 완료")


if __name__ == "__main__":
    import_products()
