/* 对话管理（localStorage 持久化）+ 模型切换 + 上下文记忆 + 数据计算提示 */
const STORAGE_KEY = 'obsidian_kb_chats';
let chats = [];
let currentChatId = null;

const chatBody = document.getElementById('chatBody');
const chatList = document.getElementById('chatList');
const emptyState = document.getElementById('emptyState');
const inputBox = document.getElementById('inputBox');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const modelSelect = document.getElementById('modelSelect');
const noteModal = document.getElementById('noteModal');
const noteTitle = document.getElementById('noteTitle');
const noteContent = document.getElementById('noteContent');
const noteClose = document.getElementById('noteClose');

// ---- 模型选择持久化 ----
const MODEL_KEY = 'obsidian_kb_model';
const savedModel = localStorage.getItem(MODEL_KEY) || 'auto';
modelSelect.value = savedModel;
modelSelect.addEventListener('change', () => {
  localStorage.setItem(MODEL_KEY, modelSelect.value);
});

// ---- 加载/保存对话 ----
function loadChats() {
  try { chats = JSON.parse(localStorage.getItem(STORAGE_KEY)) || []; }
  catch { chats = []; }
}
function saveChats() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

// ---- 知识库统计 ----
async function loadKbStats() {
  try {
    const res = await fetch('/stats');
    const d = await res.json();
    document.getElementById('statNotes').textContent = d.notes ?? '-';
    document.getElementById('statChunks').textContent = d.chunks ?? '-';
    document.getElementById('kbStatsLine').textContent = `${d.notes} 篇笔记 · ${d.chunks} 个分块 · 云端${(d.chain||[]).length}级+本地兜底`;
    const mini = document.getElementById('kbStatsMini');
    if (mini) mini.textContent = `${d.notes} 笔记 · ${d.chunks} 分块`;
    // 最近更新时间（首页显示 + 超时警示）
    const lu = document.getElementById('kbLastUpdate');
    if (lu && d.last_update) {
      const t = d.last_update.time;
      const ts = d.last_update.ts || 0;
      const hours = (Date.now() / 1000 - ts) / 3600;
      if (!ts) {
        lu.textContent = '最近更新：未知';
      } else if (hours > 72) {
        lu.textContent = `最近更新：${t}（已 ${Math.round(hours / 24)} 天未更新 ⚠️）`;
        lu.classList.add('stale');
      } else if (hours > 48) {
        lu.textContent = `最近更新：${t}（已 ${Math.round(hours / 24)} 天未更新）`;
        lu.classList.add('stale');
      } else {
        lu.textContent = `最近更新：${t}`;
        lu.classList.remove('stale');
      }
    }
    return d;
  } catch (e) {
    document.getElementById('kbStatsLine').textContent = '知识库服务未连接';
    return null;
  }
}

// ---- 渲染对话列表（桌面侧栏 + 移动端抽屉）----
function renderChatList() {
  chatList.innerHTML = '';
  const drawerList = document.getElementById('drawerChatList');
  if (drawerList) drawerList.innerHTML = '';
  chats.forEach(c => {
    const item = createChatItem(c);
    chatList.appendChild(item);
    if (drawerList) {
      const dup = createChatItem(c);
      dup.classList.add('drawer-item');
      drawerList.appendChild(dup);
    }
  });
}

function createChatItem(c) {
  const item = document.createElement('div');
  item.className = 'chat-item' + (c.id === currentChatId ? ' active' : '');
  const t = c.title || '新对话';
  item.innerHTML = `<span class="title">${escapeHtml(t)}</span><button class="del" data-id="${c.id}">×</button>`;
  item.addEventListener('click', e => {
    if (e.target.classList.contains('del')) return;
    switchChat(c.id, true);
  });
  item.querySelector('.del').addEventListener('click', e => {
    e.stopPropagation();
    deleteChat(c.id);
  });
  return item;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ---- 切换/新建/删除对话 ----
function switchChat(id, closeDrawer = false) {
  currentChatId = id;
  renderChat();
  renderChatList();
  if (closeDrawer) closeDrawerFn();
}

function openDrawer() {
  const mask = document.getElementById('drawerMask');
  const drawer = document.getElementById('mobileDrawer');
  if (!mask || !drawer) return;
  mask.hidden = false;
  drawer.classList.add('open');
}
function closeDrawerFn() {
  const mask = document.getElementById('drawerMask');
  const drawer = document.getElementById('mobileDrawer');
  if (!mask || !drawer) return;
  mask.hidden = true;
  drawer.classList.remove('open');
}

function newChat() {
  currentChatId = null;
  chatBody.innerHTML = '';
  emptyState.hidden = false;
  renderChatList();
  loadKbStats();   // 刷新统计卡片
  closeDrawerFn(); // 关闭抽屉
  inputBox.focus();
}

function deleteChat(id) {
  chats = chats.filter(c => c.id !== id);
  saveChats();
  if (currentChatId === id) newChat();
  else renderChatList();
}

function ensureCurrentChat(firstMsg) {
  if (!currentChatId) {
    const chat = {
      id: Date.now() + Math.random(),
      title: firstMsg.slice(0, 24) + (firstMsg.length > 24 ? '…' : ''),
      messages: [],
    };
    chats.unshift(chat);
    currentChatId = chat.id;
    saveChats();
    emptyState.hidden = true;
  }
  return chats.find(c => c.id === currentChatId);
}

function renderChat() {
  chatBody.innerHTML = '';
  emptyState.hidden = true;
  const chat = chats.find(c => c.id === currentChatId);
  if (!chat) { emptyState.hidden = false; return; }
  chat.messages.forEach(m => {
    if (m.role === 'user') {
      const el = document.createElement('div');
      el.className = 'msg user';
      el.innerHTML = `<div class="bubble">${escapeHtml(m.text)}</div>`;
      chatBody.appendChild(el);
    } else {
      chatBody.appendChild(renderBotMsg(m));
    }
  });
  chatBody.scrollTop = chatBody.scrollHeight;
}

function renderBotMsg(m) {
  const el = document.createElement('div');
  el.className = 'msg bot';
  const provider = m.provider ? `<span class="provider">${escapeHtml(m.provider)}</span>` : '';
  let calcTag = '';
  if (m.calc) calcTag = '<span class="provider" style="color:#7ee787">🧮 已计算</span>';
  let sources = '';
  if (m.sources && m.sources.length) {
    sources = `<div class="sources-wrap">
      <button class="sources-toggle" title="查看来源">📚 ${m.sources.length} 条来源 <span class="chev">▸</span></button>
      <div class="sources" hidden>${m.sources.map(s =>
        `<div class="source-card" data-source="${escapeHtml(s)}">📄 ${escapeHtml(s.split(/[\\/]/).pop())}</div>`
      ).join('')}</div>
    </div>`;
  }
  el.innerHTML = `
    <div class="meta">${provider}${calcTag}${m.modelLabel ? `<span>${escapeHtml(m.modelLabel)}</span>` : ''}</div>
    <div class="content">${formatContent(m.text)}</div>
    ${sources}
  `;
  el.querySelectorAll('.sources-toggle').forEach(t => {
    t.addEventListener('click', () => {
      const list = t.nextElementSibling;
      const isHidden = !list.hasAttribute('hidden');
      list.hidden = isHidden;
      t.querySelector('.chev').textContent = isHidden ? '▸' : '▾';
    });
  });
  el.querySelectorAll('.source-card').forEach(card => {
    card.addEventListener('click', () => openNote(card.dataset.source));
  });
  return el;
}

// ---- Markdown 简单格式化 ----
function formatContent(text) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--bg-input);padding:1px 5px;border-radius:3px;font-size:13px">$1</code>')
    .replace(/^##?\s+(.+)$/gm, '<strong style="display:block;margin:8px 0 4px">$1</strong>')
    .replace(/\n/g, '<br>');
}

// ---- 发送消息（带上下文记忆）----
async function sendMessage(text) {
  text = text.trim();
  if (!text) return;

  const chat = ensureCurrentChat(text);
  chat.messages.push({ role: 'user', text });
  saveChats();
  renderChat();
  renderChatList();

  // loading
  const loading = document.createElement('div');
  loading.className = 'msg bot';
  loading.id = 'loadingMsg';
  loading.innerHTML = `<div class="loading">思考中<span class="dot"></span><span class="dot"></span><span class="dot"></span></div>`;
  chatBody.appendChild(loading);
  chatBody.scrollTop = chatBody.scrollHeight;
  sendBtn.disabled = true;

  try {
    const model = modelSelect.value;
    // 携带历史对话（最近 6 轮），让 AI 结合上下文回答
    const history = chat.messages.slice(-12, -1).map(m => ({
      role: m.role,
      content: typeof m.text === 'string' ? m.text : '',
    }));
    const res = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: text,
        local: model === 'qwen3.5:9b',
        model: model,
        history: history,
      }),
    });
    const data = await res.json();
    loading.remove();
    if (res.status !== 200) throw new Error(data.detail || `HTTP ${res.status}`);

    const modelLabel = modelSelect.options[modelSelect.selectedIndex].text;
    chat.messages.push({
      role: 'assistant',
      text: data.answer || '（无回答）',
      sources: data.sources || [],
      provider: data.provider || '',
      modelLabel: modelLabel,
      calc: !!data.calc,
    });
    saveChats();
    renderChat();
  } catch (e) {
    loading.remove();
    chat.messages.push({
      role: 'assistant',
      text: `请求失败：${e.message}\n\n请检查服务是否正常运行。`,
    });
    saveChats();
    renderChat();
  } finally {
    sendBtn.disabled = false;
  }
}

// ---- 输入框 ----
inputBox.addEventListener('input', () => {
  inputBox.style.height = 'auto';
  inputBox.style.height = Math.min(inputBox.scrollHeight, 160) + 'px';
});
inputBox.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(inputBox.value);
    inputBox.value = '';
    inputBox.style.height = 'auto';
  }
});
sendBtn.addEventListener('click', () => {
  sendMessage(inputBox.value);
  inputBox.value = '';
  inputBox.style.height = 'auto';
});
newChatBtn.addEventListener('click', newChat);
const mobileNewBtn = document.getElementById('mobileNewBtn');
if (mobileNewBtn) mobileNewBtn.addEventListener('click', newChat);
// 移动端抽屉开关
const menuBtn = document.getElementById('menuBtn');
if (menuBtn) menuBtn.addEventListener('click', openDrawer);
const drawerMask = document.getElementById('drawerMask');
if (drawerMask) drawerMask.addEventListener('click', closeDrawerFn);
const drawerClose = document.getElementById('drawerClose');
if (drawerClose) drawerClose.addEventListener('click', closeDrawerFn);
const drawerNewBtn = document.getElementById('drawerNewBtn');
if (drawerNewBtn) drawerNewBtn.addEventListener('click', newChat);

// ---- 提示词标签 ----
document.querySelectorAll('.tag').forEach(tag => {
  tag.addEventListener('click', () => {
    inputBox.value = tag.textContent;
    inputBox.focus();
  });
});

// ---- 笔记弹窗 ----
async function openNote(source) {
  try {
    const res = await fetch('/note?source=' + encodeURIComponent(source));
    const data = await res.json();
    noteTitle.textContent = source.split(/[\\/]/).pop();
    noteContent.textContent = data.content;
    noteModal.hidden = false;
  } catch (e) {
    alert('打开笔记失败：' + e.message);
  }
}
noteClose.addEventListener('click', () => { noteModal.hidden = true; });
noteModal.addEventListener('click', e => {
  if (e.target === noteModal) noteModal.hidden = true;
});

// ---- 初始化 ----
loadChats();
loadKbStats();
renderChatList();
if (chats.length > 0 && !currentChatId) {
  switchChat(chats[0].id);
} else {
  emptyState.hidden = false;
}