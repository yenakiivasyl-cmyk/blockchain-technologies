"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const uah = (n) => Math.round(n).toLocaleString("uk-UA").replace(/,/g, " ") + " ₴";
const short = (h, n = 10) => (h && h.length > n + 6 ? `${h.slice(0, n)}…${h.slice(-4)}` : h || "—");
const time = (t) => new Date(t * 1000).toLocaleTimeString("uk-UA");
const TYPE_UA = { REGISTER: "Реєстрація", CAMPAIGN: "Збір", DONATION: "Донат", PURCHASE: "Закупівля", SHIPMENT: "Відвантаження", RECEIPT: "Отримання" };

let S = null;
let viewing = null;
let selectedBlock = null;
let selectedActor = null;
let lastHeight = {};
const openAttack = new Set();

function hashHtml(h, n = 20) {
  const zeros = (h.match(/^0*/) || [""])[0].length;
  const shown = h.slice(0, n);
  return `<span class="zeros">${shown.slice(0, zeros)}</span>${shown.slice(zeros)}…`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.className = "toast"), 4200);
}

async function load(rerenderForms = false) {
  S = await api("/api/state" + (viewing ? `?node=${viewing}` : ""));
  viewing = S.viewing;
  render(rerenderForms);
}

async function act(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg);
    await load(true);
  } catch (e) {
    toast(e.message, true);
  }
}

// ─────────────────────────── рендеринг ───────────────────────────

function render(rerenderForms) {
  $("#techChips").innerHTML = ["SHA-256", "Ed25519", "Merkle tree", `PoW · ${S.difficulty} нулі`, "Nakamoto consensus"]
    .map((c) => `<span class="chip">${c}</span>`).join("");
  renderStats();
  renderNodes();
  renderChain();
  renderDetail();
  renderCampaigns();
  renderMempool();
  renderActorSelect(rerenderForms);
  renderDonationSelect();
  renderLog();
}

function renderStats() {
  const s = S.stats;
  $("#stats").innerHTML = [
    ["Зібрано", uah(s.raised), "accent"], ["Витрачено на закупівлі", uah(s.spent)], ["Доставлено й підтверджено", uah(s.delivered)],
    ["Блоків", s.blocks], ["Транзакцій", s.txs], ["Учасників", s.actors],
  ].map(([l, v, c]) => `<div class="stat ${c || ""}"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("");
}

function renderNodes() {
  $("#nodes").innerHTML = S.nodes.map((n) => {
    const cls = [n.id === viewing && "viewing", !n.valid && "invalid", !n.online && "offline"].filter(Boolean).join(" ");
    const dot = !n.valid ? "bad" : !n.online ? "off" : "";
    const status = !n.valid ? `ПОШКОДЖЕНО з блоку #${n.first_bad}` : n.online ? "онлайн · синхронізовано" : "офлайн";
    const blocks = Array.from({ length: n.height }, (_, i) => `<option>${i + 1}</option>`).join("");
    return `
      <div class="node ${cls}" data-node="${n.id}">
        <div class="top"><span class="dot ${dot}"></span><span class="title">${esc(n.name)}</span>
          <span class="status ${n.valid ? "" : "bad"}">${status}</span></div>
        <dl>
          <dt>Висота</dt><dd>#${n.height}</dd>
          <dt>Вершина</dt><dd class="mono">${hashHtml(n.tip, 16)}</dd>
          <dt>Сумарна робота</dt><dd>${n.work.toLocaleString("uk-UA")}</dd>
          <dt>Mempool</dt><dd>${n.mempool} tx</dd>
          <dt>Адреса вузла</dt><dd class="mono">${short(n.address, 8)}</dd>
        </dl>
        <div class="actions">
          <button class="yellow small" data-mine="${n.id}">⛏ Майнити</button>
          <button class="ghost small" data-sync="${n.id}">⇄ Консенсус</button>
          <button class="ghost small" data-online="${n.id}" data-state="${n.online ? 0 : 1}">${n.online ? "✕ Відключити" : "↻ Підключити"}</button>
          <button class="danger small" data-attack="${n.id}">☠ Атака</button>
        </div>
        <div class="attack ${openAttack.has(n.id) ? "open" : ""}" data-attackform="${n.id}">
          Блок <select style="width:auto">${blocks}</select>
          <label><input type="checkbox" style="width:auto"> перемайнити ланцюжок</label>
          <button class="danger small" data-doattack="${n.id}">Підробити дані</button>
        </div>
      </div>`;
  }).join("");
}

function renderChain() {
  const node = S.nodes.find((n) => n.id === viewing);
  $("#chainOf").textContent = `· ${node.name}`;
  const prevHeight = lastHeight[viewing] ?? Infinity;
  lastHeight[viewing] = node.height;
  $("#chain").innerHTML = S.chain.map((b, i) => {
    const bad = b.audit && !b.audit.ok;
    const failed = bad ? Object.entries(b.audit.checks).filter(([, v]) => !v).map(([k]) => S.checks[k]) : [];
    const arrowBroken = b.audit && !b.audit.checks.link;
    const miner = S.node_names[b.miner] || (b.index === 0 ? "генезис" : short(b.miner, 6));
    return `${i ? `<div class="arrow ${arrowBroken ? "broken" : ""}"></div>` : ""}
      <div class="block ${bad ? "bad" : ""} ${selectedBlock === b.index ? "selected" : ""} ${b.index > prevHeight ? "fresh" : ""}" data-block="${b.index}">
        <div class="idx"><span>#${b.index}</span><span class="muted">${b.tx_count} tx</span></div>
        <div class="hash">${hashHtml(b.hash, 24)}</div>
        <div class="meta">nonce ${b.nonce.toLocaleString("uk-UA")}${b.mining_ms ? ` · ${b.mining_ms} мс` : ""}</div>
        <div class="meta">⛏ ${esc(miner)}</div>
        ${failed.length ? `<div class="err">✘ ${failed.join(", ")}</div>` : ""}
      </div>`;
  }).join("");
  const el = $("#chain");
  el.scrollLeft = el.scrollWidth;
}

function renderDetail() {
  const b = S.chain.find((x) => x.index === selectedBlock);
  if (!b) { $("#blockDetail").innerHTML = ""; return; }
  const checks = b.audit
    ? Object.entries(b.audit.checks).map(([k, v]) => `<div class="check ${v ? "" : "fail"}">${v ? "✔" : "✘"} ${S.checks[k]}</div>`).join("")
    : `<div class="check">✔ Генезис-блок зашитий у протокол</div>`;
  const txs = b.transactions.map((t) => `
    <div class="tx">
      <div class="row1"><span class="type ${t.type}">${TYPE_UA[t.type]}</span><span>${esc(t.text)}</span>
        <span class="sig" style="color:var(--${t.signature_ok ? "ok" : "bad"})">${t.signature_ok ? "✔ ЕЦП" : "✘ ЕЦП"}</span></div>
      <div class="id"><span>txid ${short(t.txid, 18)} · ${esc(t.sender_name)}</span>
        <button class="ghost small" data-proof="${t.txid}">Доведення Меркла</button></div>
      <div data-proofbox="${t.txid}"></div>
    </div>`).join("") || `<div class="empty">Генезис-блок не містить транзакцій</div>`;
  $("#blockDetail").innerHTML = `
    <div class="detail">
      <div>
        <h2>Блок #${b.index}</h2>
        <div class="kv">
          <div>Хеш</div><div>${b.hash}</div>
          <div>Попередній</div><div>${b.prev_hash}</div>
          <div>Корінь Меркла</div><div>${b.merkle_root}</div>
          <div>Nonce</div><div>${b.nonce}</div>
          <div>Складність</div><div>${b.difficulty} (${"0".repeat(b.difficulty) || "—"}…)</div>
          <div>Час</div><div>${new Date(b.timestamp * 1000).toLocaleString("uk-UA")}</div>
          <div>Майнер</div><div>${esc(S.node_names[b.miner] || b.miner)}</div>
          <div>ЕЦП майнера</div><div>${short(b.miner_signature, 32)}</div>
        </div>
        <div class="checks">${checks}</div>
        ${b.audit && b.audit.error ? `<p style="color:var(--bad)">${esc(b.audit.error)}</p>` : ""}
      </div>
      <div><h2>Транзакції</h2><div class="txs">${txs}</div></div>
    </div>`;
}

function renderProof(box, p) {
  const pathIdx = [];
  let idx = p.position;
  for (const level of p.levels) { pathIdx.push(idx); idx = Math.floor(idx / 2); }
  const rows = p.levels.map((level, li) => {
    const mine = pathIdx[li];
    const sib = (mine ^ 1) < level.length ? mine ^ 1 : mine;
    return `<div class="lvl">${level.map((h, i) => `<span class="n ${i === mine ? "path" : i === sib && li < p.levels.length - 1 ? "sib" : ""}">${h.slice(0, 6)}</span>`).join("")}</div>`;
  }).reverse().join("");
  box.innerHTML = `<div class="merkle">
    <div class="muted" style="font-size:12px">Корінь ↑ · <span class="zeros">жовтим</span> — шлях транзакції, <span style="color:var(--blue)">синім</span> — хеші доведення (${p.proof.length} шт.)</div>
    ${rows}
    <div style="font-size:12.5px;margin-top:6px">${p.verified ? "✔" : "✘"} Відновлений корінь ${p.verified ? "збігається" : "НЕ збігається"} з коренем блоку #${p.block} · підтверджень: ${p.confirmations}</div>
  </div>`;
}

function renderCampaigns() {
  $("#campaigns").innerHTML = S.campaigns.map((c) => {
    const pct = (v) => Math.min(100, (v / c.goal) * 100);
    const bought = c.spent - c.delivered - c.in_transit;
    const purchases = c.purchases_view.map((p) => `
      <div class="pp">${esc(p.items.map((i) => `${i.name} ×${i.qty}`).join(", "))} · <b>${uah(p.total)}</b>
        <div class="muted" style="font-size:11.5px">${esc(p.supplier_name)}</div>
        <div class="steps"><span class="done">Закуплено</span><span class="${p.shipment ? "done" : ""}">Відвантажено</span><span class="${p.receipt ? "done" : ""}">Отримано</span></div>
      </div>`).join("") || `<div class="muted" style="font-size:13px">Закупівель ще не було</div>`;
    return `
      <div class="campaign">
        <div><h3>${esc(c.title)}</h3><div class="who">${esc(c.fund_name)} → ${esc(c.recipient_name)}</div></div>
        <div class="nums"><span><b>${uah(c.raised)}</b> <span class="muted">з ${uah(c.goal)}</span></span><span class="muted">${c.donors} донор(ів)</span></div>
        <div class="bar"><span class="raised" style="width:${pct(c.raised)}%"></span></div>
        <div class="bar"><span class="delivered" style="width:${pct(c.delivered)}%"></span><span class="transit" style="width:${pct(c.in_transit)}%"></span><span class="bought" style="width:${pct(bought)}%"></span></div>
        <div class="legend"><span><i style="background:var(--ok)"></i>доставлено ${uah(c.delivered)}</span><span><i style="background:var(--warn)"></i>в дорозі ${uah(c.in_transit)}</span><span><i style="background:#9b8cff"></i>закуплено ${uah(bought)}</span><span>залишок ${uah(c.raised - c.spent)}</span></div>
        <div class="pipeline">${purchases}</div>
      </div>`;
  }).join("");
}

function renderMempool() {
  const node = S.nodes.find((n) => n.id === viewing);
  $("#mempoolOf").textContent = `· ${node.name}`;
  $("#mempool").innerHTML = S.mempool.length
    ? `<div class="mp">${S.mempool.map((t) => `<div class="tx"><div class="row1"><span class="type ${t.type}">${TYPE_UA[t.type]}</span><span>${esc(t.text)}</span></div><div class="id">txid ${short(t.txid, 18)}</div></div>`).join("")}</div>`
    : `<div class="empty">Порожньо — усі транзакції вже в блоках</div>`;
}

function renderActorSelect(rerenderForms) {
  const sel = $("#actorSelect");
  if (!selectedActor || !S.actors.some((a) => a.address === selectedActor)) selectedActor = (S.actors.find((a) => a.role === "DONOR") || S.actors[0] || {}).address;
  const groups = Object.entries(S.roles).map(([role, title]) => {
    const opts = S.actors.filter((a) => a.role === role).map((a) => `<option value="${a.address}" ${a.address === selectedActor ? "selected" : ""}>${esc(a.name)}</option>`).join("");
    return opts ? `<optgroup label="${title}">${opts}</optgroup>` : "";
  }).join("");
  if (sel.innerHTML !== groups) sel.innerHTML = groups;
  if (rerenderForms || !$("#actorForms").innerHTML) renderActorForms();
}

function options(list, label, value = (x) => x.id) {
  return list.length ? list.map((x) => `<option value="${value(x)}">${esc(label(x))}</option>`).join("") : `<option value="">— немає —</option>`;
}

function renderActorForms() {
  const me = S.actors.find((a) => a.address === selectedActor);
  if (!me) { $("#actorForms").innerHTML = ""; return; }
  const campaigns = options(S.campaigns, (c) => `${c.title} (зібрано ${uah(c.raised)})`);
  let html = `<div class="addr">${S.roles[me.role]} · адреса ${me.address}</div>`;
  if (me.role === "DONOR") {
    html += `<form class="form" data-form="donate"><h3>Зробити донат</h3>
      <div class="field"><label>Збір</label><select name="campaign">${campaigns}</select></div>
      <div class="grid2"><div class="field"><label>Сума, ₴</label><input name="amount" type="number" min="1" value="1000" required></div>
      <div class="field"><label>Побажання</label><input name="message" placeholder="необов'язково"></div></div>
      <button class="yellow">Підписати та надіслати</button></form>`;
  }
  if (me.role === "FUND") {
    const mine = S.campaigns.filter((c) => c.fund === me.address);
    html += `<form class="form" data-form="purchase"><h3>Закупівля</h3>
      <div class="grid2"><div class="field"><label>Збір</label><select name="campaign">${options(mine, (c) => `${c.title} (доступно ${uah(c.raised - c.spent)})`)}</select></div>
      <div class="field"><label>Постачальник</label><select name="supplier">${options(S.actors.filter((a) => a.role === "SUPPLIER"), (a) => a.name, (a) => a.address)}</select></div></div>
      <div class="grid3"><div class="field"><label>Товар</label><input name="item" value="Аптечка IFAK" required></div>
      <div class="field"><label>Кількість</label><input name="qty" type="number" min="1" value="5" required></div>
      <div class="field"><label>Ціна, ₴</label><input name="price" type="number" min="1" value="1150" required></div></div>
      <div class="field"><label>Рахунок-фактура (файл буде захешовано SHA-256 у браузері)</label><input name="file" type="file"></div>
      <button>Підписати закупівлю</button></form>
      <form class="form" data-form="campaign"><h3>Відкрити новий збір</h3>
      <div class="field"><label>Назва</label><input name="title" placeholder="напр., Павербанки для шпиталю" required></div>
      <div class="grid2"><div class="field"><label>Мета, ₴</label><input name="goal" type="number" min="1" value="50000" required></div>
      <div class="field"><label>Отримувач</label><select name="recipient">${options(S.actors.filter((a) => a.role === "RECIPIENT"), (a) => a.name, (a) => a.address)}</select></div></div>
      <button>Відкрити збір</button></form>`;
  }
  if (me.role === "SUPPLIER") {
    const mine = S.open_purchases.filter((p) => p.supplier === me.address);
    html += `<form class="form" data-form="ship"><h3>Відвантажити замовлення</h3>
      <div class="field"><label>Закупівля</label><select name="purchase">${options(mine, (p) => `${p.label} · ${uah(p.total)}`)}</select></div>
      <div class="field"><label>Номер ТТН</label><input name="tracking" value="2045${Math.floor(Math.random() * 1e10)}" required></div>
      <button>Підписати відвантаження</button></form>`;
  }
  if (me.role === "RECIPIENT") {
    const mine = S.open_shipments.filter((s) => s.recipient === me.address);
    html += `<form class="form" data-form="receipt"><h3>Підтвердити отримання</h3>
      <div class="field"><label>Відвантаження</label><select name="shipment">${options(mine, (s) => `${s.label} · ТТН ${s.tracking}`)}</select></div>
      <div class="grid2"><div class="field"><label>Стан</label><select name="status"><option value="OK">Отримано повністю</option><option value="PARTIAL">Частково</option><option value="DAMAGED">З пошкодженнями</option></select></div>
      <div class="field"><label>Коментар</label><input name="note" placeholder="необов'язково"></div></div>
      <div class="field"><label>Фото / акт (SHA-256 у браузері)</label><input name="file" type="file"></div>
      <button>Підписати акт отримання</button></form>`;
  }
  html += `<form class="form" data-form="register"><h3>Зареєструвати нового учасника</h3>
    <div class="grid2"><div class="field"><label>Назва / ім'я</label><input name="name" required placeholder="напр., Ігор Бойко"></div>
    <div class="field"><label>Роль</label><select name="role">${Object.entries(S.roles).map(([k, v]) => `<option value="${k}" ${k === "DONOR" ? "selected" : ""}>${v}</option>`).join("")}</select></div></div>
    <button class="ghost">Згенерувати ключі Ed25519 і зареєструвати</button></form>`;
  $("#actorForms").innerHTML = html;
}

function renderDonationSelect() {
  const sel = $("#donationSelect");
  const prev = sel.value;
  const opts = S.donations.map((d) => `<option value="${d.id}">${esc(d.donor_name)} — ${uah(d.amount)} → ${esc(d.campaign_title)}</option>`).join("");
  if (sel.innerHTML !== opts) {
    sel.innerHTML = opts;
    if (S.donations.some((d) => d.id === prev)) sel.value = prev;
    else { const big = [...S.donations].sort((a, b) => b.amount - a.amount)[0]; if (big) sel.value = big.id; }
  }
  if (sel.value) loadTrace(sel.value);
}

async function loadTrace(id) {
  try {
    const t = await api(`/api/trace/${id}?node=${viewing}`);
    // badge: номер блоку, довільний текст або null (без мітки)
    const step = (state, title, body, badge) => {
      const tag = typeof badge === "number" ? `<span class="blk">блок #${badge}</span>` : badge ? `<span class="blk" style="color:var(--muted)">${badge}</span>` : "";
      return `<div class="tstep"><div class="rail"><div class="b ${state}"></div><div class="l"></div></div>
        <div class="body"><b>${title}</b> ${tag}<div class="small">${body}</div></div></div>`;
    };
    let html = step("", `${esc(t.donation.donor_name)} задонатив ${uah(t.donation.amount)}`,
      `${t.donation.message ? `«${esc(t.donation.message)}» · ` : ""}txid ${short(t.donation.id, 14)}`, t.donation.block ?? "mempool");
    html += step("", `Збір «${esc(t.campaign.title)}»`,
      `Ваша частка — ${(t.share * 100).toFixed(1)}% від зібраних ${uah(t.campaign.raised)} · фонд ${esc(t.campaign.fund)} → ${esc(t.campaign.recipient)}`, null);
    for (const s of t.steps) {
      html += step("", `Закупівля: ${esc(s.items.map((i) => `${i.name} ×${i.qty}`).join(", "))}`,
        `${esc(s.supplier)} · ${uah(s.total)} · <b style="color:var(--yellow)">з них ваших ≈ ${uah(s.your_part)}</b>${s.invoice_hash ? ` · рахунок SHA-256 ${short(s.invoice_hash, 10)}` : ""}`, s.block);
      html += s.shipment
        ? step("", "Відвантажено отримувачу", `ТТН ${esc(s.shipment.tracking)}`, s.shipment.block)
        : step("wait", "Очікує відвантаження", "Постачальник ще не підписав відвантаження", null);
      html += s.receipt
        ? step("ok", `Отримання підтверджено (${s.receipt.status})`, esc(s.receipt.note || "Підписано ключем отримувача"), s.receipt.block)
        : step("wait", "Очікує підтвердження отримувачем", "", null);
    }
    if (t.unused > 0) html += step("wait", `Ще не витрачено: ${uah(t.unused)}`, "Кошти залишаються на балансі збору — фонд не може витратити їх поза збором", "баланс збору");
    $("#trace").innerHTML = `<div class="trace">${html}</div>`;
  } catch (e) {
    $("#trace").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

function renderLog() {
  $("#log").innerHTML = S.events.map((e) => `<div class="ev"><span class="t">${time(e.t)}</span><span class="k k-${e.kind}">${e.kind}</span><span>${esc(e.text)}</span></div>`).join("");
}

async function verifyFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/verify", { method: "POST", body: fd });
    $("#verifyResult").innerHTML = r.found
      ? `<div class="verdict ok"><h3>✔ Документ справжній</h3>
          <div style="font-size:13px">«${esc(r.filename)}» зареєстровано в блоці <span class="blk">#${r.proof.block}</span> (підтверджень: ${r.proof.confirmations}).<br>
          ${esc(r.text)} · підписав <b>${esc(r.signer)}</b> · поле <code>${r.field}</code></div>
          <div class="mono" style="margin-top:6px;color:var(--muted)">SHA-256 ${r.hash}</div>
          <div style="font-size:12.5px;margin-top:4px">Merkle-доведення: ${r.proof.proof.length} хеш(ів) → корінь ${r.proof.verified ? "збігається ✔" : "не збігається ✘"}</div></div>`
      : `<div class="verdict bad"><h3>✘ Документ не знайдено в блокчейні</h3>
          <div style="font-size:13px">«${esc(r.filename)}» не реєструвався або був змінений після реєстрації — навіть зміна одного символу дає зовсім інший хеш.</div>
          <div class="mono" style="margin-top:6px;color:var(--muted)">SHA-256 ${r.hash}</div></div>`;
  } catch (e) { toast(e.message, true); }
}

async function fileHash(input) {
  const f = input && input.files && input.files[0];
  if (!f || !window.crypto?.subtle) return undefined;
  const buf = await crypto.subtle.digest("SHA-256", await f.arrayBuffer());
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ─────────────────────────── події ───────────────────────────

document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, .node, .block");
  if (!t) return;
  const d = t.dataset;
  if (d.mine) {
    ev.stopPropagation();
    t.disabled = true; t.textContent = "⛏ Майнимо…";
    return act(() => post("/api/mine", { node: d.mine }), (r) => `Блок #${r.index} видобуто: nonce ${r.nonce}, ${r.ms} мс`);
  }
  if (d.sync) { ev.stopPropagation(); return act(() => post("/api/consensus", { node: d.sync }), (r) => r.changed ? "Ланцюжок замінено на найкращий валідний" : "Власний ланцюжок уже найкращий"); }
  if (d.online) { ev.stopPropagation(); return act(() => post("/api/online", { node: d.online, online: d.state === "1" })); }
  if (d.attack) { ev.stopPropagation(); openAttack.has(d.attack) ? openAttack.delete(d.attack) : openAttack.add(d.attack); return renderNodes(); }
  if (d.doattack) {
    ev.stopPropagation();
    const form = t.closest(".attack");
    const block = form.querySelector("select").value;
    const remine = form.querySelector("input").checked;
    openAttack.delete(d.doattack);
    viewing = d.doattack; selectedBlock = Number(block);
    return act(() => post("/api/tamper", { node: d.doattack, block, remine }), (r) => `Атаку виконано: змінено ${r.what}`);
  }
  if (d.proof) {
    const box = document.querySelector(`[data-proofbox="${d.proof}"]`);
    if (box.innerHTML) { box.innerHTML = ""; return; }
    try { renderProof(box, await api(`/api/proof/${d.proof}?node=${viewing}`)); } catch (e) { toast(e.message, true); }
    return;
  }
  if (t.id === "resetBtn") {
    selectedBlock = null; viewing = null; lastHeight = {};
    return act(() => post("/api/reset", {}), "Демонстраційну мережу відтворено");
  }
  if (t.classList.contains("node") && !ev.target.closest(".attack")) { viewing = t.dataset.node; selectedBlock = null; return load(); }
  if (t.classList.contains("block")) { selectedBlock = Number(d.block); renderChain(); renderDetail(); }
});

$("#actorSelect").addEventListener("change", (e) => { selectedActor = e.target.value; renderActorForms(); });
$("#donationSelect").addEventListener("change", (e) => loadTrace(e.target.value));

$("#actorForms").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const v = Object.fromEntries(new FormData(f));
  const kind = f.dataset.form;
  let body;
  if (kind === "donate") body = { type: "DONATION", payload: { campaign: v.campaign, amount: v.amount, message: v.message } };
  if (kind === "campaign") body = { type: "CAMPAIGN", payload: { title: v.title, goal: v.goal, recipient: v.recipient } };
  if (kind === "purchase") body = { type: "PURCHASE", payload: { campaign: v.campaign, supplier: v.supplier, items: [{ name: v.item, qty: v.qty, price: v.price }], invoice_hash: await fileHash(f.file) } };
  if (kind === "ship") body = { type: "SHIPMENT", payload: { purchase: v.purchase, tracking: v.tracking } };
  if (kind === "receipt") body = { type: "RECEIPT", payload: { shipment: v.shipment, status: v.status, note: v.note, photo_hash: await fileHash(f.file) } };
  if (kind === "register") body = { type: "REGISTER", payload: { name: v.name, role: v.role } };
  body.sender = selectedActor;
  for (const k of Object.keys(body.payload)) if (body.payload[k] === undefined || body.payload[k] === "") delete body.payload[k];
  act(() => post("/api/tx", body), (r) => `Транзакцію ${short(r.txid, 12)} підписано та розіслано вузлам`);
});

const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) verifyFile(e.dataTransfer.files[0]); });
$("#fileInput").addEventListener("change", (e) => e.target.files[0] && verifyFile(e.target.files[0]));

// посилання на конкретний стан: ?node=lviv&block=3&proof=1
const qs = new URLSearchParams(location.search);
viewing = qs.get("node");
if (qs.has("block")) selectedBlock = Number(qs.get("block"));
load(true).then(() => {
  if (qs.has("proof")) document.querySelector("[data-proof]")?.click();
  if (qs.has("scroll")) document.querySelector("#blockDetail")?.scrollIntoView();
});
