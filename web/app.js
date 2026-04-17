/**
 * RIE ERP — 발주·송장 대조 시스템 app.js v1.0
 *
 * 주요 기능:
 *  - 지점별 발주서 + 송장 Excel 업로드
 *  - 상품명/바코드 기준으로 발주-송장 일치 여부 대조
 *  - 일치/불일치/송장만 존재 3가지 상태 표시
 *  - 결과 필터링, 검색, CSV 내보내기
 *  - 지점별 경로 메모 저장 (localStorage)
 */

'use strict';

// ────────────────────────────────────────────────────────────────────────────
// AUTH
// ────────────────────────────────────────────────────────────────────────────
const TOKEN_KEY = 'rie_session_token';

function getToken()        { return localStorage.getItem(TOKEN_KEY); }
function setToken(t)       { localStorage.setItem(TOKEN_KEY, t); }
function clearToken()      { localStorage.removeItem(TOKEN_KEY); }

// Authenticated fetch — attaches Bearer token; on 401 clears token & shows login
async function authFetch(url, options = {}) {
  const token = getToken();
  const headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    showLoginOverlay();
    throw new Error('인증이 필요합니다. 다시 로그인해주세요.');
  }
  return res;
}

function showLoginOverlay() {
  const overlay = document.getElementById('loginOverlay');
  if (overlay) overlay.classList.remove('hidden');
}

function hideLoginOverlay() {
  const overlay = document.getElementById('loginOverlay');
  if (overlay) overlay.classList.add('hidden');
}

// Login form logic (runs immediately so the overlay is wired up before init)
(function setupLogin() {
  const pwInput   = document.getElementById('loginPwInput');
  const loginBtn  = document.getElementById('loginBtn');
  const errorDiv  = document.getElementById('loginError');

  async function attemptLogin() {
    const pw = pwInput.value.trim();
    errorDiv.style.display = 'none';
    loginBtn.disabled = true;
    pwInput.disabled  = true;
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pw }),
      });
      if (!res.ok) {
        errorDiv.style.display = '';
        pwInput.value = '';
        pwInput.focus();
        return;
      }
      const data = await res.json();
      setToken(data.token);
      hideLoginOverlay();
      init();  // initialise the app after login
    } catch {
      errorDiv.style.display = '';
    } finally {
      loginBtn.disabled = false;
      pwInput.disabled  = false;
    }
  }

  loginBtn.addEventListener('click', attemptLogin);
  pwInput.addEventListener('keydown', e => { if (e.key === 'Enter') attemptLogin(); });
})();

// ────────────────────────────────────────────────────────────────────────────
// BRANCH STORE
// ────────────────────────────────────────────────────────────────────────────
const BRANCH_KEY = 'rie_branches_v3';

const DEFAULT_BRANCHES = [
  { id: 'b_gangnam',  name: '강남점',      pathPO: '', pathINV: '' },
  { id: 'b_hongdae',  name: '홍대점',      pathPO: '', pathINV: '' },
  { id: 'b_pangyo',   name: '판교아지트점', pathPO: '', pathINV: '' },
  { id: 'b_yongsan',  name: '용산점',       pathPO: '', pathINV: '' },
  { id: 'b_yeongdp',  name: '영등포점',     pathPO: '', pathINV: '' },
  { id: 'b_lotte',    name: '롯데월드몰점', pathPO: '', pathINV: '' },
  { id: 'b_jeonju',   name: '전주한옥마을', pathPO: '', pathINV: '' },
];

async function loadBranches() {
  try {
    const res = await authFetch('/api/branches');
    if (!res.ok) throw new Error();
    const data = await res.json();
    return data;
  } catch {
    return JSON.parse(JSON.stringify(DEFAULT_BRANCHES)); 
  }
}

let branches = [];
let currentBranchId = null;

// ────────────────────────────────────────────────────────────────────────────
// STATE
// ────────────────────────────────────────────────────────────────────────────
let poRows       = [];   // parsed purchase-order rows
let invRows      = [];   // parsed invoice rows
let compResult   = [];   // comparison result rows
let poPreviewRows= [];   // rows shown in PO preview panel
let filterMode   = 'all';// all | ok | miss | extra
let poFile       = null;
let invFile      = null;
let poMeta       = { orderDate: '', contactPerson: '', contactTel: '', supplierAddress: '' };

// FileSystemDirectoryHandle per branch (in-memory, not persisted)
const dirHandles = {};

// ────────────────────────────────────────────────────────────────────────────
// DOM REFS
// ────────────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const sidebar        = $('sidebar');
const sidebarToggle  = $('sidebarToggle');
const branchList     = $('branchList');
const addBranchBtn   = $('addBranchBtn');
const bcCurrent      = $('bcCurrent');

// Hero
const heroIcon    = $('heroIcon');
const heroName    = $('heroName');
const heroPathPO  = $('heroPathPO');
const heroPathINV = $('heroPathINV');
const editPathBtn = $('editPathBtn');

// Uploads
const dropPO      = $('dropPO');
const poInput     = $('poInput');
const selectPOBtn = $('selectPOBtn');
const poFileName  = $('poFileName');

const dropINV          = $('dropINV');
const invInput         = $('invInput');
const invFileName      = $('invFileName');
const saveInvFromPOBtn = $('saveInvFromPOBtn');

// Compare
const compareBar   = $('compareBar');
const compareBtn   = $('compareBtn');
const clearFilesBtn= $('clearFilesBtn');
const compareResult= $('compareResult');
const emptyCompare = $('emptyCompare');
const compareBody  = $('compareBody');
const compareSearch= $('compareSearch');
const exportResultBtn = $('exportResultBtn');
const saveToPathBtn   = $('saveToPathBtn');
const matchSummary = $('matchSummary');

// Stats
const statMatched = $('statMatched');
const statMissed  = $('statMissed');
const mtTotal = $('mtTotal');
const mtOk    = $('mtOk');
const mtMiss  = $('mtMiss');
const mtExtra = $('mtExtra');
const mtRate  = $('mtRate');
const rcAll   = $('rcAll');
const rcOk    = $('rcOk');
const rcMiss  = $('rcMiss');
const rcExtra = $('rcExtra');

// Modal
const modalBackdrop    = $('modalBackdrop');
const modalTitle       = $('modalTitle');
const modalBranchName  = $('modalBranchName');
const modalPathPO      = $('modalPathPO');
const modalPathINV     = $('modalPathINV');
const modalClose       = $('modalClose');
const modalCancel      = $('modalCancel');
const modalConfirm     = $('modalConfirm');

// Loading
const loadingOverlay = $('loadingOverlay');
const loadingTitle   = $('loadingTitle');
const loadingDetail  = $('loadingDetail');
const toast          = $('toast');

// Database View
const navDatabase    = $('navDatabase');
const dbBranchFilter = $('dbBranchFilter');
const dbStatusFilter = $('dbStatusFilter');
const dbSearch       = $('dbSearch');
const dbRowCount     = $('dbRowCount');
const dbTableBody    = $('dbTableBody');
let dbData = [];

// ────────────────────────────────────────────────────────────────────────────
// SIDEBAR TOGGLE
// ────────────────────────────────────────────────────────────────────────────
sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));

// ────────────────────────────────────────────────────────────────────────────
// GACHA NAV ACCORDION TOGGLE
// ────────────────────────────────────────────────────────────────────────────
const navGacha = $('navGacha');
const accordionBranches = $('accordionBranches');
if (navGacha && accordionBranches) {
  navGacha.addEventListener('click', () => {
    accordionBranches.classList.toggle('open');
  });
}

// ────────────────────────────────────────────────────────────────────────────
// BRANCH RENDER
// ────────────────────────────────────────────────────────────────────────────
function renderBranches() {
  branchList.innerHTML = '';
  branches.forEach(b => {
    const item = document.createElement('div');
    item.className = 'branch-item';
    const initial = (b.name || '?').charAt(0);
    const isActive = b.id === currentBranchId;
    item.innerHTML = `
      <button class="branch-btn${isActive ? ' branch-active' : ''}" data-bid="${b.id}" id="branchBtn_${b.id}">
        <span class="branch-avatar">${escHtml(initial)}</span>
        <span class="branch-name-text">${escHtml(b.name)}</span>
        <span class="branch-status-dot"></span>
      </button>
    `;
    item.querySelector('.branch-btn').addEventListener('click', () => selectBranch(b.id));
    branchList.appendChild(item);
  });
}

function selectBranch(bid) {
  if (currentBranchId === bid) return;
  currentBranchId = bid;
  const branch = branches.find(b => b.id === bid);
  if (!branch) return;

  // Update nav highlights
  renderBranches();

  // Breadcrumb
  bcCurrent.textContent = branch.name;

  // Hero
  const initial = (branch.name || '?').charAt(0);
  heroIcon.textContent = initial;
  heroName.textContent = branch.name;
  updateHeroPaths(branch);

  // Clear previous files
  resetFiles();

  updateSaveToPathBtn();

  // Switch tab
  showTab('tabBranch');

  showToast(`${branch.name} 선택됨`, 'success');
}

function updateHeroPaths(branch) {
  if (branch.pathPO) {
    heroPathPO.textContent = branch.pathPO;
    heroPathPO.classList.add('set');
  } else {
    heroPathPO.textContent = '경로 미설정';
    heroPathPO.classList.remove('set');
  }
  if (branch.pathINV) {
    heroPathINV.textContent = branch.pathINV;
    heroPathINV.classList.add('set');
  } else {
    heroPathINV.textContent = '경로 미설정';
    heroPathINV.classList.remove('set');
  }
}

function showTab(tabId) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById(tabId);
  if (panel) panel.classList.add('active');
}

// ────────────────────────────────────────────────────────────────────────────
// DATABASE VIEW
// ────────────────────────────────────────────────────────────────────────────
if (navDatabase) {
  navDatabase.addEventListener('click', async () => {
    // UI states
    currentBranchId = null;
    document.querySelectorAll('.branch-btn').forEach(b => b.classList.remove('branch-active'));
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    navDatabase.classList.add('active');

    showTab('tabDatabase');
    bcCurrent.textContent = '데이터베이스 조회';

    try {
      showLoading(true, 'DB 데이터 로딩 중', '서버에서 데이터를 불러옵니다...');
      const res = await authFetch('/api/history');
      if (!res.ok) throw new Error('데이터를 가져오는데 실패했습니다. 서버 상태를 확인해주세요.');
      dbData = await res.json();
      populateDbFilters();
      renderDbTable();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      showLoading(false);
    }
  });

  function populateDbFilters() {
    const branches = [...new Set(dbData.map(r => r.branch_name))].sort();
    const currentVal = dbBranchFilter.value;
    dbBranchFilter.innerHTML = '<option value="all">모든 지점</option>';
    branches.forEach(b => {
      dbBranchFilter.innerHTML += `<option value="${b}">${escHtml(b)}</option>`;
    });
    // Set back to previous if possible
    if (branches.includes(currentVal)) dbBranchFilter.value = currentVal;
  }

  function renderDbTable() {
    const bFilter = dbBranchFilter.value;
    const sFilter = dbStatusFilter.value;
    const qFilter = (dbSearch.value || '').trim().toLowerCase();

    const visible = dbData.filter(r => {
      if (bFilter !== 'all' && r.branch_name !== bFilter) return false;
      if (sFilter !== 'all' && r.status !== sFilter) return false;
      if (qFilter) {
        const hay = (r.name + r.barcode + r.inv_no + r.branch_name).toLowerCase();
        if (!hay.includes(qFilter)) return false;
      }
      return true;
    });

    dbRowCount.textContent = `${visible.length}건`;

    dbTableBody.innerHTML = visible.map(r => {
      const statusBadge = {
        ok:    '<span class="status-badge status-ok">✓ 일치</span>',
        miss:  '<span class="status-badge status-miss">✗ 불일치</span>',
        extra: '<span class="status-badge status-extra">+ 송장만</span>',
      }[r.status];

      const diffHtml = r.qty_diff === 0
        ? '<span class="diff-zero">±0</span>'
        : r.qty_diff > 0
          ? `<span class="diff-pos">+${r.qty_diff}</span>`
          : `<span class="diff-neg">${r.qty_diff}</span>`;

      const barcodeHtml = r.barcode
        ? `<span class="ct-barcode-val">${escHtml(r.barcode)}</span>`
        : '<span class="ct-inv-empty">—</span>';

      const invNoHtml = r.inv_no
        ? `<span class="ct-inv-val">${escHtml(r.inv_no)}</span>`
        : '<span class="ct-inv-empty">송장 없음</span>';

      return `<tr class="row-${r.status}">
        <td style="text-align:center; font-weight:500;">${escHtml(r.branch_name)}</td>
        <td style="text-align:center; color:var(--text3);">${escHtml(r.file_date)}</td>
        <td style="text-align:center">${statusBadge}</td>
        <td style="text-align:left; font-weight:500;" title="${escHtml(r.name)}">${escHtml(r.name)}</td>
        <td>${barcodeHtml}</td>
        <td style="text-align:center; font-weight:700; color:var(--blue)">${r.po_qty}</td>
        <td>${invNoHtml}</td>
        <td style="text-align:center; color:var(--green); font-weight:600">${r.inv_qty}</td>
        <td style="text-align:center">${diffHtml}</td>
      </tr>`;
    }).join('') || `<tr><td colspan="9" style="text-align:center;padding:32px;color:var(--text3)">데이터가 없습니다.</td></tr>`;
  }

  dbBranchFilter.addEventListener('change', renderDbTable);
  dbStatusFilter.addEventListener('change', renderDbTable);
  dbSearch.addEventListener('input', renderDbTable);
}

// ────────────────────────────────────────────────────────────────────────────
// ADD BRANCH MODAL
// ────────────────────────────────────────────────────────────────────────────
let editingBranchId = null;

addBranchBtn.addEventListener('click', () => {
  editingBranchId = null;
  modalTitle.textContent = '새 지점 추가';
  modalBranchName.value = '';
  modalPathPO.value = '';
  modalPathINV.value = '';
  openModal();
});

editPathBtn.addEventListener('click', () => {
  if (!currentBranchId) return;
  const branch = branches.find(b => b.id === currentBranchId);
  if (!branch) return;
  editingBranchId = branch.id;
  modalTitle.textContent = `${branch.name} — 경로 설정`;
  modalBranchName.value = branch.name;
  modalPathPO.value  = branch.pathPO  || '';
  modalPathINV.value = branch.pathINV || '';
  openModal();
});

function openModal()  { modalBackdrop.style.display = 'grid'; setTimeout(() => modalBranchName.focus(), 50); }
function closeModal() { modalBackdrop.style.display = 'none'; }

modalClose.addEventListener('click', closeModal);
modalCancel.addEventListener('click', closeModal);
modalBackdrop.addEventListener('click', e => { if (e.target === modalBackdrop) closeModal(); });

modalConfirm.addEventListener('click', () => {
  const name    = modalBranchName.value.trim();
  const pathPO  = modalPathPO.value.trim();
  const pathINV = modalPathINV.value.trim();

  if (!name) { modalBranchName.focus(); return; }

  if (editingBranchId) {
    // Edit existing
    const branch = branches.find(b => b.id === editingBranchId);
    if (branch) {
      branch.name    = name;
      branch.pathPO  = pathPO;
      branch.pathINV = pathINV;
      saveBranches(branches);
      renderBranches();
      if (editingBranchId === currentBranchId) {
        heroName.textContent = name;
        updateHeroPaths(branch);
        bcCurrent.textContent = name;
      }
      showToast('저장 완료', 'success');
    }
  } else {
    // New branch
    const newB = {
      id:      'b_' + Date.now(),
      name,
      pathPO,
      pathINV,
    };
    branches.push(newB);
    saveBranches(branches);
    renderBranches();
    selectBranch(newB.id);
    showToast(`${name} 추가 완료`, 'success');
  }

  closeModal();
});

[modalBranchName, modalPathPO, modalPathINV].forEach(inp => {
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') modalConfirm.click(); });
});

// ────────────────────────────────────────────────────────────────────────────
// FILE UPLOAD — PO (발주서)
// ────────────────────────────────────────────────────────────────────────────
selectPOBtn.addEventListener('click', e => { e.stopPropagation(); poInput.click(); });
dropPO.addEventListener('click', () => poInput.click());
poInput.addEventListener('change', e => { if (e.target.files[0]) setPOFile(e.target.files[0]); });

dropPO.addEventListener('dragover', e => { e.preventDefault(); dropPO.classList.add('drag-over'); });
dropPO.addEventListener('dragleave', () => dropPO.classList.remove('drag-over'));
dropPO.addEventListener('drop', e => {
  e.preventDefault();
  dropPO.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f && isExcel(f.name)) setPOFile(f);
  else showToast('.xlsx 파일만 지원합니다', 'error');
});

async function setPOFile(file) {
  poFile = file;
  poFileName.textContent = file.name;
  poFileName.classList.add('ready');
  dropPO.classList.add('has-file');
  checkBothReady();

  // Parse PO immediately and show detail preview
  try {
    const wb = await readExcel(file);
    poRows = parsePO(wb);

    // Supplement order date from filename if not found inside the Excel
    if (!poMeta.orderDate) {
      const dm = file.name.match(/20\d{6}/);
      if (dm) poMeta.orderDate = dm[0];
    }

    poPreviewRows = poRows;
    renderPOPreview(poPreviewRows);
    renderPOMeta();
    saveInvFromPOBtn.style.display = '';
    checkBranchMismatch();
  } catch (err) {
    hidePOPreview();
    saveInvFromPOBtn.style.display = 'none';
    console.warn('PO preview failed:', err.message);
  }
}

function renderPOPreview(rows) {
  if (!rows.length) { hidePOPreview(); return; }

  $('poPreviewCount').textContent = `총 ${rows.length}개 품목`;
  $('poPreviewBody').innerHTML = rows.map(r => `
    <tr>
      <td style="text-align:center;color:var(--text3)">${escHtml(String(r.seq))}</td>
      <td style="font-weight:500">${escHtml(r.name)}</td>
      <td>${r.barcode ? `<span class="ct-barcode-val">${escHtml(r.barcode)}</span>` : '<span class="ct-inv-empty">—</span>'}</td>
      <td style="text-align:center;font-weight:700;color:var(--blue)">${r.qty}</td>
    </tr>
  `).join('');

  const section = $('poPreviewSection');
  section.style.display = 'block';
  // Ensure body is expanded
  $('poPreviewBodyWrap').style.display = 'block';
  $('poPreviewToggle').textContent = '접기';
}

function hidePOPreview() {
  $('poPreviewSection').style.display = 'none';
  poPreviewRows = [];
  const mi = $('poMetaInfo');
  if (mi) { mi.style.display = 'none'; mi.innerHTML = ''; }
}

function renderPOMeta() {
  const el = $('poMetaInfo');
  if (!el) return;

  const fields = [
    { label: '발주 날짜',    value: poMeta.orderDate },
    { label: '담당자',       value: poMeta.contactPerson },
    { label: '연락처',       value: poMeta.contactTel },
    { label: '납품처 주소',  value: poMeta.supplierAddress },
  ];

  el.innerHTML = `<div class="po-meta-grid">${
    fields.map(f => `
      <div class="po-meta-item">
        <span class="po-meta-label">${escHtml(f.label)}</span>
        ${f.value
          ? `<span class="po-meta-value">${escHtml(f.value)}</span>`
          : `<span class="po-meta-missing">확인 필요</span>`
        }
      </div>`).join('')
  }</div>`;
  el.style.display = 'block';
}

// ────────────────────────────────────────────────────────────────────────────
// FILE UPLOAD — INV (송장)
// ────────────────────────────────────────────────────────────────────────────
dropINV.addEventListener('click', () => invInput.click());
invInput.addEventListener('change', e => { if (e.target.files[0]) setINVFile(e.target.files[0]); });

dropINV.addEventListener('dragover', e => { e.preventDefault(); dropINV.classList.add('drag-over'); });
dropINV.addEventListener('dragleave', () => dropINV.classList.remove('drag-over'));
dropINV.addEventListener('drop', e => {
  e.preventDefault();
  dropINV.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f && isExcel(f.name)) setINVFile(f);
  else showToast('.xlsx 파일만 지원합니다', 'error');
});

function setINVFile(file) {
  invFile = file;
  invFileName.textContent = file.name;
  invFileName.classList.add('ready');
  dropINV.classList.add('has-file');
  checkBothReady();
  checkBranchMismatch();
}

function checkBothReady() {
  if (poFile && invFile) {
    compareBar.style.display = 'flex';
  }
}

// ── Branch mismatch warning ───────────────────────────────────────────────────
function getBranchKeywords(branchName) {
  const keywords = new Set([branchName]);
  const core = branchName.replace(/몰점$|마을$|점$/, '');
  if (core) keywords.add(core);
  // Also add sub-parts for compound names like '판교아지트'
  const subCore = core.replace(/아지트$|한옥$|월드몰$|월드$/, '');
  if (subCore && subCore !== core) keywords.add(subCore);
  return [...keywords];
}

function checkBranchMismatch() {
  const warning = $('branchMismatchWarning');
  if (!warning) return;
  const branch = branches.find(b => b.id === currentBranchId);
  if (!branch || !poFile) { warning.style.display = 'none'; return; }

  const keywords = getBranchKeywords(branch.name);
  const mismatchSources = [];

  const fileNames = [poFile && poFile.name, invFile && invFile.name].filter(Boolean);
  const allFileNames = fileNames.join(' ');
  if (fileNames.length && !keywords.some(kw => allFileNames.includes(kw))) {
    mismatchSources.push('파일명');
  }
  if (poMeta.supplierAddress && !keywords.some(kw => poMeta.supplierAddress.includes(kw))) {
    mismatchSources.push('납품처 주소');
  }

  if (mismatchSources.length) {
    warning.innerHTML = `⚠️ <strong>지점 불일치 주의:</strong> ${mismatchSources.join(', ')}에 현재 지점(<strong>${branch.name}</strong>) 키워드가 없습니다. 다른 지점 파일일 수 있습니다.`;
    warning.style.display = '';
  } else {
    warning.style.display = 'none';
  }
}

function resetFiles() {
  poFile = null; invFile = null;
  poRows = []; invRows = []; compResult = [];
  poFileName.textContent = '';
  poFileName.classList.remove('ready');
  invFileName.textContent = '';
  invFileName.classList.remove('ready');
  dropPO.classList.remove('has-file', 'drag-over');
  dropINV.classList.remove('has-file', 'drag-over');
  poInput.value = '';
  invInput.value = '';
  compareBar.style.display = 'none';
  compareResult.style.display = 'none';
  matchSummary.style.display = 'none';
  emptyCompare.style.display = 'flex';
  statMatched.textContent = '0';
  statMissed.textContent  = '0';
  filterMode = 'all';
  setActiveFilter('all');
  hidePOPreview();
  saveToPathBtn.style.display = 'none';
  saveInvFromPOBtn.style.display = 'none';
  poMeta = { orderDate: '', contactPerson: '', contactTel: '', supplierAddress: '' };
  // Clear auto-load status text
  const invSub = $('invSubText');
  if (invSub) invSub.textContent = '';
  const warn = $('branchMismatchWarning');
  if (warn) warn.style.display = 'none';
}

clearFilesBtn.addEventListener('click', resetFiles);

// ── PO Preview toggle ──────────────────────────────────────────────────────
$('poPreviewToggle').addEventListener('click', () => {
  const wrap = $('poPreviewBodyWrap');
  const btn  = $('poPreviewToggle');
  if (wrap.style.display === 'none') {
    wrap.style.display = 'block';
    btn.textContent = '접기';
  } else {
    wrap.style.display = 'none';
    btn.textContent = '펼치기';
  }
});

// ── Save invoice from PO ───────────────────────────────────────────────────
saveInvFromPOBtn.addEventListener('click', e => {
  e.stopPropagation();
  if (!poRows.length) { showToast('발주서를 먼저 업로드하세요', 'error'); return; }

  const branch  = branches.find(b => b.id === currentBranchId);
  const bName   = branch ? branch.name : '기타';
  const dateMatch = poFile ? poFile.name.match(/20\d{6}/) : null;
  const dateStr = dateMatch ? dateMatch[0] : new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const fileName = `${bName}_송장_${dateStr}.xlsx`;

  const headers = [
    '순번', '거래처코드', '출하의뢰번호 (NO_GIR)', '출하의뢰항번 (SEQ_GIR)', '납품처코드',
    '상품명(사이트)', '사이트명',
    '상품명 (NM_ITEM)_1', '바코드 (CD_ITEM)_1',
    '상품명 (NM_ITEM)_2', '바코드 (CD_ITEM)_2',
    '상품명 (NM_ITEM)_3', '바코드 (CD_ITEM)_3',
    '주문수량 (QT_GIR)',
    '주문자명 (NM_CUST)', '주문자 연락처1 (NO_TEL_D1)', '주문자 연락처2 (NO_TEL_D2)',
    '수취인명 (NM_CUST_DLV)', '수취인연락처1 (NO_TEL_D1)', '수취인연락처2 (NO_TEL_D2)',
    '수취인우편번호 CD_ZIP', '배송주소', '수취인주소2 (ADDR2)',
    '배송메시지 (DC_REQ)', '송장번호 (CD_INVOICE)', '택배사명 (CD_DELI)',
    '주문번호', '반품사유',
  ];

  const dataRows = poRows.map((r, idx) => [
    idx + 1,                        // 순번
    'C0000010',                     // 거래처코드
    1,                              // 출하의뢰번호 (NO_GIR)
    idx + 1,                        // 출하의뢰항번 (SEQ_GIR)
    'C0000010',                     // 납품처코드
    '', '',                         // 상품명(사이트), 사이트명
    r.name,                         // 상품명 (NM_ITEM)_1
    r.barcode,                      // 바코드 (CD_ITEM)_1
    '', '', '', '',                 // NM_ITEM_2, CD_ITEM_2, NM_ITEM_3, CD_ITEM_3
    r.qty,                          // 주문수량 (QT_GIR)
    poMeta.contactPerson,           // 주문자명
    poMeta.contactTel,              // 주문자 연락처1
    '',                             // 주문자 연락처2
    poMeta.contactPerson,           // 수취인명
    poMeta.contactTel,              // 수취인연락처1
    '',                             // 수취인연락처2
    '',                             // 수취인우편번호
    poMeta.supplierAddress,         // 배송주소
    '', '', '', '', '', '', '',     // 나머지 빈 컬럼
  ]);

  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows]);
  const wb2 = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb2, ws, 'Sheet1');
  XLSX.writeFile(wb2, fileName);
  showToast(`송장 저장 완료: ${fileName}`, 'success');
});

function updateSaveToPathBtn() {
  const hasDir    = !!(currentBranchId && dirHandles[currentBranchId]);
  const hasResult = compResult.length > 0;
  saveToPathBtn.style.display = (hasDir && hasResult) ? '' : 'none';
}

async function tryAutoLoadInvoice(branchId, dateStr) {
  const handle = dirHandles[branchId];
  if (!handle) return;
  try {
    for await (const [name, entry] of handle.entries()) {
      if (
        entry.kind === 'file' &&
        !name.startsWith('~$') &&
        name.includes(dateStr) &&
        isExcel(name)
      ) {
        const file = await entry.getFile();
        setINVFile(file);
        const invSub = $('invSubText');
        if (invSub) invSub.textContent = '자동 로드됨';
        showToast(`송장 자동 로드: ${name}`, 'success');
        return;
      }
    }
    // No match found — user can still upload manually
  } catch (err) {
    console.warn('Auto invoice search failed:', err);
  }
}

// ────────────────────────────────────────────────────────────────────────────
// COMPARE
// ────────────────────────────────────────────────────────────────────────────
compareBtn.addEventListener('click', async () => {
  if (!poFile || !invFile || !currentBranchId) return;
  showLoading(true, '대조 처리 중', '서버에서 비교 중입니다...');
  try {
    const formData = new FormData();
    formData.append('branch_id', currentBranchId);
    formData.append('po_file', poFile);
    formData.append('inv_file', invFile);

    const res = await authFetch('/api/compare', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || '대조 요청 중 오류가 발생했습니다.');
    }

    const resData = await res.json();
    compResult = resData.data;

    renderComparison();
    showToast(`대조 및 DB 저장 완료 — ${compResult.length}건`, 'success');

  } catch (err) {
    showToast(err.message, 'error');
    console.error(err);
  } finally {
    showLoading(false);
  }
});

// ── Parse purchase-order Excel ───────────────────────────────────────────
function parsePO(wb) {
  const ws   = wb.Sheets[wb.SheetNames[0]];
  const data = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });

  // Extract metadata (발주일자, 담당자, TEL, 납품처 주소) — same logic as reading/parser.py
  let orderDate = '', contactPerson = '', contactTel = '', supplierAddress = '';
  for (let r = 0; r < Math.min(data.length, 50); r++) {
    for (let c = 0; c < Math.min(data[r].length, 10); c++) {
      const val = String(data[r][c] || '').trim();
      if (!val) continue;
      if (val.toUpperCase().includes('TEL') && !contactTel) {
        contactTel = String(data[r][c + 1] || '').trim();
      }
      if ((val === '담당자' || val === '담당자명') && !contactPerson) {
        contactPerson = String(data[r][c + 1] || '').trim();
      }
      if ((val.includes('납품처 주소') || val.includes('주소')) && !supplierAddress) {
        supplierAddress = String(data[r][c + 1] || '').trim();
      }
      if ((val.includes('발주일') || val.includes('주문일') || val.includes('날짜') || val === '일자') && !orderDate) {
        const raw = String(data[r][c + 1] || '').trim();
        if (raw) orderDate = raw;
      }
    }
  }
  poMeta = { orderDate, contactPerson, contactTel, supplierAddress };

  let startRow = -1;
  let nameCol = 2, barcodeCol = 3, qtyCol = 6, orderNoCol = -1;

  // Find header row with "No." or "NO"
  for (let r = 0; r < data.length; r++) {
    const valA = String(data[r][0] || '').trim().toUpperCase();
    if (valA === 'NO.' || valA === 'NO') {
      startRow = r + 1;
      data[r].forEach((cell, ci) => {
        const h = String(cell || '').replace(/\s|\n/g, '');
        if (h.includes('제품명') || h.includes('상품명'))         nameCol    = ci;
        else if (h.includes('바코드'))                            barcodeCol = ci;
        else if (h.includes('총') && h.includes('주문수량'))      qtyCol     = ci;
        else if (h.includes('수량') && qtyCol === 6)             qtyCol     = ci;
        else if (h.includes('주문번호') || h.includes('발주번호')) orderNoCol = ci;
      });
      break;
    }
  }

  // Fallback: look for any row with 상품명
  if (startRow === -1) {
    for (let r = 0; r < Math.min(data.length, 25); r++) {
      const row = data[r];
      if (row.some(c => String(c).includes('제품명') || String(c).includes('상품명'))) {
        startRow = r + 1;
        row.forEach((cell, ci) => {
          const h = String(cell || '').replace(/\s/g, '');
          if (h.includes('제품명') || h.includes('상품명'))  nameCol    = ci;
          else if (h.includes('바코드'))                     barcodeCol = ci;
          else if (h.includes('수량'))                       qtyCol     = ci;
          else if (h.includes('주문번호') || h.includes('발주')) orderNoCol = ci;
        });
        break;
      }
    }
  }

  if (startRow === -1) throw new Error('발주서에서 제품 목록을 찾을 수 없습니다. (No. 마커 또는 상품명 열 필요)');

  const rows = [];
  for (let r = startRow; r < data.length; r++) {
    const valA    = String(data[r][0] || '').trim().toUpperCase();
    if (valA === 'TOTAL' || valA === '합계') break;

    const name    = String(data[r][nameCol]    || '').trim();
    const barcode = String(data[r][barcodeCol] || '').trim();
    const digits  = String(data[r][qtyCol]     || '').replace(/[^\d]/g, '');
    const qty     = digits ? parseInt(digits, 10) : 0;
    const orderNo = orderNoCol >= 0 ? String(data[r][orderNoCol] || '').trim() : '';

    if (name && qty > 0) {
      rows.push({ name, barcode, qty, orderNo, seq: rows.length + 1 });
    }
  }
  return rows;
}

// ── Parse invoice Excel ───────────────────────────────────────────────────
function parseINV(wb) {
  const ws   = wb.Sheets[wb.SheetNames[0]];
  const data = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });

  // Try reading as generic table — find header row
  let startRow = 0;
  let invNoCol = -1, nameCol = -1, barcodeCol = -1, qtyCol = -1, orderNoCol = -1;

  for (let r = 0; r < Math.min(data.length, 15); r++) {
    const row = data[r];
    const rowStr = row.map(c => String(c || '').replace(/\s/g, ''));

    // Detect ERP-format header (CD_INVOICE, NM_ITEM, CD_ITEM, QT_GIR)
    const hasErpHeader = rowStr.some(h =>
      h.includes('NM_ITEM') || h.includes('CD_ITEM') || h.includes('QT_GIR') || h.includes('CD_INVOICE')
    );
    // Detect Korean-format header
    const hasKoHeader = rowStr.some(h =>
      h.includes('송장') || h.includes('상품명') || h.includes('바코드')
    );

    if (hasErpHeader || hasKoHeader) {
      startRow = r + 1;
      rowStr.forEach((h, ci) => {
        // ERP-format columns (primary)
        if (h.includes('CD_INVOICE') && invNoCol === -1)
          invNoCol = ci;
        else if (h.includes('NM_ITEM') && h.includes('_1') && nameCol === -1)
          nameCol = ci;
        else if (h.includes('CD_ITEM') && h.includes('_1') && barcodeCol === -1)
          barcodeCol = ci;
        else if (h.includes('QT_GIR') && qtyCol === -1)
          qtyCol = ci;
        // Korean fallback columns
        else if ((h.includes('송장번호') || h.includes('송장')) && invNoCol === -1)
          invNoCol = ci;
        else if ((h.includes('상품명') || h.includes('제품명')) && nameCol === -1)
          nameCol = ci;
        else if (h.includes('바코드') && barcodeCol === -1)
          barcodeCol = ci;
        else if (h.includes('수량') && qtyCol === -1)
          qtyCol = ci;
        else if ((h.includes('주문번호') || h.includes('발주')) && orderNoCol === -1)
          orderNoCol = ci;
      });
      break;
    }
  }

  const rows = [];
  for (let r = startRow; r < data.length; r++) {
    const invNo   = invNoCol   >= 0 ? String(data[r][invNoCol]   || '').trim() : '';
    const name    = nameCol    >= 0 ? String(data[r][nameCol]    || '').trim() : '';
    const barcode = barcodeCol >= 0 ? String(data[r][barcodeCol] || '').trim() : '';
    const digits  = qtyCol     >= 0 ? String(data[r][qtyCol]     || '').replace(/[^\d]/g, '') : '';
    const qty     = digits ? parseInt(digits, 10) : 0;
    const orderNo = orderNoCol >= 0 ? String(data[r][orderNoCol] || '').trim() : '';

    if (name || barcode) {
      rows.push({ invNo, name, barcode, qty, orderNo });
    }
  }
  return rows;
}

// ── Build comparison result ───────────────────────────────────────────────
function buildComparison(po, inv) {
  const result = [];
  const invUsed = new Set();

  // For each PO row find matching invoice row (by barcode or name)
  for (const poRow of po) {
    let matchedInv = null;
    let matchIdx   = -1;

    // 1st priority: match by barcode
    if (poRow.barcode) {
      matchIdx = inv.findIndex((ir, i) =>
        !invUsed.has(i) &&
        ir.barcode && ir.barcode === poRow.barcode
      );
    }

    // 2nd priority: match by normalized name
    if (matchIdx === -1) {
      const normName = normStr(poRow.name);
      matchIdx = inv.findIndex((ir, i) =>
        !invUsed.has(i) &&
        normStr(ir.name) === normName
      );
    }

    if (matchIdx !== -1) {
      matchedInv = inv[matchIdx];
      invUsed.add(matchIdx);
      const qtyDiff = matchedInv.qty - poRow.qty;
      result.push({
        status:  'ok',
        seq:     poRow.seq,
        name:    poRow.name,
        barcode: poRow.barcode,
        poQty:   poRow.qty,
        invNo:   matchedInv.invNo,
        invQty:  matchedInv.qty,
        qtyDiff,
      });
    } else {
      result.push({
        status:  'miss',
        seq:     poRow.seq,
        name:    poRow.name,
        barcode: poRow.barcode,
        poQty:   poRow.qty,
        invNo:   '',
        invQty:  0,
        qtyDiff: -poRow.qty,
      });
    }
  }

  // Invoice rows that had no PO match
  inv.forEach((ir, i) => {
    if (!invUsed.has(i) && (ir.name || ir.barcode)) {
      result.push({
        status:  'extra',
        seq:     '—',
        name:    ir.name || '—',
        barcode: ir.barcode || '',
        poQty:   0,
        invNo:   ir.invNo,
        invQty:  ir.qty,
        qtyDiff: ir.qty,
      });
    }
  });

  return result;
}

function normStr(s) {
  return String(s).replace(/\s+/g, '').toLowerCase();
}

// ────────────────────────────────────────────────────────────────────────────
// RENDER COMPARISON
// ────────────────────────────────────────────────────────────────────────────
function renderComparison() {
  const total = compResult.filter(r => r.status !== 'extra').length;
  const ok    = compResult.filter(r => r.status === 'ok').length;
  const miss  = compResult.filter(r => r.status === 'miss').length;
  const extra = compResult.filter(r => r.status === 'extra').length;
  const rate  = total > 0 ? Math.round(ok / total * 100) + '%' : '—';

  // Tiles
  mtTotal.textContent = total;
  mtOk.textContent    = ok;
  mtMiss.textContent  = miss;
  mtExtra.textContent = extra;
  mtRate.textContent  = rate;

  // Top pills
  statMatched.textContent = ok;
  statMissed.textContent  = miss;

  // Filter counts
  rcAll.textContent   = compResult.length;
  rcOk.textContent    = ok;
  rcMiss.textContent  = miss;
  rcExtra.textContent = extra;

  matchSummary.style.display = 'grid';
  emptyCompare.style.display = 'none';
  compareResult.style.display = 'block';

  updateSaveToPathBtn();
  renderTable();
}

function renderTable() {
  const q = (compareSearch?.value || '').trim().toLowerCase();

  const visible = compResult.filter(r => {
    if (filterMode !== 'all' && r.status !== filterMode) return false;
    if (q) {
      const hay = (r.name + r.barcode + r.invNo).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  compareBody.innerHTML = visible.map(r => {
    const statusBadge = {
      ok:    '<span class="status-badge status-ok">✓ 일치</span>',
      miss:  '<span class="status-badge status-miss">✗ 불일치</span>',
      extra: '<span class="status-badge status-extra">+ 송장만</span>',
    }[r.status];

    const diffHtml = r.qtyDiff === 0
      ? '<span class="diff-zero">±0</span>'
      : r.qtyDiff > 0
        ? `<span class="diff-pos">+${r.qtyDiff}</span>`
        : `<span class="diff-neg">${r.qtyDiff}</span>`;

    const barcodeHtml = r.barcode
      ? `<span class="ct-barcode-val">${escHtml(r.barcode)}</span>`
      : '<span class="ct-inv-empty">—</span>';

    const invNoHtml = r.invNo
      ? `<span class="ct-inv-val">${escHtml(r.invNo)}</span>`
      : '<span class="ct-inv-empty">송장 없음</span>';

    return `<tr class="row-${r.status}">
      <td style="text-align:center">${statusBadge}</td>
      <td style="text-align:center;color:var(--text3)">${escHtml(String(r.seq))}</td>
      <td style="text-align:left;font-weight:500;max-width:240px" title="${escHtml(r.name)}">${escHtml(r.name)}</td>
      <td>${barcodeHtml}</td>
      <td style="text-align:center;font-weight:700;color:var(--blue)">${r.poQty || '—'}</td>
      <td>${invNoHtml}</td>
      <td style="text-align:center;color:var(--green);font-weight:600">${r.invQty || '—'}</td>
      <td style="text-align:center">${diffHtml}</td>
    </tr>`;
  }).join('') || `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--text3)">결과 없음</td></tr>`;
}

// Filter tabs
document.querySelectorAll('.rtab').forEach(btn => {
  btn.addEventListener('click', () => {
    filterMode = btn.dataset.filter;
    setActiveFilter(filterMode);
    renderTable();
  });
});

compareSearch.addEventListener('input', renderTable);

function setActiveFilter(mode) {
  document.querySelectorAll('.rtab').forEach(b => b.classList.toggle('active', b.dataset.filter === mode));
}

// Export
exportResultBtn.addEventListener('click', () => {
  if (!compResult.length) return;

  const branch    = branches.find(b => b.id === currentBranchId);
  const bName     = branch ? branch.name : '기타';
  const today     = new Date().toISOString().slice(0, 10).replace(/-/g, '');

  const esc = v => `"${String(v).replace(/"/g, '""')}"`;
  const headers = ['상태', '순번', '상품명', '바코드', '발주수량', '송장번호', '송장수량', '수량차이'];
  const body = compResult.map(r => [
    { ok: '일치', miss: '불일치', extra: '송장만존재' }[r.status],
    r.seq, r.name, r.barcode, r.poQty, r.invNo, r.invQty, r.qtyDiff,
  ].map(esc).join(','));

  const csv = '\uFEFF' + [headers.map(esc).join(','), ...body].join('\n');
  downloadFile(`${bName}_대조결과_${today}.csv`, csv, 'text/csv;charset=utf-8');
  showToast('대조 결과 내보내기 완료', 'success');
});

// Save directly to the designated folder
saveToPathBtn.addEventListener('click', async () => {
  if (!compResult.length) return;
  const handle = currentBranchId && dirHandles[currentBranchId];
  if (!handle) { showToast('저장 경로가 설정되지 않았습니다', 'error'); return; }

  const branch  = branches.find(b => b.id === currentBranchId);
  const bName   = branch ? branch.name : '기타';
  const today   = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const fileName = `${bName}_대조결과_${today}.csv`;

  const esc = v => `"${String(v).replace(/"/g, '""')}"`;
  const headers = ['상태', '순번', '상품명', '바코드', '발주수량', '송장번호', '송장수량', '수량차이'];
  const body = compResult.map(r => [
    { ok: '일치', miss: '불일치', extra: '송장만존재' }[r.status],
    r.seq, r.name, r.barcode, r.poQty, r.invNo, r.invQty, r.qtyDiff,
  ].map(esc).join(','));
  const csv = '\uFEFF' + [headers.map(esc).join(','), ...body].join('\n');

  try {
    const fileHandle = await handle.getFileHandle(fileName, { create: true });
    const writable   = await fileHandle.createWritable();
    await writable.write(csv);
    await writable.close();
    showToast(`저장 완료: ${fileName}`, 'success');
  } catch (err) {
    if (err.name !== 'AbortError') showToast(`저장 실패: ${err.message}`, 'error');
  }
});

// ────────────────────────────────────────────────────────────────────────────
// HELPERS
// ────────────────────────────────────────────────────────────────────────────
function readExcel(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = e => {
      try { resolve(XLSX.read(e.target.result, { type: 'array' })); }
      catch (err) { reject(err); }
    };
    reader.onerror = () => reject(new Error('파일 읽기 실패'));
    reader.readAsArrayBuffer(file);
  });
}

function showLoading(show, title = '', detail = '') {
  loadingOverlay.style.display = show ? 'grid' : 'none';
  if (title)  loadingTitle.textContent  = title;
  if (detail) loadingDetail.textContent = detail;
}

function showToast(msg, type = 'info') {
  toast.textContent = msg;
  toast.className = `toast toast-${type} show`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => toast.classList.remove('show'), 3500);
}

function downloadFile(name, content, type) {
  const blob = new Blob([content], { type });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 500);
}

function isExcel(name) { return /\.(xlsx|xls)$/i.test(name); }

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// ────────────────────────────────────────────────────────────────────────────
// INIT
// ────────────────────────────────────────────────────────────────────────────
async function init() {
  branches = await loadBranches();
  renderBranches();
  showTab('tabWelcome');
}

// Validate stored token against the server before trusting it.
// If valid → hide overlay and init; if stale/invalid → clear and show login.
(async () => {
  if (!getToken()) return;
  try {
    const res = await fetch('/api/branches', {
      headers: { Authorization: `Bearer ${getToken()}` }
    });
    if (res.ok) {
      hideLoginOverlay();
      init();
    } else {
      clearToken();
    }
  } catch {
    clearToken();
  }
})();
