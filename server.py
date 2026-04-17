import os
import secrets
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import openpyxl
from psycopg2.extras import RealDictCursor

from logic import parse_purchase_order, parse_invoice, build_comparison
from init_db import get_connection

app = FastAPI(title="RIE ERP Server")

@app.on_event("startup")
def startup_event():
    from init_db import init_db
    init_db()

# ── Auth ──────────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "7777")
SESSION_TOKEN  = secrets.token_hex(32)   # fresh token each server start

class LoginRequest(BaseModel):
    password: str

def require_auth(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if authorization[7:] != SESSION_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.post("/api/login")
async def login(req: LoginRequest):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    return {"token": SESSION_TOKEN}

# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent

# 2. API: Branch List
@app.get("/api/branches")
async def get_branches(_: None = Depends(require_auth)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM branches")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

# 3. API: History
@app.get("/api/history")
async def get_history(branch_name: Optional[str] = None, _: None = Depends(require_auth)):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if branch_name and branch_name != "all":
        cur.execute(
            "SELECT * FROM comparisons WHERE branch_name = %s ORDER BY id DESC",
            (branch_name,)
        )
    else:
        cur.execute("SELECT * FROM comparisons ORDER BY id DESC LIMIT 5000")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

# 4. API: Compare and Save
@app.post("/api/compare")
async def api_compare(
    branch_id: str = Form(...),
    po_file: UploadFile = File(...),
    inv_file: UploadFile = File(...),
    _: None = Depends(require_auth)
):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT name FROM branches WHERE id = %s", (branch_id,))
    branch = cur.fetchone()
    if not branch:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Branch not found")

    branch_name = branch["name"]

    # Extract date from PO filename (e.g., 20251001)
    date_match = re.search(r'20\d{6}', po_file.filename)
    file_date = date_match.group(0) if date_match else "00000000"

    po_path = None
    inv_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".xlsx") as po_tmp:
            po_tmp.write(await po_file.read())
            po_path = Path(po_tmp.name)

        with NamedTemporaryFile(delete=False, suffix=".xlsx") as inv_tmp:
            inv_tmp.write(await inv_file.read())
            inv_path = Path(inv_tmp.name)

        po_data = parse_purchase_order(po_path)

        inv_wb = openpyxl.load_workbook(inv_path, data_only=True)
        inv_data = parse_invoice(inv_wb.active)

        results = build_comparison(po_data, inv_data)

        cur.execute(
            "DELETE FROM comparisons WHERE branch_name = %s AND file_date = %s",
            (branch_name, file_date)
        )

        for res in results:
            cur.execute('''
                INSERT INTO comparisons
                (branch_name, file_date, status, seq, name, barcode, po_qty, inv_no, inv_qty, qty_diff)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                branch_name, file_date, res['status'], res['seq'], res['name'],
                res['barcode'], res['po_qty'], res['inv_no'], res['inv_qty'], res['qty_diff']
            ))
        conn.commit()

        # Update JSON file for static frontend compatibility
        cur.execute("SELECT * FROM comparisons")
        all_rows = cur.fetchall()
        json_out_path = BASE_DIR / "web" / "comparisons_data.json"
        try:
            with open(json_out_path, 'w', encoding='utf-8') as f:
                json.dump([dict(r) for r in all_rows], f, ensure_ascii=False)
        except OSError:
            pass  # non-critical; skip if filesystem is read-only

        return {"status": "success", "count": len(results), "data": results}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
        if po_path and po_path.exists():
            os.unlink(po_path)
        if inv_path and inv_path.exists():
            os.unlink(inv_path)

# 5. Serve Static Files (at the end to not override API routes)
WEB_DIR = BASE_DIR / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
