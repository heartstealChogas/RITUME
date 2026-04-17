import os
import secrets
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import openpyxl

from logic import parse_purchase_order, parse_invoice, build_comparison
from init_db import get_client

app = FastAPI(title="RIE ERP Server")

@app.on_event("startup")
def startup_event():
    from init_db import init_db
    init_db()

# ── Auth ──────────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "7777")
SESSION_TOKEN  = secrets.token_hex(32)

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
    client = get_client()
    result = client.table('branches').select('*').execute()
    return result.data

# 3. API: History
@app.get("/api/history")
async def get_history(branch_name: Optional[str] = None, _: None = Depends(require_auth)):
    client = get_client()
    query = client.table('comparisons').select('*').order('id', desc=True)
    if branch_name and branch_name != "all":
        query = query.eq('branch_name', branch_name)
    else:
        query = query.limit(5000)
    result = query.execute()
    return result.data

# 4. API: Compare and Save
@app.post("/api/compare")
async def api_compare(
    branch_id: str = Form(...),
    po_file: UploadFile = File(...),
    inv_file: UploadFile = File(...),
    _: None = Depends(require_auth)
):
    client = get_client()

    branch_result = client.table('branches').select('name').eq('id', branch_id).execute()
    if not branch_result.data:
        raise HTTPException(status_code=404, detail="Branch not found")

    branch_name = branch_result.data[0]['name']

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

        client.table('comparisons').delete() \
            .eq('branch_name', branch_name).eq('file_date', file_date).execute()

        if results:
            rows = [
                {
                    'branch_name': branch_name,
                    'file_date':   file_date,
                    'status':      res['status'],
                    'seq':         res['seq'],
                    'name':        res['name'],
                    'barcode':     res['barcode'],
                    'po_qty':      res['po_qty'],
                    'inv_no':      res['inv_no'],
                    'inv_qty':     res['inv_qty'],
                    'qty_diff':    res['qty_diff'],
                }
                for res in results
            ]
            client.table('comparisons').insert(rows).execute()

        # Update JSON cache for static frontend
        all_result = client.table('comparisons').select('*').execute()
        json_out_path = BASE_DIR / "web" / "comparisons_data.json"
        try:
            with open(json_out_path, 'w', encoding='utf-8') as f:
                json.dump(all_result.data, f, ensure_ascii=False)
        except OSError:
            pass

        return {"status": "success", "count": len(results), "data": results}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
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
