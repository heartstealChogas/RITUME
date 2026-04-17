import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY environment variables are not set")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    client = get_client()
    result = client.table('branches').select('id').execute()
    if len(result.data) == 0:
        default_branches = [
            {'id': 'b_gangnam', 'name': '강남점',      'path_po': '', 'path_inv': ''},
            {'id': 'b_hongdae', 'name': '홍대점',      'path_po': '', 'path_inv': ''},
            {'id': 'b_pangyo',  'name': '판교아지트점', 'path_po': '', 'path_inv': ''},
            {'id': 'b_yongsan', 'name': '용산점',      'path_po': '', 'path_inv': ''},
            {'id': 'b_yeongdp', 'name': '영등포점',    'path_po': '', 'path_inv': ''},
            {'id': 'b_lotte',   'name': '롯데월드몰점', 'path_po': '', 'path_inv': ''},
            {'id': 'b_jeonju',  'name': '전주한옥마을', 'path_po': '', 'path_inv': ''},
        ]
        client.table('branches').insert(default_branches).execute()
    print("Database initialized (Supabase REST API)")

if __name__ == "__main__":
    init_db()
