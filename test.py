import sys, os
sys.path.append('.')
from process_compare import main
import process_compare

def debug():
    po_dir = process_compare.DATA_DIR / "발주서"
    inv_dir = process_compare.DATA_DIR / "송장"
    
    po_files = list(po_dir.rglob("*.xlsx"))
    for pf in po_files:
        if pf.name.startswith("~$"): continue
        branch_name = pf.parent.name
        
        inv_branch_dir = inv_dir / branch_name
        for inv_f in inv_branch_dir.rglob("*.xlsx"):
            if not inv_f.name.startswith("~$"):
                print("Testing:", pf.name, inv_f.name)
                
                po_data = process_compare.parse_purchase_order(pf)
                inv_data = process_compare.parse_invoice(inv_f)
                
                print("Sample PO:")
                for i in range(min(2, len(po_data))):
                    print(po_data[i])
                    
                print("Sample INV:")
                for i in range(min(2, len(inv_data))):
                    print(inv_data[i])
                
                comp = process_compare.build_comparison(po_data, inv_data)
                print("Missed comparisons:")
                missed = [c for c in comp if c['status'] == 'miss']
                for i in range(min(5, len(missed))):
                    print(missed[i])
                return

if __name__ == '__main__':
    debug()
