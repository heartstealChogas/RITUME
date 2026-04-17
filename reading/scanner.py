import os
import json
import re
from pathlib import Path
import openpyxl

from songjang.parser import parse_purchase_order

PROCESSED_FILE_DB = 'processed_invoices.json'

OUT_HEADERS = [
    '순번', '거래처코드', '출하의뢰번호 (NO_GIR)', '출하의뢰항번 (SEQ_GIR)', 
    '납품처코드', '상품명(사이트)', '사이트명', '상품명 (NM_ITEM)_1', 
    '바코드 (CD_ITEM)_1', '상품명 (NM_ITEM)_2', '바코드 (CD_ITEM)_2', 
    '상품명 (NM_ITEM)_3', '바코드 (CD_ITEM)_3', '주문수량 (QT_GIR)', 
    '주문자명 (NM_CUST)', '주문자 연락처1 (NO_TEL_D1)', '주문자 연락처2 (NO_TEL_D2)', 
    '수취인명 (NM_CUST_DLV)', '수취인연락처1 (NO_TEL_D1)', '수취인연락처2 (NO_TEL_D2)', 
    '수취인우편번호 CD_ZIP', '배송주소', '수취인주소2 (ADDR2)', '배송메시지 (DC_REQ)', 
    '송장번호 (CD_INVOICE)', '택배사명 (CD_DELI)', '주문번호', '반품사유'
]

class InvoiceScanner:
    def __init__(self, songjang_dir: Path, data_dir: Path):
        self.songjang_dir = songjang_dir
        self.output_dir = self.songjang_dir / "송장출력"
        self.output_dir.mkdir(exist_ok=True)
        self.db_path = data_dir / PROCESSED_FILE_DB
        self.processed = self._load_db()

    def _load_db(self) -> dict:
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_db(self):
        self.db_path.parent.mkdir(exist_ok=True)
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.processed, f, ensure_ascii=False, indent=2)

    def scan_and_process_all(self):
        """Scans all *.xlsx files in the songjang directory and processes new ones."""
        all_files = list(self.songjang_dir.rglob('*.xlsx'))
        
        # Exclude temporary files and output directory
        target_files = [
            f for f in all_files 
            if not f.name.startswith('~$') 
            and f.name != '송장양식.xlsx' 
            and '송장출력' not in f.parts
        ]

        processed_count = 0
        error_count = 0
        
        for f in target_files:
            file_id = str(f.relative_to(self.songjang_dir))
            
            # Use size + mtime as a basic fingerprint to reprocess if file changes
            stat = f.stat()
            fingerprint = f"{stat.st_size}_{stat.st_mtime}"
            
            if self.processed.get(file_id) == fingerprint:
                continue # Already processed
                
            # Process new or changed file
            try:
                rows = parse_purchase_order(f)
                if rows:
                    self._generate_export(f, rows)
                
                # Mark successfully processed
                self.processed[file_id] = fingerprint
                processed_count += 1
                
            except Exception as e:
                print(f"Error processing {f.name}: {e}")
                error_count += 1
                
        if processed_count > 0:
            self._save_db()
            
        return processed_count, error_count

    def _generate_export(self, source_path: Path, rows: list[dict]):
        branch_name = '기타'
        if source_path.parent != self.songjang_dir:
            branch_name = source_path.parent.name
            
        date_match = re.search(r'20\d{6}', source_path.name)
        date_str = date_match.group(0) if date_match else 'UnknownDate'
        
        branch_dir = self.output_dir / branch_name
        branch_dir.mkdir(exist_ok=True)
        
        out_name = f'{branch_name}_송장_{date_str}.xlsx'
        out_path = branch_dir / out_name
        
        counter = 1
        while out_path.exists():
            # If the exact path exists, we assume we might be overwriting or incrementing.
            # To be safe and unique per file, we append counter
            out_name = f'{branch_name}_송장_{date_str}_{counter}.xlsx'
            out_path = branch_dir / out_name
            counter += 1
            
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Sheet1'
        
        ws.append(OUT_HEADERS)
        for r in rows:
            row_vals = [r.get(hdr, '') for hdr in OUT_HEADERS]
            ws.append(row_vals)
            
        wb.save(str(out_path))
