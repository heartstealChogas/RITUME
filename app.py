# -*- coding: utf-8 -*-
"""가차 상품 목록 시스템 - FastAPI 서버 (Supabase)"""
import os
from collections import Counter
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from db import get_client, init_db

BASE_DIR = os.path.dirname(__file__)
os.makedirs(os.path.join(BASE_DIR, "static", "images"), exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
    except Exception as e:
        print(f"[startup] DB 초기화 경고: {e}")
    yield


app = FastAPI(title="가차 상품 목록", lifespan=lifespan)
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
