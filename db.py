# -*- coding: utf-8 -*-
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL과 SUPABASE_KEY 환경변수가 설정되지 않았습니다")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def init_db():
    """앱 시작 시 기본 매장 데이터 확인 (테이블은 setup_db.sql로 미리 생성)"""
    client = get_client()
    result = client.table('stores').select('id').execute()
    if not result.data:
        default_stores = [
            {'name': '강남점',      'pin': '0000'},
            {'name': '홍대점',      'pin': '0000'},
            {'name': '판교아지트점', 'pin': '0000'},
            {'name': '용산점',      'pin': '0000'},
            {'name': '영등포점',    'pin': '0000'},
            {'name': '롯데월드몰점', 'pin': '0000'},
            {'name': '전주한옥마을', 'pin': '0000'},
        ]
        client.table('stores').insert(default_stores).execute()
    print("Supabase 연결 완료:", SUPABASE_URL)


if __name__ == "__main__":
    init_db()
