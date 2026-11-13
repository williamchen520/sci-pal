const errorBox = document.getElementById("error");

async function api(path) {
  const response = await fetch(path, { credentials: "same-origin" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `请求失败 (${response.status})`);
  return body;
}

function el(tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  return node;
}

function table(headers, rows) {
  const node = document.createElement("table");
  const head = document.createElement("tr");
  for (const header of headers) head.appendChild(el("th", header));
  node.appendChild(head);
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      if (cell instanceof Node) td.appendChild(cell);
      else td.textContent = cell ?? "";
      tr.appendChild(td);
    }
    node.appendChild(tr);
  }
  return node;
}

function runLink(multiRunId) {
  const link = el("a", multiRunId);
  link.href = `/evidence.html?multi_run_id=${encodeURIComponent(multiRunId)}`;
  return link;
}

async function load() {
  errorBox.textContent = "";
  try {
    const [adjudications, conflicts] = await Promise.all([
      api("/api/rag/audit/adjudications?limit=200"),
      api("/api/rag/audit/conflicts?limit=200"),
    ]);
    const aBox = document.getElementById("adjudications");
    const cBox = document.getElementById("conflicts");
    aBox.replaceChildren();
    cBox.replaceChildren();
    if (!adjudications.adjudications.length) aBox.appendChild(el("div", "empty", "还没有人工裁决。"));
    else
      aBox.appendChild(
        table(
          ["时间", "multi run", "query", "rag", "decision", "decided_by", "note"],
          adjudications.adjudications.map((item) => [
            item.created_at,
            runLink(item.multi_run_id),
            item.query,
            item.rag_id,
            item.decision,
            item.decided_by,
            item.note,
          ])
        )
      );
    if (!conflicts.conflicts.length) cBox.appendChild(el("div", "empty", "还没有冲突标记。"));
    else
      cBox.appendChild(
        table(
          ["时间", "multi run", "query", "rag", "flagged_by", "note"],
          conflicts.conflicts.map((item) => [
            item.created_at,
            runLink(item.multi_run_id),
            item.query,
            item.rag_id,
            item.flagged_by,
            item.note,
          ])
        )
      );
  } catch (error) {
    if (String(error.message).includes("401")) {
      window.location.replace("/login.html");
      return;
    }
    errorBox.textContent = error.message;
  }
}

load();
