# -*- coding: utf-8 -*-
"""가차 발주 관리 시스템 - FastAPI 서버"""
import os
import io
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import openpyxl

from songjang.parser import parse_purchase_order, OUT_HEADERS

from db import init_db, get_conn

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static", "images"), exist_ok=True)

init_db()

app = FastAPI(title="가차 발주 시스템")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


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
    conn = get_conn()
    if cha_su:
        rows = conn.execute(
            "SELECT * FROM products WHERE cha_su=? ORDER BY seq", (cha_su,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM products ORDER BY cha_su, seq").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/products/cha-su-list")
async def get_cha_su_list():
    conn = get_conn()
    rows = conn.execute(
        "SELECT cha_su, COUNT(*) as cnt FROM products GROUP BY cha_su ORDER BY cha_su"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# 매장 API
# ─────────────────────────────────────────────
@app.get("/api/stores")
async def get_stores():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM stores ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/stores")
async def create_store(data: dict):
    name = data.get("name", "").strip()
    pin = data.get("pin", "0000")
    if not name:
        raise HTTPException(400, "매장명을 입력하세요")
    conn = get_conn()
    try:
        conn.execute("INSERT INTO stores (name, pin) VALUES (?, ?)", (name, pin))
        conn.commit()
    except Exception:
        raise HTTPException(400, "이미 존재하는 매장명입니다")
    finally:
        conn.close()
    return {"ok": True}


# ─────────────────────────────────────────────
# 배치 레이아웃 API
# ─────────────────────────────────────────────
@app.get("/api/stores/{store_id}/layouts")
async def get_store_layouts(store_id: int):
    """매장의 모든 저장된 차수 목록 + 상품 수"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT cha_su, COUNT(*) as item_cnt,
               MAX(updated_at) as last_saved
        FROM layouts
        WHERE store_id=?
        GROUP BY cha_su
        ORDER BY cha_su
    """, (store_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/layout/{store_id}/{cha_su}")
async def get_layout(store_id: int, cha_su: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT l.*, p.name, p.code, p.image_path, p.seq
        FROM layouts l
        JOIN products p ON l.product_id = p.id
        WHERE l.store_id=? AND l.cha_su=?
    """, (store_id, cha_su)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/layout/{store_id}/{cha_su}")
async def save_layout(store_id: int, cha_su: int, data: dict):
    """배치 저장: {"items": [{"product_id":1,"pos_x":10,"pos_y":20,"width":120,"height":120,"z_index":0}]}"""
    items = data.get("items", [])
    conn = get_conn()
    for item in items:
        conn.execute("""
            INSERT INTO layouts (store_id, cha_su, product_id, pos_x, pos_y, width, height, z_index, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(store_id, cha_su, product_id)
            DO UPDATE SET pos_x=excluded.pos_x, pos_y=excluded.pos_y,
                          width=excluded.width, height=excluded.height,
                          z_index=excluded.z_index, updated_at=CURRENT_TIMESTAMP
        """, (store_id, cha_su, item["product_id"],
              item.get("pos_x", 0), item.get("pos_y", 0),
              item.get("width", 120), item.get("height", 120),
              item.get("z_index", 0)))
    conn.commit()
    conn.close()
    return {"ok": True, "saved": len(items)}


@app.delete("/api/layout/{store_id}/{cha_su}")
async def reset_layout(store_id: int, cha_su: int):
    conn = get_conn()
    conn.execute("DELETE FROM layouts WHERE store_id=? AND cha_su=?", (store_id, cha_su))
    conn.commit()
    conn.close()
    return {"ok": True}


# ─────────────────────────────────────────────
# 발주 API
# ─────────────────────────────────────────────
@app.get("/api/orders")
async def get_orders(store_id: Optional[int] = None, cha_su: Optional[int] = None):
    conn = get_conn()
    sql = """
        SELECT og.*, s.name as store_name,
               (SELECT SUM(oi.qty) FROM order_items oi WHERE oi.order_group_id=og.id) as total_qty
        FROM order_groups og
        JOIN stores s ON og.store_id = s.id
        WHERE 1=1
    """
    params = []
    if store_id:
        sql += " AND og.store_id=?"
        params.append(store_id)
    if cha_su:
        sql += " AND og.cha_su=?"
        params.append(cha_su)
    sql += " ORDER BY og.created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/orders/{order_id}/items")
async def get_order_items(order_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT oi.*, p.image_path
        FROM order_items oi
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE oi.order_group_id=?
    """, (order_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/orders/upload")
async def upload_order(
    file: UploadFile = File(...),
    store_id: int = Form(...),
    cha_su: int = Form(...),
    note: str = Form("")
):
    """발주서 업로드 → DB 저장 + 송장 엑셀 반환 (한 번에 처리)"""
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

    # DB 저장
    conn = get_conn()
    conn.execute("""
        INSERT INTO order_groups (store_id, cha_su, file_name, status, note)
        VALUES (?, ?, ?, 'pending', ?)
    """, (store_id, cha_su, file.filename, note))
    group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    inserted = 0
    for r in invoice_rows:
        code  = r.get("바코드 (CD_ITEM)_1", "")
        qty   = r.get("주문수량 (QT_GIR)", 0)
        pname = r.get("상품명 (NM_ITEM)_1", "")
        if not code or qty <= 0:
            continue
        product = conn.execute(
            "SELECT id, name FROM products WHERE code=?", (code,)
        ).fetchone()
        pid   = product["id"]   if product else None
        pname = pname or (product["name"] if product else code)
        conn.execute("""
            INSERT INTO order_items (order_group_id, product_id, product_code, product_name, qty)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, pid, code, pname, qty))
        inserted += 1

    conn.commit()
    conn.close()

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
            "X-Items-Count": str(inserted),
            "Access-Control-Expose-Headers": "X-Order-Id, X-Items-Count",
        },
    )


@app.patch("/api/orders/{order_id}/status")
async def update_order_status(order_id: int, data: dict):
    status = data.get("status")
    if status not in ("pending", "processing", "done", "cancelled"):
        raise HTTPException(400, "잘못된 상태값")
    conn = get_conn()

    order = conn.execute(
        "SELECT store_id, status FROM order_groups WHERE id=?", (order_id,)
    ).fetchone()
    if not order:
        raise HTTPException(404, "발주를 찾을 수 없습니다")

    prev_status = order["status"]
    store_id = order["store_id"]

    conn.execute("UPDATE order_groups SET status=? WHERE id=?", (status, order_id))

    # 완료 처리 시 매장 재고에 발주 수량 반영
    if status == "done" and prev_status != "done":
        items = conn.execute(
            "SELECT product_id, qty FROM order_items WHERE order_group_id=?", (order_id,)
        ).fetchall()
        for item in items:
            if not item["product_id"]:
                continue
            conn.execute("""
                INSERT INTO store_stock (store_id, product_id, qty_in, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(store_id, product_id)
                DO UPDATE SET qty_in = qty_in + excluded.qty_in,
                              updated_at = CURRENT_TIMESTAMP
            """, (store_id, item["product_id"], item["qty"]))

    # 완료 취소(done → 다른 상태) 시 재고 롤백
    if prev_status == "done" and status != "done":
        items = conn.execute(
            "SELECT product_id, qty FROM order_items WHERE order_group_id=?", (order_id,)
        ).fetchall()
        for item in items:
            if not item["product_id"]:
                continue
            conn.execute("""
                UPDATE store_stock
                SET qty_in = MAX(0, qty_in - ?), updated_at = CURRENT_TIMESTAMP
                WHERE store_id=? AND product_id=?
            """, (item["qty"], store_id, item["product_id"]))

    conn.commit()
    conn.close()
    return {"ok": True}


# ─────────────────────────────────────────────
# 재고 현황 API
# ─────────────────────────────────────────────
@app.get("/api/stock/{store_id}")
async def get_store_stock(store_id: int, cha_su: Optional[int] = None):
    """매장별 상품 재고 현황 (입고 - 출고 = 잔여)"""
    conn = get_conn()
    sql = """
        SELECT p.id as product_id, p.name, p.code, p.cha_su, p.image_path,
               COALESCE(ss.qty_in, 0)  as qty_in,
               COALESCE(ss.qty_out, 0) as qty_out,
               COALESCE(ss.qty_in, 0) - COALESCE(ss.qty_out, 0) as qty_remaining,
               ss.updated_at
        FROM products p
        LEFT JOIN store_stock ss ON ss.product_id = p.id AND ss.store_id = ?
        WHERE 1=1
    """
    params = [store_id]
    if cha_su:
        sql += " AND p.cha_su = ?"
        params.append(cha_su)
    sql += " ORDER BY p.cha_su, p.seq"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stock/summary/all")
async def get_stock_summary_all():
    """전체 매장 재고 요약 (매장별 총 잔여 수량)"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.id as store_id, s.name as store_name,
               COUNT(DISTINCT ss.product_id) as product_count,
               COALESCE(SUM(ss.qty_in - ss.qty_out), 0) as total_remaining
        FROM stores s
        LEFT JOIN store_stock ss ON ss.store_id = s.id
        GROUP BY s.id
        ORDER BY s.id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
