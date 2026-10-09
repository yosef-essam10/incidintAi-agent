const $ = s => document.querySelector(s); let cur = null, chart = null, lastN = -1, lastSig = "";
const esc = t => String(t ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const api = (u, o) => fetch(u, o).then(r => r.json());
const post = (u, b) => api(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) });
const pick = id => { cur = id; lastN = -1; lastSig = ""; tick(); };
document.querySelectorAll(".sim button").forEach(b => b.onclick = async () => { const r = await post("/api/simulate", { scenario: b.dataset.s }); pick(r.id); });
async function list() {
  const d = await api("/api/incidents");
  $("#list").innerHTML = d.length ? d.map(i => `<button class="inc ${i.id === cur ? "on" : ""}" data-id="${i.id}"><b>${i.id}</b> ${i.service}<small>${esc(i.root_cause)}</small><span class="pill ${i.status}">${i.status.replace("_", " ")}</span></button>`).join("") : '<p class="empty">No incidents yet.</p>';
  document.querySelectorAll(".inc").forEach(b => b.onclick = () => pick(b.dataset.id));
}
async function detail() {
  if (!cur) return; const i = await api("/api/incidents/" + cur);
  const sig = JSON.stringify(i); if (sig === lastSig) return; lastSig = sig;
  const v = i.verification;
  $("#detail").innerHTML = `<div><h2>${i.id} &middot; ${i.service} <span class="pill ${i.status}">${i.status.replace("_", " ")}</span></h2><span class="empty">Severity: ${i.severity}</span></div>
  <div class="grid"><div><h4>Investigation timeline</h4><ul class="tl">${i.timeline.map(t => `<li>${esc(t.step)}<br><small>${esc(t.detail)}</small></li>`).join("")}</ul></div>
  <div><h4>Root cause</h4>${i.confidence ? `<div class="conf">${Math.round(i.confidence * 100)}%</div><b>${esc(i.root_cause)}</b><p>${esc(i.reasoning)}</p>` : '<p class="empty">Investigating...</p>'}<h4>Evidence</h4><ul>${i.evidence.map(e => `<li>${esc(e)}</li>`).join("")}</ul></div></div>
  ${i.action && i.status !== "resolved" ? `<div class="act"><h4>Recommendation</h4><b>${esc(i.action)}</b> &middot; risk: ${i.risk}${i.status === "awaiting_approval" ? '<div class="btns"><button class="ok" id="ap">Approve</button><button class="no" id="rj">Reject</button></div>' : ""}</div>` : ""}
  ${v ? `<div><h4>Verification ${v.passed ? "passed" : "failed"}</h4><div class="ba"><div>Before<br>Errors ${v.before.error_rate}%<br>Latency ${v.before.latency_ms}ms<br>Connections ${v.before.conn}</div><div><b>After<br>Errors ${v.after.error_rate}%<br>Latency ${v.after.latency_ms}ms<br>Connections ${v.after.conn}</b></div></div></div>` : ""}
  <div><h4>Latency and error rate</h4><canvas id="c" height="110"></canvas></div>`;
  if ($("#ap")) { $("#ap").onclick = () => post(`/api/incidents/${cur}/approve`).then(() => { lastSig = ""; tick(); }); $("#rj").onclick = () => post(`/api/incidents/${cur}/reject`).then(() => { lastSig = ""; tick(); }); }
  const s = i.series, C = "#f6ead7"; if (chart) chart.destroy();
  chart = new Chart($("#c"), { type: "line", data: { labels: s.map(x => x.t), datasets: [
    { label: "Latency ms", data: s.map(x => x.latency), borderColor: "#ff4d5a", tension: .3, pointRadius: 0 },
    { label: "Error %", data: s.map(x => x.errors), borderColor: "#3ddc97", yAxisID: "y1", tension: .3, pointRadius: 0 }] },
    options: { animation: false, plugins: { legend: { labels: { color: C } } }, scales: { x: { ticks: { color: C } }, y: { ticks: { color: C } }, y1: { position: "right", grid: { drawOnChartArea: false }, ticks: { color: C } } } } });
  if (i.chat.length !== lastN) { lastN = i.chat.length; $("#msgs").innerHTML = i.chat.map(m => `<div class="m ${m.role}">${esc(m.content)}</div>`).join(""); $("#msgs").scrollTop = 1e6; }
}
async function tick() { await list(); await detail(); }
async function send() {
  const q = $("#q").value.trim(); if (!q) return;
  if (!cur) { $("#msgs").insertAdjacentHTML("beforeend", '<div class="m agent">Select an incident first, then ask your question.</div>'); return; }
  $("#q").value = ""; $("#msgs").insertAdjacentHTML("beforeend", `<div class="m user">${esc(q)}</div><div class="m agent">Thinking...</div>`); $("#msgs").scrollTop = 1e6;
  await post(`/api/incidents/${cur}/chat`, { message: q }); lastN = -1; lastSig = ""; detail();
}
$("#send").onclick = send;
$("#q").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
tick(); setInterval(tick, 2000);