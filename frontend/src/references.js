/** 文献库页面：RIS / EndNote XML 导入 + 列表。 */
const itemsEl = document.getElementById('items');
const headEl = document.getElementById('listHead');
const statusEl = document.getElementById('status');

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function setStatus(message, kind) {
    statusEl.textContent = message || '';
    statusEl.className = `hint${kind ? ' ' + kind : ''}`;
}

async function loadList() {
    try {
        const resp = await fetch('/api/references?limit=200');
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        headEl.textContent = `共 ${body.count} 条`;
        if (!body.references.length) {
            itemsEl.innerHTML = '<div class="empty">还没有导入文献</div>';
            return;
        }
        itemsEl.innerHTML = body.references.map((ref) => `
            <div class="item">
                <div class="item-title">${escapeHtml(ref.title || '(无标题)')}</div>
                <div class="item-meta">${escapeHtml(ref.authors || '')}${ref.journal ? ` · ${escapeHtml(ref.journal)}` : ''}${ref.year ? ` · ${escapeHtml(ref.year)}` : ''}${ref.doi ? ` · ${escapeHtml(ref.doi)}` : ''}</div>
            </div>`).join('');
    } catch (err) {
        itemsEl.innerHTML = `<div class="empty">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

async function post(body) {
    const resp = await fetch('/api/references/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || `HTTP ${resp.status}`);
    return data;
}

async function importFile() {
    const file = document.getElementById('risFile').files[0];
    if (!file) {
        setStatus('先选择一个 .ris / .xml 文件', 'bad');
        return;
    }
    const button = document.getElementById('uploadBtn');
    button.disabled = true;
    setStatus('导入中…');
    try {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch('/api/references/import', { method: 'POST', body: form });
        const data = await resp.json();
        if (!resp.ok || !data.ok) throw new Error(data.error || `HTTP ${resp.status}`);
        setStatus(`已导入 ${data.added} 条，跳过 ${data.skipped} 条（${data.format}）`, 'ok');
        await loadList();
    } catch (err) {
        setStatus(`导入失败：${err.message}`, 'bad');
    } finally {
        button.disabled = false;
    }
}

async function importText() {
    const text = document.getElementById('pasteBox').value;
    if (!text.trim()) {
        setStatus('先粘贴 RIS 内容', 'bad');
        return;
    }
    const button = document.getElementById('pasteBtn');
    button.disabled = true;
    setStatus('导入中…');
    try {
        const data = await post({ content: text });
        setStatus(`已导入 ${data.added} 条，跳过 ${data.skipped} 条（${data.format}）`, 'ok');
        document.getElementById('pasteBox').value = '';
        await loadList();
    } catch (err) {
        setStatus(`导入失败：${err.message}`, 'bad');
    } finally {
        button.disabled = false;
    }
}

loadList();
