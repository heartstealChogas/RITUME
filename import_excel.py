# -*- coding: utf-8 -*-
"""
가창.xlsx 총정리 시트 → Supabase products 테이블 임포트
컬럼 순서: 이미지(A), 차수(B), 순번(C), 제품코드(D), 제품약어(E), 가격(F), POP번(G)
"""
import sys
import os
import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

from db import get_client

BASE_DIR = os.path.dirname(__file__)
EXCEL_PATH = os.path.join(BASE_DIR, "가창.xlsx")
IMG_DIR = os.path.join(BASE_DIR, "static", "images")


def extract_images(ws):
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
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb["총정리"]

    print("이미지 추출 중...")
    image_map = extract_images(ws)
    print(f"  {len(image_map)}개 추출 완료")

    rows = list(ws.iter_rows(values_only=True))
    # rows[0] = 헤더: 이미지, 차수, 순번, 제품코드, 제품약어, 가격, POP번, ...

    client = get_client()

    # 기존 상품 삭제
    client.table('products').delete().neq('id', 0).execute()
    print("기존 상품 삭제 완료")

    inserted = 0
    batch = []
    for i, row in enumerate(rows[1:], start=1):  # i=1 → excel row 1 (0-based)
        if not row or len(row) < 6:
            continue
        _, cha_su, seq, code, name, price = row[0], row[1], row[2], row[3], row[4], row[5]
        pop_name = row[6] if len(row) > 6 else None

        if not code:
            continue

        img_path = image_map.get(i)
        batch.append({
            'cha_su':     int(cha_su) if cha_su else None,
            'seq':        int(seq)    if seq    else None,
            'code':       str(code),
            'name':       str(name)   if name   else '',
            'price':      int(price)  if price  else None,
            'pop_name':   str(pop_name) if pop_name else None,
            'image_path': img_path,
        })
        inserted += 1

        # Supabase 배치 업서트 (100개 단위)
        if len(batch) >= 100:
            client.table('products').insert(batch).execute()
            print(f"  {inserted}개 저장 중...")
            batch = []

    if batch:
        client.table('products').insert(batch).execute()

    print(f"상품 {inserted}개 Supabase 저장 완료")


if __name__ == "__main__":
    import_products()
