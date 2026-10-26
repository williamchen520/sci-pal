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
        currentSteps = steps;
        const link = protocol.url
            ? `<a href="${escapeHtml(protocol.url)}" target="_blank" rel="noreferrer">在 protocols.io 打开 ↗</a>`
            : '';
        detailEl.innerHTML = `
            <h2>${escapeHtml(protocol.title || protocol.protocol_id)}</h2>
            <div class="meta">
                ${escapeHtml(protocol.doi || '')}${protocol.version ? ` · v${escapeHtml(protocol.version)}` : ''}
                ${protocol.license ? ` · ${escapeHtml(protocol.license)}` : ''}
                · ${steps.length} 步 ${link ? ` · ${link}` : ''}
                · <a href="/api/protocols/${encodeURIComponent(protocol.protocol_id)}/export">导出 Markdown</a>
            </div>
            ${steps.map((step) => `
                <div class="step">
                    <h3>${step.ordinal}. ${escapeHtml(step.title || '(未命名步骤)')}</h3>
                    ${step.duration ? `<div><span class="tag">⏱ ${escapeHtml(step.duration)}</span></div>` : ''}
                    ${step.instructions ? `<p>${escapeHtml(step.instructions)}</p>` : ''}
                    ${(step.reagents || []).length ? `<p><span class="tag">试剂</span>${escapeHtml(step.reagents.join('、'))}</p>` : ''}
                </div>`).join('') || '<div class="empty">该协议没有解析出步骤</div>'}
            <div class="runs">
                <h3>实验记录</h3>
                <div class="run-form">
                    <input id="runTitle" placeholder="实验标题">
                    <input id="runOperator" placeholder="操作人">
                    <input id="runDate" type="date">
                    <select id="runStatus">
                        <option value="planned">计划</option>
                        <option value="running">进行中</option>
                        <option value="completed">完成</option>
                        <option value="failed">失败</option>
                    </select>
                    <input id="runResult" placeholder="结果 / 备注">
                    <button onclick="addRun('${escapeHtml(protocol.protocol_id)}')">添加记录</button>
                </div>
                <div id="runList"><div class="hint">加载中…</div></div>
            </div>`;
        await loadRuns(protocol.protocol_id);
    } catch (err) {
        detailEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

const RUN_LABELS = { planned: '计划', running: '进行中', completed: '完成', failed: '失败' };
let currentSteps = [];

async function loadRuns(protocolId) {
    const container = document.getElementById('runList');
    if (!container) return;
    try {
        const resp = await fetch(`/api/protocols/${encodeURIComponent(protocolId)}/runs`);
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        if (!body.runs.length) {
            container.innerHTML = '<div class="hint">还没有实验记录</div>';
            return;
        }
        container.innerHTML = body.runs.map((run) => {
            const done = run.done_steps || [];
            const checklist = currentSteps.length
                ? currentSteps.map((step) => `
                    <label class="run-step">
                        <input type="checkbox" data-run="${escapeHtml(run.run_id)}"
                               data-step="${escapeHtml(step.step_id)}"
                               ${done.includes(step.step_id) ? 'checked' : ''}>
                        ${step.ordinal}. ${escapeHtml(step.title || '')}
                    </label>`).join('')
                : '<span class="hint">该协议没有步骤</span>';
            return `
            <details class="run-item">
                <summary>
                    <span class="badge ${escapeHtml(run.status)}">${escapeHtml(RUN_LABELS[run.status] || run.status)}</span>
                    <strong>${escapeHtml(run.title || '(无标题)')}</strong>
                    <span class="hint">${escapeHtml(run.run_date || '')} · ${escapeHtml(run.operator || '')} · ${done.length}/${currentSteps.length} 步</span>
                </summary>
                ${run.result ? `<div class="hint">结果：${escapeHtml(run.result)}</div>` : ''}
                <div class="run-steps">${checklist}</div>
                <div class="run-files" id="files_${escapeHtml(run.run_id)}"></div>
                <label class="hint">附件
                    <input type="file" data-run="${escapeHtml(run.run_id)}" onchange="uploadAttachment(this)">
                </label>
            </details>`;
        }).join('');
        container.querySelectorAll('.run-step input').forEach((box) => {
            box.addEventListener('change', () => toggleStep(protocolId, box.dataset.run));
        });
        body.runs.forEach((run) => loadAttachments(run.run_id));
    } catch (err) {
        container.innerHTML = `<div class="hint bad">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

async function toggleStep(protocolId, runId) {
    const boxes = Array.from(
        document.querySelectorAll(`.run-step input[data-run="${runId}"]`)
    );
    const done = boxes.filter((box) => box.checked).map((box) => box.dataset.step);
    try {
        const resp = await fetch(`/api/experiments/${encodeURIComponent(runId)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ done_steps: done }),
        });
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        await loadRuns(protocolId);
    } catch (err) {
        setStatus(`更新进度失败：${err.message}`, 'bad');
    }
}

async function loadAttachments(runId) {
    const box = document.getElementById(`files_${runId}`);
    if (!box) return;
    try {
        const resp = await fetch(`/api/experiments/${encodeURIComponent(runId)}/attachments`);
        const body = await resp.json();
        if (!resp.ok || !body.ok) return;
        box.innerHTML = body.files.map((file) => {
            const sizeKb = Math.max(1, Math.round((file.size || 0) / 1024));
            return `<span class="file-item">
                <a href="/api/experiments/${encodeURIComponent(runId)}/attachments/${encodeURIComponent(file.file_id)}">${escapeHtml(file.filename)}</a>
                <span class="hint">${sizeKb} KB</span>
                <button class="link" onclick="deleteAttachment('${escapeHtml(runId)}','${escapeHtml(file.file_id)}')">删除</button>
            </span>`;
        }).join('') || '<span class="hint">暂无附件</span>';
    } catch (err) {
        box.innerHTML = `<span class="hint bad">附件加载失败：${escapeHtml(err.message)}</span>`;
    }
}

async function uploadAttachment(input) {
    const runId = input.dataset.run;
    const file = input.files[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
        const resp = await fetch(`/api/experiments/${encodeURIComponent(runId)}/attachments`, {
            method: 'POST',
            body: form,
        });
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        input.value = '';
        await loadAttachments(runId);
    } catch (err) {
        setStatus(`附件上传失败：${err.message}`, 'bad');
    }
}

async function deleteAttachment(runId, fileId) {
    try {
        const resp = await fetch(
            `/api/experiments/${encodeURIComponent(runId)}/attachments/${encodeURIComponent(fileId)}`,
            { method: 'DELETE' }
        );
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        await loadAttachments(runId);
    } catch (err) {
        setStatus(`附件删除失败：${err.message}`, 'bad');
    }
}

async function addRun(protocolId) {
    const title = document.getElementById('runTitle').value.trim();
    if (!title) {
        setStatus('实验标题不能为空', 'bad');
        return;
    }
    const payload = {
        title,
        operator: document.getElementById('runOperator').value.trim(),
        run_date: document.getElementById('runDate').value,
        status: document.getElementById('runStatus').value,
        result: document.getElementById('runResult').value.trim(),
    };
    try {
        const resp = await fetch(`/api/protocols/${encodeURIComponent(protocolId)}/runs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        document.getElementById('runTitle').value = '';
        document.getElementById('runResult').value = '';
        setStatus('实验记录已添加', 'ok');
        await loadRuns(protocolId);
    } catch (err) {
        setStatus(`添加失败：${err.message}`, 'bad');
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
