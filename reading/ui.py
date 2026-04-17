import os
import datetime
from pathlib import Path

import openpyxl
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QAbstractItemView, QFileDialog,
    QMessageBox, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer

from utils.config import BASE_DIR
from songjang.parser import parse_purchase_order
from songjang.scanner import InvoiceScanner, OUT_HEADERS

class InvoiceTab(QWidget):
    """
    Gacha Invoice (가차 송장) Tab.
    Reads purchase order Excel ("발주서"), exports it in the "송장양식.xlsx" format,
    and supports background automatic scanning.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parsed_rows: list[dict] = []
        
        # Initialize Scanner component
        songjang_dir = BASE_DIR / "songjang"
        data_dir = BASE_DIR / "data"
        self.scanner = InvoiceScanner(songjang_dir, data_dir)
        
        # Background Watcher
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(10000) # Check every 10 seconds
        self.auto_timer.timeout.connect(self._run_auto_scan_silent)
        
        self._build_ui()
        self.auto_timer.start()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        lbl = QLabel("발주서(Excel) 모드:")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold;")

        self.btn_import = QPushButton("단일 발주서 열기")
        self.btn_import.setMinimumWidth(120)
        self.btn_import.setStyleSheet(
            "QPushButton { background: #1a73e8; color: #fff; font-weight: bold;"
            " border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #1558b0; }"
            "QPushButton:pressed { background: #0d47a1; }"
        )
        self.btn_import.clicked.connect(self._on_import_clicked)

        self.btn_export = QPushButton("송장 내보내기 (수동)")
        self.btn_export.setMinimumWidth(140)
        self.btn_export.setStyleSheet(
            "QPushButton { background: #34a853; color: #fff; font-weight: bold;"
            " border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #2d8e47; }"
            "QPushButton:pressed { background: #256e38; }"
        )
        self.btn_export.clicked.connect(self._on_export_clicked)

        # Scanner controls
        self.btn_scan = QPushButton("폴더 전체 강제스캔")
        self.btn_scan.setMinimumWidth(140)
        self.btn_scan.setStyleSheet(
            "QPushButton { background: #f29900; color: #fff; font-weight: bold;"
            " border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #e68a00; }"
            "QPushButton:pressed { background: #cc7a00; }"
        )
        self.btn_scan.setToolTip("songjang 폴더 내 모든 새로운 파일을 자동 변환합니다.")
        self.btn_scan.clicked.connect(self._on_scan_clicked)

        toolbar.addWidget(lbl)
        toolbar.addWidget(self.btn_import)
        toolbar.addWidget(self.btn_export)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_scan)
        layout.addLayout(toolbar)

        # ── Drag and drop area + Table ───────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(len(OUT_HEADERS))
        self.table.setHorizontalHeaderLabels(OUT_HEADERS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        self.table.setAcceptDrops(True)
        self.table.dragEnterEvent = self._drag_enter_event
        self.table.dropEvent = self._drop_event

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSortIndicatorShown(True)
        layout.addWidget(self.table)

        # ── Status label ─────────────────────────────────────────────────────
        self.status_lbl = QLabel("발주서 엑셀 파일을 창안에 드래그하거나 '단일 발주서 열기'를 누르세요. 백그라운드 자동 변환도 실행 중입니다.")
        self.status_lbl.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.status_lbl)

    # ── Drag & Drop ──────────────────────────────────────────────────────────
    def _drag_enter_event(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().endswith((".xlsx", ".xls")):
                event.accept()
                return
        event.ignore()

    def _drop_event(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.endswith((".xlsx", ".xls")):
                self._load_purchase_order(Path(path))

    # ── Event Handlers ───────────────────────────────────────────────────────
    def _on_scan_clicked(self):
        """Manually trigger the folder scan process."""
        self.status_lbl.setText("폴더 전체를 스캔하는 중...")
        processed, errors = self.scanner.scan_and_process_all()
        
        msg = f"새로 스캔하여 처리한 발주서: {processed}건"
        if errors > 0:
            msg += f"\n오류 발생: {errors}건"
            
        QMessageBox.information(self, "스캔 완료", msg)
        self.status_lbl.setText(msg)

    def _run_auto_scan_silent(self):
        """Silently scan in the background."""
        processed, errors = self.scanner.scan_and_process_all()
        if processed > 0:
            self.status_lbl.setText(f"새로운 파일 {processed}건 자동 변환 완료 "
                                    f"({datetime.datetime.now().strftime('%H:%M:%S')})")

    def _on_import_clicked(self):
        last_dir = str(self.scanner.songjang_dir)
        path, _ = QFileDialog.getOpenFileName(
            self, "단일 발주서 가져오기", last_dir, "Excel 파일 (*.xlsx *.xls)"
        )
        if path:
            self._load_purchase_order(Path(path))

    def _load_purchase_order(self, path: Path):
        self.status_lbl.setText("수동 발주서 분석 중...")
        try:
            # We call the external parser tool
            self._parsed_rows = parse_purchase_order(path)
            self._refresh_table()
            
            QMessageBox.information(
                self, "발주서 가져오기 성공", 
                f"총 {len(self._parsed_rows)}개의 제품 정보를 추출했습니다.\n내보내기를 진행해주세요."
            )
            
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.status_lbl.setText(f"파일 불러오기 실패: {exc}")
            QMessageBox.critical(self, "오류", f"발주서를 분석하는 중 오류가 발생했습니다:\n{exc}")

    def _refresh_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._parsed_rows))
        
        for r_idx, row_data in enumerate(self._parsed_rows):
            for c_idx, key in enumerate(OUT_HEADERS):
                val = row_data.get(key, "")
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r_idx, c_idx, item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.status_lbl.setText(f"발주서 데이터 로드 완료 ({len(self._parsed_rows)}건)")

    def _on_export_clicked(self):
        if not self._parsed_rows:
            QMessageBox.information(self, "내보내기", "내보낼 데이터가 없습니다. 먼저 발주서를 가져와주세요.")
            return
            
        today = datetime.datetime.now().strftime("%Y%m%d")
        default_save_name = f"송장임시_가차_{today}.xlsx"
        
        path, _ = QFileDialog.getSaveFileName(
            self, "임시 송장 내보내기", default_save_name, "Excel 파일 (*.xlsx)"
        )
        if not path:
            return
            
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'Sheet1'
            
            ws.append(OUT_HEADERS)
            for r_idx in range(self.table.rowCount()):
                row_vals = []
                for c_idx in range(self.table.columnCount()):
                    it = self.table.item(r_idx, c_idx)
                    row_vals.append(it.text() if it else "")
                ws.append(row_vals)
                
            wb.save(path)
            QMessageBox.information(self, "내보내기 완료", f"저장 완료:\n{path}")
            
        except Exception as exc:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "내보내기 실패", f"파일을 저장하는 중 오류가 발생했습니다:\n{exc}")
