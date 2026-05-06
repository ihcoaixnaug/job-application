/* ═══════════════════════════════════════
   求职助手 — frontend logic
   ═══════════════════════════════════════ */

/* ── state ─────────────────────────────── */
let allJobs = [];
let currentView = 'kanban';
let currentDataMode = 'real';   // 'real' | 'demo'
let currentJobId = null;
let searchPoll = null;
let resumeText = '';
let preferences = '';
let pendingApplyJobId = null;
let demoMode = false;
let greetingMode = 'fixed';
let greetingTemplate = '';
let kwChips = [];   // active search keyword chips

const BASE_PREFIX = (() => {
  const p = window.location.pathname;
  if (p === '/job-application' || p.startsWith('/job-application/')) return '/job-application';
  if (p === '/job-assistant' || p.startsWith('/job-assistant/')) return '/job-assistant';
  return '';
})();

function withBase(path) {
  if (/^https?:\/\//.test(path)) return path;
  return `${BASE_PREFIX}${path.startsWith('/') ? path : `/${path}`}`;
}

/* status pipeline */
const PIPELINE = ['pending','applied','reviewing','testing','interviewing','offered','rejected'];
const STATUS_LABEL = {
  pending:     '待投递',
  applied:     '已投递',
  reviewing:   '简历筛选中',
  testing:     '笔试/测评',
  interviewing:'面试中',
  offered:     '🎉 Offer',
  rejected:    '未通过',
};
const NEXT_STATUS = {
  pending:     'applied',
  applied:     'reviewing',
  reviewing:   'testing',
  testing:     'interviewing',
  interviewing:'offered',
};
const ADVANCE_LABEL = {
  pending:     '投递',
  applied:     '进入筛选',
  reviewing:   '收到测评',
  testing:     '收到面试',
  interviewing:'拿到Offer',
};

/* tier badge config */
const TIER_CFG = {
  '大厂': { cls: 'tier-big',  label: '大厂' },
  '中厂': { cls: 'tier-mid',  label: '中厂' },
  '小厂': { cls: 'tier-small',label: '小厂' },
};

/* Boss activity config */
const ACTIVITY_CFG = {
  '今日活跃': { cls: 'act-today',  icon: '●' },
  '3天内活跃':{ cls: 'act-recent', icon: '●' },
  '本周活跃': { cls: 'act-week',   icon: '●' },
};

/* timeline dot class by keyword */
function tlClass(text) {
  if (/offer|Offer/.test(text))            return 'tl-offered';
  if (/面试|hr面|业务面/.test(text))       return 'tl-interviewing';
  if (/笔试|测评|笔测/.test(text))         return 'tl-testing';
  if (/筛选|评估|查看/.test(text))         return 'tl-reviewing';
  if (/投递|打招呼|简历/.test(text))       return 'tl-applied';
  if (/挂|拒|未通过|不合适/.test(text))    return 'tl-rejected';
  return '';
}

/* ── init ──────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  await Promise.all([
    loadResume(), loadPreferences(), loadSettings(),
    loadJobs(), loadDemoMode(), loadGreetingSettings(),
  ]);
  loadBossStatus();
  setupDnD();
  setupFileDrop();
  setInterval(loadJobs, 30000);
  setInterval(loadBossStatus, 5000);
});

/* ── resume ────────────────────────────── */
async function loadResume() {
  try {
    const d = await apiFetch('/api/resume');
    if (d.filename) {
      setUploadedName(d.filename);
      resumeText = d.text || '';
      document.getElementById('resumeText').value = resumeText;
      document.getElementById('resumeDetails').style.display = 'block';
      document.getElementById('resumeEmpty').style.display = 'none';
    }
  } catch (e) {}
}

async function uploadResume(e) {
  const file = e.target.files[0];
  if (!file) return;
  if (!file.name.endsWith('.docx')) { toast('请上传 .docx 文件', 'error'); return; }
  toast('解析简历中…', 'info');
  const fd = new FormData();
  fd.append('file', file);
  try {
    await fetch(withBase('/api/resume/upload'), { method: 'POST', body: fd }).then(r => r.json());
    const full = await apiFetch('/api/resume');
    resumeText = full.text || '';
    document.getElementById('resumeText').value = resumeText;
    setUploadedName(file.name);
    document.getElementById('resumeDetails').style.display = 'block';
    document.getElementById('resumeEmpty').style.display = 'none';
    toast('✅ 简历解析完成', 'success');
  } catch (e) { toast('上传失败: ' + e.message, 'error'); }
}

function setUploadedName(name) {
  document.getElementById('uploadHint').style.display = 'none';
  const el = document.getElementById('uploadedName');
  el.style.display = 'block';
  el.textContent = '✅ ' + name;
}

function setupFileDrop() {
  const area = document.getElementById('uploadArea');
  area.addEventListener('dragover', e => { e.preventDefault(); area.style.borderColor = 'var(--primary)'; });
  area.addEventListener('dragleave', () => { area.style.borderColor = ''; });
  area.addEventListener('drop', e => {
    e.preventDefault(); area.style.borderColor = '';
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const dt = new DataTransfer(); dt.items.add(file);
    const inp = document.getElementById('resumeFile');
    inp.files = dt.files;
    uploadResume({ target: inp });
  });
}

/* ── preferences ───────────────────────── */
async function loadPreferences() {
  try {
    const d = await apiFetch('/api/preferences');
    preferences = d.preferences || '';
    document.getElementById('preferences').value = preferences;
  } catch (e) {}
}

async function savePrefs() {
  preferences = document.getElementById('preferences').value.trim();
  await apiFetch('/api/preferences', 'POST', { preferences });
  toast('偏好已保存', 'success');
}

/* ── keyword chips ─────────────────────── */
function renderKwChips() {
  const wrap = document.getElementById('kwChips');
  if (!wrap) return;
  wrap.innerHTML = kwChips.map((kw, i) =>
    `<span class="kw-chip">${esc(kw)}<button onclick="removeKwChip(${i})" title="移除">×</button></span>`
  ).join('');
}

function addKwChip(kw) {
  const inp = document.getElementById('keyword');
  const val = (kw || inp.value).trim();
  if (!val) return;
  if (!kwChips.includes(val)) {
    kwChips.push(val);
    renderKwChips();
  }
  inp.value = '';
}

function removeKwChip(i) {
  kwChips.splice(i, 1);
  renderKwChips();
}

function kwInputKeydown(e) {
  if (e.key === 'Enter') { e.preventDefault(); addKwChip(); }
}

async function generateKeywords() {
  const prefs = document.getElementById('preferences').value.trim();
  if (!prefs) return toast('请先填写投岗偏好', 'error');
  const btn = document.getElementById('kwGenBtn');
  btn.disabled = true; btn.textContent = '生成中…';
  try {
    const d = await apiFetch('/api/generate-keywords', 'POST', { preferences: prefs });
    const newKws = (d.keywords || []).filter(k => !kwChips.includes(k));
    kwChips = [...kwChips, ...newKws];
    renderKwChips();
    toast(`✅ 已生成 ${d.keywords.length} 个关键词`, 'success');
  } catch (e) {
    toast('生成失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '🤖 AI 解析偏好';
  }
}

/* ── greeting settings ─────────────────── */
async function loadGreetingSettings() {
  try {
    const d = await apiFetch('/api/greeting-settings');
    greetingMode     = d.mode     || 'fixed';
    greetingTemplate = d.template || '';
    _applyGreetingModeUI();
  } catch (e) {}
}

function _applyGreetingModeUI() {
  const fixedRad = document.getElementById('greetFixed');
  const aiRad    = document.getElementById('greetAI');
  const wrap     = document.getElementById('greetingTemplateWrap');
  const tplInp   = document.getElementById('greetingTplInput');
  if (fixedRad) fixedRad.checked = (greetingMode === 'fixed');
  if (aiRad)    aiRad.checked    = (greetingMode === 'ai');
  if (wrap)     wrap.style.display = greetingMode === 'fixed' ? 'block' : 'none';
  if (tplInp)   tplInp.value = greetingTemplate;
}

function onGreetingModeChange() {
  greetingMode = document.querySelector('input[name="greetingMode"]:checked')?.value || 'fixed';
  _applyGreetingModeUI();
}

async function saveGreetingSettings() {
  const mode     = document.querySelector('input[name="greetingMode"]:checked')?.value || 'fixed';
  const template = document.getElementById('greetingTplInput').value;
  greetingMode     = mode;
  greetingTemplate = template;
  await apiFetch('/api/greeting-settings', 'POST', { mode, template });
  toast('打招呼设置已保存', 'success');
}

/* ── demo mode ─────────────────────────── */
async function loadDemoMode() {
  try {
    const d = await apiFetch('/api/demo-mode');
    demoMode = d.enabled;
    _applyDemoModeUI();
  } catch (e) {}
}

async function toggleDemoMode() {
  demoMode = !demoMode;
  try {
    await apiFetch('/api/demo-mode', 'POST', { enabled: demoMode });
    _applyDemoModeUI();
    toast(demoMode ? '已切换到演示模式' : '已切换到真实模式', 'info');
  } catch (e) {
    demoMode = !demoMode;
    toast('切换失败: ' + e.message, 'error');
  }
}

function _applyDemoModeUI() {
  const pill  = document.getElementById('demoPill');
  const dot   = document.getElementById('demoDot');
  const label = document.getElementById('demoLabel');
  const btn   = document.getElementById('searchBtn');
  if (demoMode) {
    pill.classList.add('demo-pill--on');
    dot.classList.add('demo-dot--on');
    if (btn) btn.textContent = '📦 加载演示数据';
  } else {
    pill.classList.remove('demo-pill--on');
    dot.classList.remove('demo-dot--on');
    if (btn) btn.textContent = '🚀 搜索并 AI 匹配';
  }
}

/* ── settings ──────────────────────────── */
async function loadSettings() {
  try {
    const d = await apiFetch('/api/settings');
    document.getElementById('apiDot').className =
      'api-dot ' + (d.has_api_key ? 'api-dot--on' : 'api-dot--off');
    document.getElementById('apiDot').title =
      d.has_api_key ? 'OpenRouter 已配置' : 'OpenRouter 未配置';
    if (d.model) {
      const sel = document.getElementById('modelSel');
      [...sel.options].forEach(o => { if (o.value === d.model) o.selected = true; });
    }
    if (d.shixiseng_phone) document.getElementById('sxsPhone').value = d.shixiseng_phone;
  } catch (e) {}
}

function openSettings()  {
  document.getElementById('settingsModal').classList.add('open');
  _applyGreetingModeUI();
}
function closeSettings() { document.getElementById('settingsModal').classList.remove('open'); }

async function saveSettings() {
  await apiFetch('/api/settings', 'POST', {
    openrouter_api_key: document.getElementById('apiKey').value || null,
    openrouter_model:   document.getElementById('modelSel').value || null,
    shixiseng_phone:    document.getElementById('sxsPhone').value || null,
  });
  toast('设置已保存', 'success');
  closeSettings();
  await loadSettings();
}

async function sxsSendCode() {
  const phone = document.getElementById('sxsPhone').value.trim();
  const statusEl = document.getElementById('sxsStatus');
  statusEl.textContent = '正在打开浏览器…';
  if (phone) apiFetch('/api/settings', 'POST', { shixiseng_phone: phone }).catch(() => {});
  try {
    const { task_id } = await apiFetch('/api/shixiseng-send-code', 'POST', { phone: phone || '' });
    const iv = setInterval(async () => {
      try {
        const d = await apiFetch(`/api/task/${task_id}`);
        if (d.status === 'completed') {
          clearInterval(iv);
          statusEl.textContent = '⏳ 浏览器已打开，请在浏览器中完成登录后点击右侧按钮';
          document.getElementById('sxsSaveBtn').style.display = 'inline-block';
        } else if (d.status === 'error') {
          clearInterval(iv);
          statusEl.textContent = '❌ ' + d.message;
        }
      } catch (pe) { clearInterval(iv); statusEl.textContent = '❌ 网络错误'; }
    }, 1500);
  } catch (e) { statusEl.textContent = '❌ ' + e.message; }
}

async function sxsSaveSession() {
  const statusEl = document.getElementById('sxsStatus');
  statusEl.textContent = '保存中…';
  try {
    await apiFetch('/api/shixiseng-save-session', 'POST');
    statusEl.textContent = '✅ 实习僧登录状态已保存';
    document.getElementById('sxsSaveBtn').style.display = 'none';
    toast('实习僧登录成功！', 'success');
  } catch (e) { statusEl.textContent = '❌ ' + e.message; }
}

async function bossLogin() {
  const statusEl = document.getElementById('bossStatus');
  statusEl.textContent = '正在打开浏览器…';
  try {
    const { task_id } = await apiFetch('/api/boss-login', 'POST');
    const iv = setInterval(async () => {
      const d = await apiFetch(`/api/task/${task_id}`);
      if (d.status === 'completed') {
        clearInterval(iv);
        statusEl.textContent = '⏳ 浏览器已打开，请扫码，完成后点击右侧按钮';
        document.getElementById('bossSaveBtn').style.display = 'inline-block';
      } else if (d.status === 'error') {
        clearInterval(iv);
        statusEl.textContent = '❌ ' + d.message;
      }
    }, 1500);
  } catch (e) { statusEl.textContent = '❌ ' + e.message; }
}

async function bossSaveSession() {
  const statusEl = document.getElementById('bossStatus');
  statusEl.textContent = '验证登录状态…';
  try {
    await apiFetch('/api/boss-save-session', 'POST');
    statusEl.textContent = '✅ Boss直聘登录成功，已保存';
    document.getElementById('bossSaveBtn').style.display = 'none';
    toast('Boss直聘登录成功！', 'success');
    loadBossStatus();
  } catch (e) { statusEl.textContent = '❌ ' + e.message; }
}

async function loadBossStatus() {
  try {
    const d = await apiFetch('/api/boss-status');
    const dot = document.getElementById('bossStatusDot');
    if (d.active) {
      dot.className = 'boss-status-dot boss-status-dot--on';
      dot.title = 'Boss直聘 已连接';
    } else {
      dot.className = 'boss-status-dot boss-status-dot--off';
      dot.title = 'Boss直聘 未连接';
    }
  } catch (e) {}
}

async function openBossWindow() {
  toast('正在打开 Boss 登录窗口…', 'info');
  try {
    const { task_id } = await apiFetch('/api/boss-login', 'POST');
    const iv = setInterval(async () => {
      try {
        const d = await apiFetch(`/api/task/${task_id}`);
        if (d.status === 'completed') {
          clearInterval(iv);
          toast('Boss 浏览器已打开，请扫码登录', 'info');
        } else if (d.status === 'error') {
          clearInterval(iv);
          toast('打开失败: ' + d.message, 'error');
        }
      } catch (pe) { clearInterval(iv); }
    }, 1500);
  } catch (e) { toast('打开失败: ' + e.message, 'error'); }
}

/* ── data mode switch ──────────────────── */
function switchDataMode(mode, btn) {
  currentDataMode = mode;
  document.querySelectorAll('.dbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  loadJobs();
}

/* ── data ──────────────────────────────── */
async function loadJobs() {
  try {
    const demoFlag = currentDataMode === 'demo' ? 1 : 0;
    const [jobs, stats] = await Promise.all([
      apiFetch(`/api/jobs?demo=${demoFlag}`),
      apiFetch(`/api/stats?demo=${demoFlag}`),
    ]);
    allJobs = jobs;
    rerender();
    PIPELINE.forEach(k => {
      const el = document.getElementById('s-' + k);
      if (el) el.textContent = stats[k] || 0;
    });
  } catch (e) { console.error('loadJobs', e); }
}

/* ── search ────────────────────────────── */
async function startSearch() {
  const resume = resumeText || document.getElementById('resumeText').value.trim();
  if (!resume && !demoMode) return toast('请先上传简历', 'error');

  const prefs = document.getElementById('preferences').value.trim();

  // Collect keywords: chips first, then inline input, then auto-fill from prefs
  let activeKws = [...kwChips];
  const inlineKw = document.getElementById('keyword').value.trim();
  if (inlineKw && !activeKws.includes(inlineKw)) activeKws.push(inlineKw);
  if (!activeKws.length && prefs) {
    activeKws = prefs.split('/').map(s => s.trim()).filter(Boolean).slice(0, 1);
  }
  if (!activeKws.length && !demoMode) return toast('请添加搜索关键词，或点击"AI 解析偏好"生成', 'error');

  const platforms = [];
  if (document.getElementById('cb-boss').checked)      platforms.push('boss');
  if (document.getElementById('cb-shixiseng').checked) platforms.push('shixiseng');
  if (!platforms.length) return toast('请选择至少一个平台', 'error');

  setSearching(true); showProg(true);

  try {
    const { task_id } = await apiFetch('/api/search', 'POST', {
      keyword:          activeKws[0] || '实习',
      keywords:         activeKws,
      resume:           resume  || '（演示模式）',
      preferences:      prefs,
      platforms,
      cities:           [...document.querySelectorAll('input[name="city"]:checked')].map(el => el.value),
      max_pages:        +document.getElementById('maxPages').value,
      top_n:            +document.getElementById('topN').value,
      boss_active_today:document.getElementById('cb-boss-active').checked,
    });
    searchPoll = setInterval(() => pollSearch(task_id), 1200);
  } catch (e) {
    toast('搜索失败: ' + e.message, 'error');
    setSearching(false); showProg(false);
  }
}

async function pollSearch(tid) {
  const d = await apiFetch(`/api/task/${tid}`);
  setProg(d.progress || 0, d.message || '…');
  if (d.status === 'completed') {
    clearInterval(searchPoll); setSearching(false); showProg(false);
    // Auto-switch view to whichever tab matches the search that just finished
    const targetMode = demoMode ? 'demo' : 'real';
    if (currentDataMode !== targetMode) {
      currentDataMode = targetMode;
      const btnId = targetMode === 'demo' ? 'dtDemo' : 'dtReal';
      document.querySelectorAll('.dbtn').forEach(b => b.classList.remove('active'));
      document.getElementById(btnId)?.classList.add('active');
    }
    await loadJobs();
    toast('✅ ' + d.message, 'success');
  } else if (d.status === 'error') {
    clearInterval(searchPoll); setSearching(false); showProg(false);
    toast('失败: ' + d.message, 'error');
  }
}

function setSearching(v) {
  const btn = document.getElementById('searchBtn');
  btn.disabled = v;
  btn.textContent = v ? '⏳ 处理中…' : (demoMode ? '📦 加载演示数据' : '🚀 搜索并 AI 匹配');
}
function showProg(v) { document.getElementById('progCard').style.display = v ? 'block' : 'none'; }
function setProg(p, msg) {
  document.getElementById('progFill').style.width = p + '%';
  document.getElementById('progMsg').textContent = msg;
}

/* ── render ────────────────────────────── */
function rerender() {
  const fp   = document.getElementById('fPlatform').value;
  const ft   = document.getElementById('fTier')?.value    || '';
  const fs   = +document.getElementById('fScore').value   || 0;
  const sort = document.getElementById('fSort')?.value    || 'score_desc';
  let jobs = allJobs.filter(j => {
    if (fp && j.platform !== fp)               return false;
    if (ft && j.company_tier !== ft)           return false;
    if (fs && (j.match_score || 0) < fs)       return false;
    return true;
  });
  jobs = sortJobs(jobs, sort);
  currentView === 'kanban' ? renderKanban(jobs) : renderTable(jobs);
}

function sortJobs(jobs, sort) {
  const [field, dir] = sort.split('_');
  return [...jobs].sort((a, b) => {
    let va, vb;
    if      (field === 'score')    { va = a.match_score||0;  vb = b.match_score||0; }
    else if (field === 'title')    { va = a.title||'';        vb = b.title||''; }
    else if (field === 'company')  { va = a.company||'';      vb = b.company||''; }
    else if (field === 'location') { va = a.location||'';     vb = b.location||''; }
    else if (field === 'status')   {
      va = PIPELINE.indexOf(a.status||'pending');
      vb = PIPELINE.indexOf(b.status||'pending');
    }
    else return 0;
    if (typeof va === 'string') return dir === 'desc' ? vb.localeCompare(va) : va.localeCompare(vb);
    return dir === 'desc' ? vb - va : va - vb;
  });
}

function renderKanban(jobs) {
  const cols = {};
  PIPELINE.forEach(s => cols[s] = []);
  jobs.forEach(j => { const s = j.status || 'pending'; if (cols[s]) cols[s].push(j); });
  PIPELINE.forEach(s => {
    const body = document.getElementById('col-' + s);
    const cnt  = document.getElementById('cnt-' + s);
    if (!body) return;
    const list = jobs.filter(j => (j.status || 'pending') === s);
    body.innerHTML = list.length
      ? list.map(jobCard).join('')
      : '<div class="col-empty">暂无职位</div>';
    cnt.textContent = cols[s].length;
  });
}

function tierBadge(tier) {
  const cfg = TIER_CFG[tier];
  if (!cfg) return '';
  return `<span class="tier-badge ${cfg.cls}">${cfg.label}</span>`;
}

function activityBadge(activity) {
  if (!activity) return '';
  const cfg = ACTIVITY_CFG[activity];
  if (cfg) return `<span class="act-badge ${cfg.cls}">${cfg.icon} ${activity}</span>`;
  return `<span class="act-badge act-other">${activity}</span>`;
}

function jobCard(j) {
  const score    = j.match_score || 0;
  const hasScore = score > 0;
  const sc       = hasScore ? (score >= 80 ? 'score-high' : score >= 60 ? 'score-mid' : 'score-low') : 'score-none';
  const ptag     = j.platform === 'boss'
    ? '<span class="tag tag-boss">Boss</span>'
    : '<span class="tag tag-shixiseng">实习僧</span>';
  const salary   = j.salary   ? `<span class="tag tag-salary">${esc(j.salary)}</span>` : '';
  const loc      = j.location ? `<span class="tag tag-loc">${esc(j.location.substring(0,8))}</span>` : '';
  const next     = NEXT_STATUS[j.status || 'pending'];
  const advLbl   = next ? ADVANCE_LABEL[j.status || 'pending'] : '';

  const tier     = tierBadge(j.company_tier);
  const activity = j.platform === 'boss' ? activityBadge(j.boss_activity) : '';

  let chipHtml = '';
  try {
    const hl = JSON.parse(j.match_highlights || '[]').slice(0, 2);
    const cn = JSON.parse(j.match_concerns  || '[]').slice(0, 1);
    if (hl.length || cn.length) {
      chipHtml = '<div class="chips">'
        + hl.map(h => `<span class="chip chip-good">✓ ${esc(h)}</span>`).join('')
        + cn.map(c => `<span class="chip chip-bad">△ ${esc(c)}</span>`).join('')
        + '</div>';
    }
  } catch (e) {}

  let tlHtml = '';
  const tlog = (j.timeline_log || '').trim();
  if (tlog) {
    const lines = tlog.split('\n').filter(Boolean).slice(-2);
    tlHtml = '<div class="mini-tl">'
      + lines.map(line => {
          const cls = tlClass(line);
          return `<div class="mini-tl-item"><span class="mini-tl-dot ${cls}"></span><span>${esc(line)}</span></div>`;
        }).join('')
      + '</div>';
  }

  const applyLbl    = j.platform === 'boss' ? '打招呼' : '投简历';
  const actionApply = (j.status || 'pending') === 'pending'
    ? `<button class="btn btn-primary btn-xs" onclick="quickApply(${j.id})" title="自动投递">${applyLbl}</button>`
    : '';
  const actionAdvance = next
    ? `<button class="btn btn-advance btn-xs" onclick="advance(${j.id},'${next}')" title="标记为下一阶段">${advLbl} ▶</button>`
    : '';
  const actionReject = (j.status || 'pending') !== 'rejected' && (j.status || 'pending') !== 'offered'
    ? `<button class="btn btn-ghost btn-xs" onclick="setStatus(${j.id},'rejected')" title="未通过">✕</button>`
    : '';

  return `<div class="jcard ${sc}" draggable="true" data-id="${j.id}" onclick="openDetail(${j.id})">
    <div class="card-top">
      <input class="card-cb" type="checkbox" onclick="cardCheck(event,${j.id})">
      <span class="jtitle">${esc(j.title)}</span>
    </div>
    <div class="jcompany-row">
      <span class="jcompany">${esc(j.company)}</span>
      ${tier}
    </div>
    <div class="jtags">${salary}${ptag}${loc}${activity}</div>
    ${hasScore ? `
    <div class="match-row ${sc}">
      <div class="sbar"><div class="sfill" style="width:${score}%"></div></div>
      <span class="stext">${Math.round(score)}</span>
    </div>` : ''}
    ${chipHtml}
    ${tlHtml}
    <div class="card-actions" onclick="event.stopPropagation()">
      ${actionApply}${actionAdvance}${actionReject}
      <a href="${j.url||'#'}" target="_blank" class="btn btn-ghost btn-xs" onclick="event.stopPropagation()">查看</a>
    </div>
  </div>`;
}

function renderTable(jobs) {
  document.getElementById('tbody').innerHTML = jobs.map(j => {
    const score = j.match_score || 0;
    const sc    = score >= 80 ? 'high' : score >= 60 ? 'mid' : score > 0 ? 'low' : 'none';
    const st    = j.status || 'pending';
    return `<tr>
      <td><input type="checkbox" class="row-cb" data-id="${j.id}"></td>
      <td><span class="sbadge sbadge-${sc}">${score > 0 ? Math.round(score) : '—'}</span></td>
      <td>
        <div style="font-weight:600;font-size:.82rem">${esc(j.title)}</div>
        ${j.match_reason ? `<div style="font-size:.7rem;color:var(--muted)">${esc(j.match_reason)}</div>` : ''}
      </td>
      <td>
        <div style="font-size:.82rem">${esc(j.company)}</div>
        ${j.company_tier ? `<div>${tierBadge(j.company_tier)}</div>` : ''}
      </td>
      <td style="color:var(--success);font-weight:500;font-size:.78rem">${esc(j.salary||'—')}</td>
      <td style="font-size:.78rem">${esc(j.location||'—')}</td>
      <td>
        <span class="tag ${j.platform==='boss'?'tag-boss':'tag-shixiseng'}">${j.platform==='boss'?'Boss':'实习僧'}</span>
        ${j.platform==='boss' && j.boss_activity ? `<div style="margin-top:2px">${activityBadge(j.boss_activity)}</div>` : ''}
      </td>
      <td>${j.company_tier ? tierBadge(j.company_tier) : '—'}</td>
      <td><span class="stbadge st-${st}">${STATUS_LABEL[st]||st}</span></td>
      <td>
        <div style="display:flex;gap:3px">
          <button class="btn btn-primary btn-xs" onclick="quickApply(${j.id})">${j.platform==='boss'?'打招呼':'投简历'}</button>
          <button class="btn btn-ghost    btn-xs" onclick="openDetail(${j.id})">详情</button>
          <a href="${j.url||'#'}" target="_blank" class="btn btn-ghost btn-xs">链接</a>
        </div>
      </td>
    </tr>`;
  }).join('');
}

/* ── view switch ───────────────────────── */
function switchView(v, btn) {
  currentView = v;
  document.querySelectorAll('.vbtn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('kanban').style.display = v === 'kanban' ? 'flex' : 'none';
  document.getElementById('tview').style.display  = v === 'table'  ? 'block' : 'none';
  rerender();
}

/* ── apply ─────────────────────────────── */
function getResume() { return resumeText || document.getElementById('resumeText').value.trim(); }
function getPrefs()  { return document.getElementById('preferences').value.trim() || preferences; }

async function quickApply(jobId) {
  const job = allJobs.find(j => j.id === jobId);
  if (!job) return;
  if (job.platform === 'boss') {
    pendingApplyJobId = jobId;
    const greetingModal = document.getElementById('greetingModal');
    const textarea      = document.getElementById('greetingText');
    const jobInfo       = document.getElementById('greetingJobInfo');
    jobInfo.textContent = `${job.title} @ ${job.company}`;
    greetingModal.classList.add('open');

    if (greetingMode === 'fixed') {
      textarea.value = greetingTemplate || '（请在设置中填写固定文案模版）';
    } else {
      textarea.value = '生成中…';
      try {
        const d = await apiFetch(`/api/jobs/${jobId}/preview-greeting`, 'POST',
          { resume: getResume(), preferences: getPrefs() });
        textarea.value = d.greeting || '';
      } catch (e) {
        textarea.value = '';
        toast('生成失败: ' + e.message, 'error');
      }
    }
  } else {
    const resume = getResume();
    if (!resume && !demoMode) return toast('请先上传简历', 'error');
    toast('投递中…', 'info');
    try {
      const { task_id } = await apiFetch(`/api/jobs/${jobId}/apply`, 'POST',
        { job_ids: [jobId], resume: resume || '（演示）', preferences: getPrefs() });
      pollApply(task_id);
    } catch (e) { toast('投递失败: ' + e.message, 'error'); }
  }
}

function closeGreetingModal() {
  document.getElementById('greetingModal').classList.remove('open');
  pendingApplyJobId = null;
}

async function confirmSendGreeting() {
  if (!pendingApplyJobId) return;
  const jobId = pendingApplyJobId;
  const msg   = document.getElementById('greetingText').value.trim();
  closeGreetingModal();
  toast('发送中…', 'info');
  try {
    const { task_id } = await apiFetch(`/api/jobs/${jobId}/apply`, 'POST',
      { job_ids: [jobId], resume: getResume() || '（演示）', preferences: getPrefs(), custom_message: msg });
    pollApply(task_id);
  } catch (e) { toast('发送失败: ' + e.message, 'error'); }
}

async function applyCurrent() {
  if (currentJobId) { closeJobModal(); await quickApply(currentJobId); }
}

async function rejectCurrent() {
  if (currentJobId) {
    await setStatus(currentJobId, 'rejected');
    closeJobModal();
    toast('已标记未通过', 'info');
  }
}

async function applySelected() {
  const ids = getSelectedIds();
  if (!ids.length) return toast('请先选中岗位', 'error');
  const resume = getResume();
  if (!resume && !demoMode) return toast('请先上传简历', 'error');
  toast(`批量投递 ${ids.length} 个…`, 'info');
  const { task_id } = await apiFetch('/api/apply-batch', 'POST',
    { job_ids: ids, resume: resume || '（演示）', preferences: getPrefs() });
  pollApply(task_id, '批量投递');
}

function pollApply(tid, label = '投递') {
  const iv = setInterval(async () => {
    const d = await apiFetch(`/api/task/${tid}`);
    if (d.status === 'completed') {
      clearInterval(iv);
      toast(`✅ ${label}完成！${d.message||''}`, 'success');
      await loadJobs();
    } else if (d.status === 'error') {
      clearInterval(iv);
      toast(`${label}失败: ${d.message}`, 'error');
    }
  }, 1500);
}

function getSelectedIds() {
  if (currentView === 'kanban')
    return [...document.querySelectorAll('.jcard.selected')].map(c => +c.dataset.id);
  return [...document.querySelectorAll('.row-cb:checked')].map(c => +c.dataset.id);
}

/* ── status & advance ──────────────────── */
async function setStatus(jobId, status) {
  await apiFetch(`/api/jobs/${jobId}/status`, 'PUT', { status });
  await loadJobs();
  if (currentJobId === jobId) openDetail(jobId);
}

async function advance(jobId, nextStatus) {
  await setStatus(jobId, nextStatus);
  toast(`已推进 → ${STATUS_LABEL[nextStatus]}`, 'success');
}

/* ── timeline ──────────────────────────── */
async function addTimeline(jobId, entry) {
  if (!entry.trim()) return;
  await apiFetch(`/api/jobs/${jobId}/timeline`, 'POST', { entry });
  await loadJobs();
  openDetail(jobId);
}

/* ── selection ─────────────────────────── */
function cardCheck(e, id) {
  e.stopPropagation();
  e.target.closest('.jcard').classList.toggle('selected', e.target.checked);
}
function toggleAll() {
  const v = document.getElementById('cbAll').checked;
  document.querySelectorAll('.row-cb').forEach(cb => cb.checked = v);
}

/* ── drag and drop ─────────────────────── */
function setupDnD() {
  document.addEventListener('dragstart', e => {
    const c = e.target.closest('.jcard');
    if (!c) return;
    e.dataTransfer.setData('text/plain', c.dataset.id);
    c.classList.add('dragging');
  });
  document.addEventListener('dragend', e => {
    const c = e.target.closest('.jcard');
    if (c) c.classList.remove('dragging');
  });
  document.querySelectorAll('.col-body').forEach(col => {
    col.addEventListener('dragover',  e => { e.preventDefault(); col.classList.add('drag-over'); });
    col.addEventListener('dragleave', ()  => col.classList.remove('drag-over'));
    col.addEventListener('drop', async e => {
      e.preventDefault(); col.classList.remove('drag-over');
      const id     = +e.dataTransfer.getData('text/plain');
      const status = col.closest('.col').dataset.status;
      if (id && status) { await advance(id, status); }
    });
  });
}

/* ── job detail modal ──────────────────── */
function openDetail(id) {
  const j = allJobs.find(x => x.id === id);
  if (!j) return;
  currentJobId = id;
  document.getElementById('modalTitle').textContent = j.title;
  document.getElementById('modalLink').href = j.url || '#';

  const score   = j.match_score || 0;
  const sc      = score >= 80 ? 'high' : score >= 60 ? 'mid' : score > 0 ? 'low' : 'none';
  const st      = j.status || 'pending';
  const statusOpts = PIPELINE.map(v =>
    `<option value="${v}" ${st===v?'selected':''}>${STATUS_LABEL[v]}</option>`
  ).join('');

  let insightHtml = '';
  try {
    const hl = JSON.parse(j.match_highlights || '[]');
    const cn = JSON.parse(j.match_concerns  || '[]');
    if (hl.length) insightHtml += `<div style="margin-bottom:6px"><div style="font-size:.7rem;color:var(--muted);margin-bottom:3px">✅ 匹配亮点</div><ul class="insight-list insight-good">${hl.map(h=>`<li>${esc(h)}</li>`).join('')}</ul></div>`;
    if (cn.length) insightHtml += `<div style="margin-bottom:6px"><div style="font-size:.7rem;color:var(--muted);margin-bottom:3px">⚠️ 潜在不足</div><ul class="insight-list insight-bad">${cn.map(c=>`<li>${esc(c)}</li>`).join('')}</ul></div>`;
  } catch (e) {}

  const tlog = (j.timeline_log || '').trim();
  const tlItems = tlog
    ? tlog.split('\n').filter(Boolean).map(line => {
        const sp   = line.indexOf(' ');
        const ts   = sp > 0 ? line.slice(0, sp)    : '';
        const text = sp > 0 ? line.slice(sp+1)     : line;
        const cls  = tlClass(line);
        return `<div class="tl-log-item"><span class="tl-ts">${esc(ts)}</span><span class="tl-text"><span class="mini-tl-dot ${cls}" style="display:inline-block;margin-right:5px;vertical-align:middle"></span>${esc(text)}</span></div>`;
      }).join('')
    : '<div style="font-size:.75rem;color:var(--muted)">暂无记录</div>';

  const actBadge = j.platform === 'boss' && j.boss_activity ? activityBadge(j.boss_activity) : '';

  document.getElementById('modalBody').innerHTML = `
    <div class="detail-grid">
      <div class="dfield"><label>公司</label><span>${esc(j.company)} ${tierBadge(j.company_tier)}</span></div>
      <div class="dfield"><label>薪资</label><span style="color:var(--success)">${esc(j.salary||'面议')}</span></div>
      <div class="dfield"><label>地点</label><span>${esc(j.location||'—')}</span></div>
      <div class="dfield"><label>平台</label><span>${j.platform==='boss'?'Boss直聘':'实习僧'} ${actBadge}</span></div>
    </div>

    ${score > 0 ? `
    <div class="score-panel">
      <span class="sbadge sbadge-${sc}" style="width:48px;height:48px;font-size:1.1rem;flex-shrink:0">${Math.round(score)}</span>
      <div style="flex:1">
        <div style="font-weight:600">AI匹配度 ${Math.round(score)} 分</div>
        <div style="font-size:.76rem;color:var(--muted);margin-top:2px">${esc(j.match_reason||'')}</div>
        ${insightHtml}
      </div>
    </div>` : ''}

    <div style="margin-bottom:14px">
      <div style="font-size:.7rem;color:var(--muted);margin-bottom:4px">当前状态</div>
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
        <select style="width:auto" onchange="setStatus(${j.id},this.value)">${statusOpts}</select>
        ${NEXT_STATUS[st] ? `<button class="btn btn-advance btn-sm" onclick="advance(${j.id},'${NEXT_STATUS[st]}')">推进 → ${STATUS_LABEL[NEXT_STATUS[st]]}</button>` : ''}
      </div>
    </div>

    ${j.requirements ? `<div style="margin-bottom:14px"><div style="font-size:.7rem;color:var(--muted);margin-bottom:4px">岗位要求</div><div style="font-size:.82rem;line-height:1.6">${esc(j.requirements)}</div></div>` : ''}
    ${j.description  ? `<div style="margin-bottom:14px"><div style="font-size:.7rem;color:var(--muted);margin-bottom:4px">职位描述</div><div style="font-size:.8rem;line-height:1.7;white-space:pre-wrap;max-height:160px;overflow:auto">${esc(j.description).substring(0,600)}${j.description.length>600?'…':''}</div></div>` : ''}

    <div class="msec" style="margin-top:10px;padding-top:10px">
      <div style="font-size:.7rem;font-weight:600;color:var(--muted);margin-bottom:6px">📅 进度时间线</div>
      <div class="tl-log" id="tlLog">${tlItems}</div>
      <div class="tl-add">
        <input type="text" id="tlInput" placeholder="添加进展备注，如：收到笔试邀请">
        <button class="btn btn-primary btn-sm" onclick="addTimeline(${j.id},document.getElementById('tlInput').value)">记录</button>
      </div>
    </div>`;

  document.getElementById('modalApplyBtn').textContent =
    j.platform === 'boss' ? '🗣 打招呼' : '📩 投递简历';
  document.getElementById('jobModal').classList.add('open');
}

function closeJobModal() {
  document.getElementById('jobModal').classList.remove('open');
  currentJobId = null;
}

/* ── api helper ────────────────────────── */
async function apiFetch(url, method = 'GET', body = null) {
  const opts = { method, headers: {} };
  if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(withBase(url), opts);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { const d = await r.json(); msg = d.detail || msg; } catch (e) {}
    throw new Error(msg);
  }
  return r.json();
}

/* ── toast ─────────────────────────────── */
function toast(msg, type = 'info') {
  const wrap = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  wrap.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 350); }, 3200);
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* close modal on backdrop click */
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal')) e.target.classList.remove('open');
});
