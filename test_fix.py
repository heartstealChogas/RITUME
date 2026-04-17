import sys
from pathlib import Path

sys.path.insert(0, r'c:\Users\admin\Desktop\rie')
from process_compare import parse_invoice, build_comparison
from reading.parser import parse_purchase_order

inv_dir = Path(r'c:\Users\admin\Desktop\rie\data\송장')
po_dir  = Path(r'c:\Users\admin\Desktop\rie\data\발주서')

# --- Test invoice parsing ---
inv_files = [f for f in inv_dir.rglob('*.xlsx') if not f.name.startswith('~$')]
po_files  = [f for f in po_dir.rglob('*.xlsx')  if not f.name.startswith('~$')]

if inv_files:
    inv_f = inv_files[0]
    print(f'=== INVOICE: {inv_f.name} ===')
    rows = parse_invoice(inv_f)
    print(f'  Parsed {len(rows)} rows')
    for r in rows[:5]:
        print(f'  invNo={r["invNo"]!r}  barcode={r["barcode"]}  qty={r["qty"]}  name={r["name"]}')
else:
    print('No invoice files found!')

print()

if po_files:
    po_f = po_files[0]
    print(f'=== PO: {po_f.name} ===')
    rows = parse_purchase_order(po_f)
    print(f'  Parsed {len(rows)} rows')
    for r in rows[:5]:
        nm = r.get('상품명 (NM_ITEM)_1', '')
        bc = r.get('바코드 (CD_ITEM)_1', '')
        qt = r.get('주문수량 (QT_GIR)', 0)
        print(f'  name={nm}  barcode={bc}  qty={qt}')
else:
    print('No PO files found!')

# --- Test a matched pair ---
print()
print('=== COMPARISON TEST ===')
# Find a PO and its matching invoice by date
import re
for po_f in po_files:
    branch = po_f.parent.name
    date_m = re.search(r'20\d{6}', po_f.name)
    if not date_m:
        continue
    date = date_m.group(0)
    matched = None
    for inv_f in inv_files:
        if inv_f.parent.name == branch and date in inv_f.name:
            matched = inv_f
            break
    if matched:
        print(f'Branch: {branch}  Date: {date}')
        po_data  = parse_purchase_order(po_f)
        inv_data = parse_invoice(matched)
        results  = build_comparison(po_data, inv_data)
        ok   = [r for r in results if r['status'] == 'ok']
        miss = [r for r in results if r['status'] == 'miss']
        extra= [r for r in results if r['status'] == 'extra']
        print(f'  OK: {len(ok)}  MISS: {len(miss)}  EXTRA: {len(extra)}')
        for r in results[:5]:
            print(f"  [{r['status']:5}] {r['barcode']:15}  po={r['po_qty']}  inv={r['inv_qty']}  diff={r['qty_diff']}  invNo={r['inv_no']!r}")
        break
