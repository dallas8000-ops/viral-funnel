const $ = (id) => document.getElementById(id);

async function j(url, opts) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

function money(cents) {
  return `$${(cents / 100).toLocaleString()}`;
}

async function loadBoard() {
  const s = await j("/api/scoreboard");
  $("verdictTitle").textContent = s.status;
  $("verdictTitle").className = s.status;
  $("verdictLine").textContent = s.line;
  $("kpiRow").innerHTML = [
    ["Day", s.day],
    ["Paid", `${s.paid}/${s.need}`],
    ["MRR", money(s.mrr_cents)],
    ["Need/day", s.sales_per_day_required],
    ["Queue", s.queue_depth],
    ["Posted", s.posted],
  ]
    .map(([k, v]) => `<div class="kpi"><b>${v}</b><span>${k}</span></div>`)
    .join("");
  $("math").textContent = [
    `Target        ${money(s.target_cents)} MRR`,
    `Price         $49 / mo`,
    `Members need  ${s.need}`,
    `Now           ${s.paid} → ${money(s.mrr_cents)}`,
    `Clock         ${s.started_at || "NOT STARTED"}`,
    `Niche         ${s.niche || "unset"}`,
    `Offer         ${s.offer_name || "unset"}`,
  ].join("\n");
}

async function loadConfig() {
  const c = await j("/api/config");
  const form = $("cfg");
  for (const [k, v] of Object.entries(c)) {
    if (form[k]) form[k].value = v || "";
  }
}

async function loadSources() {
  const data = await j("/api/sources");
  $("sourceBody").innerHTML = data.items
    .map(
      (i) =>
        `<tr><td>${i.score.toFixed(2)}</td><td>${i.platform}</td><td><a href="${i.url}" target="_blank" rel="noreferrer">${i.title}</a></td></tr>`
    )
    .join("");
}

async function loadQueue() {
  const data = await j("/api/queue");
  $("queueBody").innerHTML = data.posts
    .map((p) => {
      const pack = p.asset_dir
        ? `<a href="/assets/${p.asset_dir.split(/[/\\\\]/).pop()}/pack.json">open</a>`
        : "";
      return `<tr><td>${p.publish_at.replace("T", " ").slice(0, 16)}</td><td><span class="badge">${p.status}</span></td><td>${p.hook}</td><td>${pack}</td></tr>`;
    })
    .join("");
}

document.querySelectorAll(".nav").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav").forEach((b) => b.classList.remove("on"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("on"));
    btn.classList.add("on");
    $(btn.dataset.tab).classList.add("on");
  });
});

$("cfg").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  await j("/api/config", { method: "PUT", body: JSON.stringify(body) });
  await loadBoard();
});

$("startClock").addEventListener("click", async () => {
  await j("/api/start", { method: "POST", body: "{}" });
  await loadBoard();
});

$("runFactory").addEventListener("click", async () => {
  $("timings").textContent = "Running…";
  try {
    const r = await j("/api/factory", { method: "POST", body: "{}" });
    $("timings").textContent = JSON.stringify(r, null, 2);
    await Promise.all([loadBoard(), loadSources(), loadQueue()]);
  } catch (err) {
    $("timings").textContent = String(err.message || err);
  }
});

$("runPublish").addEventListener("click", async () => {
  const r = await j("/api/publish", { method: "POST", body: "{}" });
  $("timings").textContent = JSON.stringify(r, null, 2);
  await loadQueue();
});

loadBoard();
loadConfig();
loadSources();
loadQueue();
