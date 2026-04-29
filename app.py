# -*- coding: utf-8 -*-
"""가차 발주 관리 시스템 - FastAPI 서버 (Supabase)"""
import os
import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict, Counter
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import openpyxl
from dotenv import load_dotenv

load_dotenv()

from songjang.parser import parse_purchase_order, OUT_HEADERS
from db import get_client, init_db

BASE_DIR = os.path.dirname(__file__)
os.makedirs(os.path.join(BASE_DIR, "static", "images"), exist_ok=True)

init_db()

app = FastAPI(title="가차 발주 시스템")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────
# 메인 페이지
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────
# 상품 API
# ─────────────────────────────────────────────
@app.get("/api/products")
async def get_products(cha_su: Optional[int] = None):
    client = get_client()
    query = client.table('products').select('*')
    if cha_su:
        query = query.eq('cha_su', cha_su)
    result = query.order('cha_su').order('seq').execute()
    return result.data


@app.get("/api/products/cha-su-list")
async def get_cha_su_list():
    client = get_client()
    result = client.table('products').select('cha_su').execute()
    counts = Counter(r['cha_su'] for r in result.data)
    return [{'cha_su': k, 'cnt': v} for k, v in sorted(counts.items())]


# ─────────────────────────────────────────────
# 매장 API
# ─────────────────────────────────────────────
@app.get("/api/stores")
async def get_stores():
    client = get_client()
    result = client.table('stores').select('*').order('id').execute()
    return result.data


@app.post("/api/stores")
async def create_store(data: dict):
    name = data.get("name", "").strip()
    pin = data.get("pin", "0000")
    if not name:
        raise HTTPException(400, "매장명을 입력하세요")
    client = get_client()
    try:
        client.table('stores').insert({'name': name, 'pin': pin}).execute()
    except Exception:
        raise HTTPException(400, "이미 존재하는 매장명입니다")
    return {"ok": True}


# ─────────────────────────────────────────────
# 배치 레이아웃 API
# ─────────────────────────────────────────────
@app.get("/api/stores/{store_id}/layouts")
async def get_store_layouts(store_id: int):
    client = get_client()
    result = client.table('layouts').select('cha_su, updated_at').eq('store_id', store_id).execute()
    groups = defaultdict(lambda: {'item_cnt': 0, 'last_saved': ''})
    for r in result.data:
        g = groups[r['cha_su']]
        g['item_cnt'] += 1
        if (r.get('updated_at') or '') > g['last_saved']:
            g['last_saved'] = r['updated_at']
    return [{'cha_su': k, **v} for k, v in sorted(groups.items())]


@app.get("/api/layout/{store_id}/{cha_su}")
async def get_layout(store_id: int, cha_su: int):
    client = get_client()
    result = client.table('layouts').select(
        '*, products(name, code, image_path, seq)'
    ).eq('store_id', store_id).eq('cha_su', cha_su).execute()
    rows = []
    for r in result.data:
        product = r.pop('products', {}) or {}
        r.update(product)
        rows.append(r)
    return rows


@app.post("/api/layout/{store_id}/{cha_su}")
async def save_layout(store_id: int, cha_su: int, data: dict):
    items = data.get("items", [])
    client = get_client()
    for item in items:
        client.table('layouts').upsert({
            'store_id':   store_id,
            'cha_su':     cha_su,
            'product_id': item['product_id'],
            'pos_x':      item.get('pos_x', 0),
            'pos_y':      item.get('pos_y', 0),
            'width':      item.get('width', 120),
            'height':     item.get('height', 120),
            'z_index':    item.get('z_index', 0),
            'updated_at': now_iso(),
        }, on_conflict='store_id,cha_su,product_id').execute()
    return {"ok": True, "saved": len(items)}


@app.delete("/api/layout/{store_id}/{cha_su}")
async def reset_layout(store_id: int, cha_su: int):
    client = get_client()
    client.table('layouts').delete().eq('store_id', store_id).eq('cha_su', cha_su).execute()
    return {"ok": True}


# ─────────────────────────────────────────────
# 발주 API
# ─────────────────────────────────────────────
@app.get("/api/orders")
async def get_orders(store_id: Optional[int] = None, cha_su: Optional[int] = None):
    client = get_client()
    query = client.table('order_groups').select('*, stores(name), order_items(qty)')
    if store_id:
        query = query.eq('store_id', store_id)
    if cha_su:
        query = query.eq('cha_su', cha_su)
    result = query.order('created_at', desc=True).execute()
    rows = []
    for r in result.data:
        store = r.pop('stores', {}) or {}
        order_items = r.pop('order_items', []) or []
        r['store_name'] = store.get('name', '')
        r['total_qty'] = sum(i.get('qty', 0) for i in order_items)
        rows.append(r)
    return rows


@app.get("/api/orders/{order_id}/items")
async def get_order_items(order_id: int):
    client = get_client()
    result = client.table('order_items').select(
        '*, products(image_path)'
    ).eq('order_group_id', order_id).execute()
    rows = []
    for r in result.data:
        product = r.pop('products', {}) or {}
        r['image_path'] = product.get('image_path')
        rows.append(r)
    return rows


@app.post("/api/orders/upload")
async def upload_order(
    file: UploadFile = File(...),
    store_id: int = Form(...),
    cha_su: int = Form(...),
    note: str = Form("")
):
    content = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        invoice_rows = parse_purchase_order(tmp_path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"파일 파싱 오류: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    if not invoice_rows:
        raise HTTPException(400, "파싱된 상품이 없습니다. 파일 형식을 확인하세요.")

    client = get_client()

    group_result = client.table('order_groups').insert({
        'store_id': store_id, 'cha_su': cha_su,
        'file_name': file.filename, 'status': 'pending', 'note': note
    }).execute()
    group_id = group_result.data[0]['id']

    codes = [r.get("바코드 (CD_ITEM)_1", "") for r in invoice_rows if r.get("바코드 (CD_ITEM)_1")]
    if codes:
        products_result = client.table('products').select('id, name, code').in_('code', codes).execute()
        product_map = {p['code']: p for p in products_result.data}
    else:
        product_map = {}

    items_to_insert = []
    for r in invoice_rows:
        code  = r.get("바코드 (CD_ITEM)_1", "")
        qty   = r.get("주문수량 (QT_GIR)", 0)
        pname = r.get("상품명 (NM_ITEM)_1", "")
        if not code or qty <= 0:
            continue
        product = product_map.get(code)
        pid   = product['id']   if product else None
        pname = pname or (product['name'] if product else code)
        items_to_insert.append({
            'order_group_id': group_id,
            'product_id':     pid,
            'product_code':   code,
            'product_name':   pname,
            'qty':            qty,
        })

    if items_to_insert:
        client.table('order_items').insert(items_to_insert).execute()

    # 송장 엑셀 생성
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(OUT_HEADERS)
    for r in invoice_rows:
        ws.append([r.get(h, "") for h in OUT_HEADERS])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    stem = Path(file.filename).stem
    out_name = f"{stem}_송장.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{out_name}",
            "X-Order-Id": str(group_id),
            "X-Items-Count": str(len(items_to_insert)),
            "Access-Control-Expose-Headers": "X-Order-Id, X-Items-Count",
        },
    )


@app.patch("/api/orders/{order_id}/status")
async def update_order_status(order_id: int, data: dict):
    status = data.get("status")
    if status not in ("pending", "processing", "done", "cancelled"):
        raise HTTPException(400, "잘못된 상태값")

    client = get_client()
    order_result = client.table('order_groups').select('store_id, status').eq('id', order_id).execute()
    if not order_result.data:
        raise HTTPException(404, "발주를 찾을 수 없습니다")

    order = order_result.data[0]
    prev_status = order['status']
    store_id = order['store_id']

    client.table('order_groups').update({'status': status}).eq('id', order_id).execute()

    if status == "done" and prev_status != "done":
        items = client.table('order_items').select('product_id, qty').eq('order_group_id', order_id).execute().data
        for item in items:
            if not item['product_id']:
                continue
            stock = client.table('store_stock').select('qty_in').eq('store_id', store_id).eq('product_id', item['product_id']).execute()
            if stock.data:
                new_qty = stock.data[0]['qty_in'] + item['qty']
                client.table('store_stock').update({
                    'qty_in': new_qty, 'updated_at': now_iso()
                }).eq('store_id', store_id).eq('product_id', item['product_id']).execute()
            else:
                client.table('store_stock').insert({
                    'store_id': store_id, 'product_id': item['product_id'],
                    'qty_in': item['qty'], 'qty_out': 0
                }).execute()

    if prev_status == "done" and status != "done":
        items = client.table('order_items').select('product_id, qty').eq('order_group_id', order_id).execute().data
        for item in items:
            if not item['product_id']:
                continue
            stock = client.table('store_stock').select('qty_in').eq('store_id', store_id).eq('product_id', item['product_id']).execute()
            if stock.data:
                new_qty = max(0, stock.data[0]['qty_in'] - item['qty'])
                client.table('store_stock').update({
                    'qty_in': new_qty, 'updated_at': now_iso()
                }).eq('store_id', store_id).eq('product_id', item['product_id']).execute()

    return {"ok": True}


# ─────────────────────────────────────────────
# 재고 현황 API
# ─────────────────────────────────────────────
@app.get("/api/stock/{store_id}")
async def get_store_stock(store_id: int, cha_su: Optional[int] = None):
    client = get_client()
    query = client.table('products').select('id, name, code, cha_su, image_path')
    if cha_su:
        query = query.eq('cha_su', cha_su)
    products = query.order('cha_su').order('seq').execute().data

    stock_result = client.table('store_stock').select(
        'product_id, qty_in, qty_out, updated_at'
    ).eq('store_id', store_id).execute()
    stock_map = {s['product_id']: s for s in stock_result.data}

    rows = []
    for p in products:
        s = stock_map.get(p['id'], {})
        qty_in  = s.get('qty_in', 0)
        qty_out = s.get('qty_out', 0)
        rows.append({
            'product_id':    p['id'],
            'name':          p['name'],
            'code':          p['code'],
            'cha_su':        p['cha_su'],
            'image_path':    p['image_path'],
            'qty_in':        qty_in,
            'qty_out':       qty_out,
            'qty_remaining': qty_in - qty_out,
            'updated_at':    s.get('updated_at'),
        })
    return rows


@app.get("/api/stock/summary/all")
async def get_stock_summary_all():
    client = get_client()
    stores = client.table('stores').select('id, name').order('id').execute().data
    stock_all = client.table('store_stock').select('store_id, qty_in, qty_out').execute().data

    stock_by_store = defaultdict(list)
    for s in stock_all:
        stock_by_store[s['store_id']].append(s)

    rows = []
    for store in stores:
        stocks = stock_by_store[store['id']]
        rows.append({
            'store_id':        store['id'],
            'store_name':      store['name'],
            'product_count':   len(stocks),
            'total_remaining': sum(s['qty_in'] - s['qty_out'] for s in stocks),
        })
    return rows


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
