// Calls Supabase's REST API directly — no backend server needed.
// The key below is the "publishable" (anon) key: safe to expose client-side,
// access is gated by Supabase Row Level Security policies, not by secrecy.
const SUPABASE_URL = 'https://gawyuzgbaubpszajsfdj.supabase.co';
const SUPABASE_KEY = 'sb_publishable_8CNYSi1HttCYCmOhJpJFQA_G7s4zTcM';
const SUPABASE_HEADERS = { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` };

const SOURCE_COLORS = {
  'devpost':'#6EE7B7','lablab.ai':'#60A5FA',
  'mlh':'#F472B6','dorahacks':'#FB923C',
  'google developers':'#FB923C','kaggle':'#67E8F9',
};

function getColor(source) {
  return SOURCE_COLORS[(source||'').toLowerCase()] || '#6EE7B7';
}

// Mock data — shown when backend not yet connected
const MOCK_DATA = [
  {source:'lablab.ai',title:'AMD AI Developer Hackathon',description:'Build real AI systems on AMD hardware. $10k + AMD GPU.',deadline:'2026-05-10',prize:'$10,000 + GPU',status:'open',url:'https://lablab.ai/event'},
  {source:'lablab.ai',title:'Enterprise AI Agents Hackathon',description:'Build the next intelligent enterprise solution using agentic AI.',deadline:'2026-05-19',prize:'See event',status:'open',url:'https://lablab.ai/event'},
  {source:'Devpost',title:'AI Innovation Challenge 2026',description:'Build next-gen AI-powered applications worldwide.',deadline:'2026-06-15',prize:'$25,000',status:'open',url:'https://devpost.com/hackathons'},
  {source:'Devpost',title:'Web3 Blockchain Hackathon',description:'Build the decentralized future. Smart contracts and dApps.',deadline:'2026-08-01',prize:'$50,000',status:'upcoming',url:'https://devpost.com/hackathons'},
  {source:'MLH',title:'HackMIT 2026',description:'MIT annual hackathon. 1000+ hackers, 36 hours.',deadline:'2026-09-15',prize:'MLH prizes',status:'upcoming',url:'https://mlh.io'},
  {source:'MLH',title:'HackHarvard 2026',description:'Harvard hackathon open to all college students.',deadline:'2026-10-12',prize:'MLH prizes',status:'upcoming',url:'https://mlh.io'},
  {source:'DoraHacks',title:'Solana Renaissance Hackathon',description:'4 weeks to ship a Web3 product or AI agent on Solana.',deadline:'2026-06-01',prize:'$50,000 USDC',status:'open',url:'https://dorahacks.io'},
  {source:'Google Developers',title:'GDSC Solution Challenge 2026',description:'Solve real-world UN SDG problems using Google tech.',deadline:'April 2026',prize:'Trip to Google HQ',status:'open',url:'https://developers.google.com'},
  {source:'Google Developers',title:'Google Code Jam 2026',description:'Algorithmic programming competition by Google.',deadline:'TBD',prize:'$15,000',status:'open',url:'https://codingcompetitions.withgoogle.com'},
  {source:'lablab.ai',title:'AI Genesis — Dubai 2026',description:'Global hybrid hackathon. Online build phase, live finale in Dubai.',deadline:'2026-11-03',prize:'See event',status:'upcoming',url:'https://lablab.ai'},
];

// State
let state = {
  hackathons: [],
  saved: JSON.parse(localStorage.getItem('ht_saved')||'[]'),
  activeTab: 'feed',
  activeFilter: 'all',
  search: '',
  toggles: JSON.parse(localStorage.getItem('ht_toggles')||'null') || {
    'lablab.ai':true,'Devpost':true,
    'MLH':true,'DoraHacks':true,'Google Developers':true,'Kaggle':true
  },
};

// Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js').catch(e => console.log('[SW]', e));
}

// PWA install
let installPromptEvent = null;
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); installPromptEvent = e;
  if (window.innerWidth < 768) setTimeout(() => document.getElementById('installPrompt').classList.add('show'), 3000);
});
window.addEventListener('appinstalled', () => {
  document.getElementById('installPrompt').classList.remove('show');
  installPromptEvent = null;
});
function triggerInstall() {
  if (installPromptEvent) {
    installPromptEvent.prompt();
    installPromptEvent.userChoice.then(c => {
      if (c.outcome === 'accepted') document.getElementById('installPrompt').classList.remove('show');
    });
  }
}

// Push notifications
async function requestNotificationPermission() {
  if (!('Notification' in window)) { alert('Notifications not supported.'); return; }
  const perm = await Notification.requestPermission();
  const status = document.getElementById('notifStatus');
  if (perm === 'granted') {
    status.textContent = 'Push notifications enabled!';
    status.style.color = 'var(--green)';
  } else {
    status.textContent = 'Permission denied.';
  }
}

// Data
async function fetchHackathons() {
  try {
    const params = new URLSearchParams({
      select: 'source,title,url,deadline,prize,thumbnail,description,status,first_seen',
      order: 'first_seen.desc',
      limit: '2000',
    });
    const res = await fetch(`${SUPABASE_URL}/rest/v1/hackathons?${params}`, {
      headers: SUPABASE_HEADERS, signal: AbortSignal.timeout(8000)
    });
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (data.length > 0) return data;
    throw new Error('empty');
  } catch {
    console.log('[Supabase] Using mock data');
    return MOCK_DATA;
  }
}

async function subscribeEmail(email) {
  try {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/subscribers`, {
      method: 'POST',
      headers: { ...SUPABASE_HEADERS, 'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates' },
      body: JSON.stringify({ email })
    });
    return res.ok;
  } catch { return false; }
}

// Helpers
function daysLeft(deadline) {
  if (!deadline || deadline === 'TBD') return null;
  const d = new Date(deadline);
  if (isNaN(d)) return null;
  const diff = Math.ceil((d - Date.now()) / 86400000);
  if (diff < 0)  return { text:'Ended',     cls:'urgency-ended' };
  if (diff === 0) return { text:'Last day!', cls:'urgency-hot' };
  if (diff <= 7)  return { text:`${diff}d left`, cls:'urgency-hot' };
  return { text:`${diff}d left`, cls:'urgency-cool' };
}

function isSaved(url) { return state.saved.some(h => h.url === url); }

function toggleSave(hackathon) {
  if (isSaved(hackathon.url)) {
    state.saved = state.saved.filter(h => h.url !== hackathon.url);
  } else {
    state.saved = [hackathon, ...state.saved];
  }
  localStorage.setItem('ht_saved', JSON.stringify(state.saved));
  renderAll();
}

function getFiltered() {
  return state.hackathons.filter(h => {
    if (state.activeFilter !== 'all') {
      const src = (h.source||'').toLowerCase().replace(/[\s.]/g,'');
      const f = state.activeFilter;
      if (!src.includes(f) && !f.includes(src.slice(0,4))) return false;
    }
    if (state.search) {
      const q = state.search.toLowerCase();
      if (!`${h.title} ${h.description||''} ${h.source}`.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}

// Render
let _forSave = [];

function cardHTML(h, i = 0) {
  const color = getColor(h.source);
  const saved = isSaved(h.url);
  const urg = daysLeft(h.deadline);
  const urgHTML = urg ? `<span class="urgency-tag ${urg.cls}">${urg.text}</span>` : '';
  return `<div class="card" style="animation-delay:${Math.min(i*40,400)}ms" onclick="openHack('${encodeURIComponent(h.url)}')">
    <div class="card-top">
      <span class="source-badge" style="color:${color};border-color:${color}">${(h.source||'').toUpperCase()}</span>
      <div class="card-actions">
        ${urgHTML}
        <button class="save-btn ${saved?'saved':''}" onclick="event.stopPropagation();doSave(${i})" title="${saved?'Unsave':'Save'}">
          ${saved?'★':'☆'}
        </button>
      </div>
    </div>
    <div class="card-title">${h.title||''}</div>
    ${h.description?`<div class="card-desc">${h.description}</div>`:''}
    <div class="card-footer">
      <div class="meta-block"><div class="meta-label">DEADLINE</div><div class="meta-value">${h.deadline||'TBD'}</div></div>
      ${h.prize&&h.prize!=='N/A'&&h.prize!=='See article'?`<div class="meta-block"><div class="meta-label">PRIZE</div><div class="meta-value prize">${h.prize}</div></div>`:''}
      <a class="open-link" href="${h.url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">OPEN →</a>
    </div>
  </div>`;
}

function skeletons() {
  return Array(6).fill(0).map(()=>`<div class="skeleton-card">
    <div style="display:flex;justify-content:space-between;margin-bottom:6px">
      <div class="skeleton-line" style="width:70px;height:16px"></div>
      <div class="skeleton-line" style="width:50px;height:16px"></div>
    </div>
    <div class="skeleton-line" style="width:90%"></div>
    <div class="skeleton-line"></div>
    <div class="skeleton-line" style="width:75%"></div>
  </div>`).join('');
}

function renderFeed() {
  const filtered = getFiltered();
  _forSave = filtered;
  const grid = document.getElementById('feedGrid');
  document.getElementById('feedCount').textContent =
    `${filtered.length} hackathon${filtered.length!==1?'s':''} · updated just now`;
  grid.innerHTML = filtered.length
    ? filtered.map((h,i)=>cardHTML(h,i)).join('')
    : `<div class="empty"><div class="empty-icon">◈</div><div class="empty-title">No hackathons found</div><div class="empty-sub">${state.search?'Try a different search term':'Pull to refresh or check back later'}</div></div>`;
}

function renderSaved() {
  _forSave = state.saved;
  const grid = document.getElementById('savedGrid');
  document.getElementById('savedCount').textContent = `${state.saved.length} item${state.saved.length!==1?'s':''}`;
  document.getElementById('savedNavCount').textContent = state.saved.length || '';
  grid.innerHTML = state.saved.length
    ? state.saved.map((h,i)=>cardHTML(h,i)).join('')
    : `<div class="empty"><div class="empty-icon">☆</div><div class="empty-title">Nothing saved yet</div><div class="empty-sub">Tap the star on any hackathon to bookmark it here</div></div>`;
}

function renderStatsBar() {
  const counts = {};
  state.hackathons.forEach(h => { counts[h.source] = (counts[h.source]||0)+1; });
  document.getElementById('statsBar').innerHTML = Object.entries(counts)
    .map(([src,n])=>`<div class="stat-chip"><div class="stat-dot" style="background:${getColor(src)}"></div><span class="stat-text">${src} · ${n}</span></div>`)
    .join('');
}

function renderSidebarFilters() {
  const FILTERS = [
    {label:'All',val:'all',color:'#6EE7B7'},
    {label:'lablab.ai',val:'lablab',color:'#60A5FA'},
    {label:'Devpost',val:'devpost',color:'#6EE7B7'},
    {label:'MLH',val:'mlh',color:'#F472B6'},
    {label:'DoraHacks',val:'dora',color:'#FB923C'},
    {label:'Google Dev',val:'google',color:'#FB923C'},
    {label:'Kaggle',val:'kaggle',color:'#67E8F9'},
  ];
  const counts = {};
  state.hackathons.forEach(h => {
    const src = (h.source||'').toLowerCase();
    FILTERS.forEach(f => {
      if (f.val!=='all' && (src.includes(f.val.slice(0,4))||f.val.includes(src.slice(0,4)))) counts[f.val]=(counts[f.val]||0)+1;
    });
    counts.all = (counts.all||0)+1;
  });
  document.getElementById('sidebarFilters').innerHTML = FILTERS.map(f=>`
    <div class="filter-item${state.activeFilter===f.val?' active':''}" onclick="setFilter('${f.val}')"
      style="${state.activeFilter===f.val?`color:${f.color}`:''}">
      <div class="filter-dot" style="background:${f.color}"></div>
      ${f.label}<span class="filter-count">${counts[f.val]||0}</span>
    </div>`).join('');
}

function renderSettings() {
  const SRCS = [
    {label:'lablab.ai',color:'#60A5FA'},{label:'Devpost',color:'#6EE7B7'},
    {label:'MLH',color:'#F472B6'},{label:'DoraHacks',color:'#FB923C'},
    {label:'Google Developers',color:'#FB923C'},{label:'Kaggle',color:'#67E8F9'},
  ];
  document.getElementById('sourceToggles').innerHTML = SRCS.map((s,i)=>`
    <div class="toggle-row">
      <div class="toggle-left"><div class="toggle-dot" style="background:${s.color}"></div><span class="toggle-name">${s.label}</span></div>
      <button class="toggle${state.toggles[s.label]!==false?' on':''}" id="tgl-${i}"
        style="background:${state.toggles[s.label]!==false?s.color+'55':'var(--border)'}"
        onclick="flipToggle('${s.label}',${i},'${s.color}')"></button>
    </div>`).join('');
}

function renderAll() {
  renderFeed(); renderSaved(); renderStatsBar(); renderSidebarFilters();
}

// Interactions
function doSave(idx) { const h = _forSave[idx]; if (h) toggleSave(h); }
function openHack(enc) { window.open(decodeURIComponent(enc),'_blank','noopener'); }

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab,.nav-item').forEach(t => t.classList.remove('active'));
  document.getElementById(`page-${tab}`).classList.add('active');
  document.getElementById(`tab-${tab}`).classList.add('active');
  const snav = document.getElementById(`snav-${tab}`);
  if (snav) snav.classList.add('active');
  if (tab==='settings') renderSettings();
  if (tab==='saved') renderSaved();
}

function setFilter(val) {
  state.activeFilter = val;
  document.querySelectorAll('.pill').forEach(p => { p.classList.remove('active'); p.style=''; });
  const pill = document.querySelector(`.pill[data-filter="${val}"]`);
  if (pill) { pill.classList.add('active'); }
  renderSidebarFilters(); renderFeed();
}

function handleSearch(val) {
  state.search = val;
  document.getElementById('searchClear').style.display = val ? 'block' : 'none';
  renderFeed();
}

function clearSearch() {
  state.search = '';
  document.getElementById('searchInput').value = '';
  document.getElementById('searchClear').style.display = 'none';
  renderFeed();
}

function flipToggle(label, idx, color) {
  state.toggles[label] = !state.toggles[label];
  localStorage.setItem('ht_toggles', JSON.stringify(state.toggles));
  const btn = document.getElementById(`tgl-${idx}`);
  btn.classList.toggle('on', state.toggles[label]);
  btn.style.background = state.toggles[label] ? color+'55' : 'var(--border)';
}

async function handleSubscribe() {
  const email = document.getElementById('emailInput').value.trim();
  if (!email||!email.includes('@')) {
    document.getElementById('emailInput').style.borderColor='var(--pink)'; return;
  }
  const btn = document.getElementById('subBtn');
  btn.textContent='Subscribing...'; btn.disabled=true;
  const ok = await subscribeEmail(email);
  document.getElementById('emailArea').innerHTML = `<div class="success-box">
    <span style="font-size:16px">✓</span>
    ${ok ? `Subscribed! You'll get notified at ${email}` : 'Could not subscribe — check backend connection'}
  </div>`;
}

// Init
async function init() {
  document.getElementById('feedGrid').innerHTML = skeletons();
  state.hackathons = await fetchHackathons();
  renderAll();
}

document.addEventListener('DOMContentLoaded', init);
