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
      const pack = p.pack_url ? `<a href="${p.pack_url}">json</a>` : "";
      return `<tr class="clickable" data-job="${p.job_id}"><td>${p.publish_at.replace("T", " ").slice(0, 16)}</td><td><span class="badge">${p.status}</span></td><td>${p.hook}</td><td>${pack}</td></tr>`;
    })
    .join("");
}

async function showPreview(jobId) {
  const job = await j(`/api/jobs/${jobId}`);
  $("preview").hidden = false;
  $("previewHook").textContent = job.hook || "Preview";
  $("previewCaption").textContent = job.caption || "";
  $("previewSlides").innerHTML = (job.slide_urls || [])
    .map((src) => `<img src="${src}" alt="" />`)
    .join("");
  $("previewPack").href = job.pack_url || "#";
  $("copyCaption").onclick = async () => {
    await navigator.clipboard.writeText(job.caption || "");
  };
}

document.querySelectorAll(".nav").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav").forEach((b) => b.classList.remove("on"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("on"));
    btn.classList.add("on");
    $(btn.dataset.tab).classList.add("on");
  });
});

$("queueBody").addEventListener("click", (e) => {
  const row = e.target.closest("tr[data-job]");
  if (!row) return;
  showPreview(row.dataset.job);
});

$("cfg").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector("[type=submit]");
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    await j("/api/config", { method: "PUT", body: JSON.stringify(body) });
    btn.textContent = "Saved ✓";
    await loadBoard();
  } catch (err) {
    btn.textContent = "Error: " + (err.message || err);
  } finally {
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 2000);
  }
});

$("startClock").addEventListener("click", async () => {
  await j("/api/start", { method: "POST", body: "{}" });
  await loadBoard();
});

$("runFactory").addEventListener("click", async () => {
  $("timings").textContent = "Running…";
  $("runFactory").disabled = true;
  try {
    const r = await j("/api/factory", { method: "POST", body: "{}" });
    $("timings").textContent = JSON.stringify(r, null, 2);
    await Promise.all([loadBoard(), loadSources(), loadQueue()]);
  } catch (err) {
    $("timings").textContent = String(err.message || err);
  } finally {
    $("runFactory").disabled = false;
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
