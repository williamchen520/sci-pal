/** protocols.io 页面：已导入协议列表 + 详情（步骤/试剂/时长）。 */
const listEl = document.getElementById('protocolList');
const detailEl = document.getElementById('protocolDetail');

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function loadList() {
    try {
        const resp = await fetch('/api/protocols?limit=50');
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        if (!body.protocols.length) {
            listEl.innerHTML = '<div class="empty">还没有导入协议</div>';
            return;
        }
        listEl.innerHTML = body.protocols.map((item) => `
            <div class="card" data-id="${escapeHtml(item.protocol_id)}">
                <div class="card-title">${escapeHtml(item.title || item.protocol_id)}</div>
                <div class="card-meta">${item.steps} 步 · ${escapeHtml(item.version || '')} · ${escapeHtml(item.doi || '')}</div>
            </div>`).join('');
        listEl.querySelectorAll('.card').forEach((card) => {
            card.addEventListener('click', () => loadDetail(card.dataset.id));
        });
    } catch (err) {
        listEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

async function loadDetail(protocolId) {
    detailEl.innerHTML = '<div class="empty">加载中...</div>';
    try {
        const resp = await fetch(`/api/protocols/${encodeURIComponent(protocolId)}`);
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        const protocol = body.protocol;
        const steps = protocol.steps || [];
        detailEl.innerHTML = `
            <h2>${escapeHtml(protocol.title || protocol.protocol_id)}</h2>
            <div class="meta">${escapeHtml(protocol.doi || '')} · v${escapeHtml(protocol.version || '?')} · ${escapeHtml(protocol.license || '')}</div>
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
    if (!value) return;
    detailEl.innerHTML = '<div class="empty">导入中...</div>';
    try {
        const resp = await fetch('/api/protocols/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ protocol_id: value }),
        });
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        input.value = '';
        await loadList();
        await loadDetail(body.protocol_id);
    } catch (err) {
        detailEl.innerHTML = `<div class="empty error">导入失败：${escapeHtml(err.message)}</div>`;
    }
}

loadList();
