/** protocols.io 页面：已导入协议列表（搜索/分页） + 详情（步骤/试剂/时长）。 */
const listEl = document.getElementById('protocolList');
const detailEl = document.getElementById('protocolDetail');
const statusEl = document.getElementById('importStatus');
const importBtn = document.getElementById('importBtn');
const searchEl = document.getElementById('protocolSearch');
const loadMoreWrap = document.getElementById('loadMoreWrap');

const PAGE_SIZE = 20;
let offset = 0;
let total = 0;
let searchTimer = null;

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function setStatus(message, kind) {
    statusEl.textContent = message || '';
    statusEl.className = `hint${kind ? ' ' + kind : ''}`;
}

function formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function cardHtml(item) {
    return `
        <div class="card" data-id="${escapeHtml(item.protocol_id)}">
            <div class="card-title">${escapeHtml(item.title || item.protocol_id)}</div>
            <div class="card-meta">${item.steps} 步 · ${escapeHtml(item.doi || '无 DOI')} · ${escapeHtml(formatDate(item.fetched_at))}</div>
        </div>`;
}

function bindCards() {
    listEl.querySelectorAll('.card').forEach((card) => {
        card.addEventListener('click', () => loadDetail(card.dataset.id));
    });
}

async function loadList(reset) {
    if (reset) {
        offset = 0;
        listEl.innerHTML = '<div class="empty">加载中...</div>';
    }
    const query = searchEl.value.trim();
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) params.set('q', query);
    try {
        const resp = await fetch(`/api/protocols?${params.toString()}`);
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        total = body.total != null ? body.total : body.count;
        offset += body.protocols.length;
        if (offset === 0) {
            listEl.innerHTML = query
                ? '<div class="empty">没有匹配的协议</div>'
                : '<div class="empty">还没有导入协议<br>粘贴左侧链接开始</div>';
        } else if (reset) {
            listEl.innerHTML = body.protocols.map(cardHtml).join('');
        } else {
            listEl.insertAdjacentHTML('beforeend', body.protocols.map(cardHtml).join(''));
        }
        bindCards();
        loadMoreWrap.style.display = offset < total ? 'block' : 'none';
        if (!query && !offset) loadMoreWrap.style.display = 'none';
    } catch (err) {
        listEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadList(true), 250);
}

function loadMore() {
    loadList(false);
}

async function loadDetail(protocolId) {
    detailEl.innerHTML = '<div class="empty">加载中...</div>';
    try {
        const resp = await fetch(`/api/protocols/${encodeURIComponent(protocolId)}`);
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        const protocol = body.protocol;
        const steps = protocol.steps || [];
        const link = protocol.url
            ? `<a href="${escapeHtml(protocol.url)}" target="_blank" rel="noreferrer">在 protocols.io 打开 ↗</a>`
            : '';
        detailEl.innerHTML = `
            <h2>${escapeHtml(protocol.title || protocol.protocol_id)}</h2>
            <div class="meta">
                ${escapeHtml(protocol.doi || '')}${protocol.version ? ` · v${escapeHtml(protocol.version)}` : ''}
                ${protocol.license ? ` · ${escapeHtml(protocol.license)}` : ''}
                · ${steps.length} 步 ${link ? ` · ${link}` : ''}
            </div>
            ${steps.map((step) => `
                <div class="step">
                    <h3>${step.ordinal}. ${escapeHtml(step.title || '(未命名步骤)')}</h3>
                    ${step.duration ? `<div><span class="tag">⏱ ${escapeHtml(step.duration)}</span></div>` : ''}
                    ${step.instructions ? `<p>${escapeHtml(step.instructions)}</p>` : ''}
                    ${(step.reagents || []).length ? `<p><span class="tag">试剂</span>${escapeHtml(step.reagents.join('、'))}</p>` : ''}
                </div>`).join('') || '<div class="empty">该协议没有解析出步骤</div>'}`;
    } catch (err) {
        detailEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

async function importProtocol() {
    const input = document.getElementById('importId');
    const value = input.value.trim();
    if (!value) {
        setStatus('请先粘贴链接或 ID', 'bad');
        return;
    }
    importBtn.disabled = true;
    setStatus('导入中…（首次会请求 protocols.io）');
    try {
        const resp = await fetch('/api/protocols/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ protocol_id: value }),
        });
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        input.value = '';
        setStatus(`已导入：${body.steps} 步`, 'ok');
        await loadList(true);
        await loadDetail(body.protocol_id);
    } catch (err) {
        setStatus(`导入失败：${err.message}`, 'bad');
    } finally {
        importBtn.disabled = false;
    }
}

document.getElementById('importId').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') importProtocol();
});

loadList(true);
