// Page views for the IPMG dashboard. Each view renders into the <main> node.

import { api, onEvent } from "./api.js?v=20260808.1";
import { STATUS_COLORS, latencyTrend, statusDonut } from "./charts.js?v=20260808.1";

const REPORT_FORMATS = ["xlsx", "csv", "json", "md"];

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function toast(message, tone = "success") {
  const region = document.getElementById("toast-region");
  if (!region) return;
  const note = h("div", { class: `toast ${tone}`, role: "status" }, message);
  region.append(note);
  setTimeout(() => note.remove(), 3600);
}

function statusPill(status) {
  const pill = h("span", { class: "pill" }, status);
  pill.style.setProperty("--pill-color", STATUS_COLORS[status] || "var(--muted)");
  return pill;
}

const SCAN_STATE_COLORS = {
  running: "var(--st-timeout)",
  complete: "var(--st-active)",
  failed: "var(--st-inactive)",
  cancelled: "var(--muted)",
};

function scanStatePill(state) {
  const pill = h("span", { class: "pill" }, state);
  pill.style.setProperty("--pill-color", SCAN_STATE_COLORS[state] || "var(--muted)");
  return pill;
}

function fmtLatency(latency) {
  return latency == null ? "—" : `${Number(latency).toFixed(1)} ms`;
}

function fmtDuration(seconds) {
  return seconds == null ? "—" : `${Number(seconds).toFixed(1)}s`;
}

function activeRate(scan) {
  const active = scan.status_counts?.Active ?? 0;
  return scan.total ? `${((active / scan.total) * 100).toFixed(1)}%` : "—";
}

function tile(value, label) {
  return h("div", { class: "card tile" }, h("div", { class: "value" }, value), h("div", { class: "label" }, label));
}

function resultsTable(rows) {
  if (!rows.length) return h("div", { class: "empty" }, "No results.");
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, ...["IP Address", "Status", "Latency", "Hostname", "Checked"].map((t) => h("th", {}, t)))),
      h(
        "tbody",
        {},
        rows.map((row) =>
          h(
            "tr",
            {},
            h("td", {}, row.ip),
            h("td", {}, statusPill(row.status)),
            h("td", {}, fmtLatency(row.latency)),
            h("td", {}, row.hostname || "—"),
            h("td", {}, row.checked_at || "")
          )
        )
      )
    )
  );
}

function scansTable(scans, { onOpen }) {
  if (!scans.length) return h("div", { class: "empty" }, "No scans yet — start one from “New Scan”.");
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h(
        "thead",
        {},
        h("tr", {}, ...["#", "Started", "Source", "Hosts", "Active rate", "Avg latency", "Duration", "Status"].map((t) => h("th", {}, t)))
      ),
      h(
        "tbody",
        {},
        scans.map((scan) =>
          h(
            "tr",
            { class: "click", onclick: () => onOpen(scan) },
            h("td", {}, String(scan.id)),
            h("td", {}, scan.started_at),
            h("td", {}, scan.source),
            h("td", {}, `${scan.completed}/${scan.total}`),
            h("td", {}, activeRate(scan)),
            h("td", {}, fmtLatency(scan.avg_latency)),
            h("td", {}, fmtDuration(scan.duration_s)),
            h("td", {}, scanStatePill(scan.status))
          )
        )
      )
    )
  );
}

// --------------------------------------------------------------- about

export function aboutView(root) {
  const feature = (title, description) => h(
    "div", { class: "card feature-card" }, h("h3", {}, title), h("p", {}, description)
  );
  const external = (label, url) => h(
    "a", { class: "ghost-btn", href: url, target: "_blank", rel: "noreferrer" }, label
  );

  root.append(
    h("h1", { class: "page-title" }, "About IPMG"),
    h("p", { class: "page-sub" }, "IP Management & Ping Monitoring for authorized networks."),
    h(
      "section", { class: "card overview-card" },
      h("h2", {}, "A practical network visibility tool"),
      h("p", {}, "IPMG scans IP addresses, CIDR ranges, and target files in parallel. It records results locally, resolves hostnames when requested, and makes scan history, changes, and exports easy to review from the command line or dashboard."),
      h("div", { class: "toolbar" },
        external("View source on GitHub", "https://github.com/sameeralam3127/ipmg"),
        external("Install from PyPI", "https://pypi.org/project/ipmg/"),
        external("MIT License", "https://github.com/sameeralam3127/ipmg/blob/main/LICENSE"),
        h("a", { class: "btn", href: "#/new" }, "Try a demo scan")
      )
    ),
    h("h2", { class: "section-title" }, "Core features"),
    h("div", { class: "grid features-grid" },
      feature("Parallel ICMP scanning", "Probe individual IPs, CIDR blocks, ranges, and spreadsheet or text inputs with configurable concurrency and timeouts."),
      feature("Local dashboard", "Launch a private FastAPI dashboard for live scan progress, status charts, searchable results, and downloadable reports."),
      feature("History & inventory", "Store every scan in local SQLite, track the last status of every observed host, and export the inventory as CSV."),
      feature("Change detection", "Compare any two scans to identify outages, new or removed hosts, hostname changes, and meaningful latency shifts."),
      feature("DNS & reporting", "Optionally resolve reverse DNS and export results or change summaries as Excel, CSV, JSON, or Markdown."),
      feature("Offline by design", "The local dashboard bundles its assets and defaults to a loopback-only server. GitHub Pages uses clearly marked demo data instead."),
    ),
    h("section", { class: "card details-card" },
      h("h2", {}, "Project details"),
      h("dl", { class: "details-list" },
        h("dt", {}, "Repository"), h("dd", {}, h("a", { href: "https://github.com/sameeralam3127/ipmg", target: "_blank", rel: "noreferrer" }, "github.com/sameeralam3127/ipmg")),
        h("dt", {}, "Package"), h("dd", {}, h("a", { href: "https://pypi.org/project/ipmg/", target: "_blank", rel: "noreferrer" }, "pypi.org/project/ipmg")),
        h("dt", {}, "License"), h("dd", {}, "MIT — free for commercial and personal use."),
        h("dt", {}, "Technology"), h("dd", {}, "Python, FastAPI, SQLite, Pandas, and a dependency-free JavaScript dashboard."),
        h("dt", {}, "Safety"), h("dd", {}, "Only scan networks you are authorized to scan.")
      )
    )
  );
}

// ------------------------------------------------------------ dashboard

export async function dashboardView(root) {
  const stats = await api.stats();
  const latest = stats.latest_scan;

  root.append(
    h("h1", { class: "page-title" }, "Dashboard"),
    h("p", { class: "page-sub" }, "Overview of your local network scans.")
  );

  const tiles = h("div", { class: "grid tiles" });
  tiles.append(
    tile(String(stats.scan_count), "Total scans"),
    tile(String(stats.host_count), "Hosts tracked"),
    tile(latest ? String(latest.total) : "—", "Hosts in last scan"),
    tile(latest ? activeRate(latest) : "—", "Active rate (last scan)"),
    tile(latest && latest.avg_latency != null ? `${latest.avg_latency} ms` : "—", "Avg latency (last scan)")
  );
  root.append(tiles);

  if (stats.running_scans.length) {
    const running = stats.running_scans[0];
    root.append(
      h(
        "div",
        { class: "banner ok" },
        `Scan #${running.id} is running (${running.completed}/${running.total}) — `,
        h("a", { href: `#/monitor/${running.id}` }, "watch live")
      )
    );
  }

  const charts = h("div", { class: "grid two-col" });
  const statusCard = h("div", { class: "card" }, h("h3", {}, "Last scan status"));
  statusCard.append(
    latest ? statusDonut(latest.status_counts || {}) : h("div", { class: "empty" }, "No completed scans yet.")
  );
  const trendCard = h("div", { class: "card" }, h("h3", {}, "Latency trend"));
  trendCard.append(latencyTrend(stats.trend || []));
  charts.append(statusCard, trendCard);
  root.append(charts);

  const recent = h("div", { class: "card", style: "margin-top:14px" }, h("h3", {}, "Recent scans"));
  const scans = await api.scans(8);
  recent.append(scansTable(scans, { onOpen: (scan) => (location.hash = `#/scan/${scan.id}`) }));
  root.append(recent);
}

// ------------------------------------------------------------- new scan

export async function newScanView(root) {
  root.append(
    h("h1", { class: "page-title" }, "New Scan"),
    h("p", { class: "page-sub" }, "Upload a target file or enter IPs, CIDR blocks, or ranges manually.")
  );

  const banner = h("div");
  const targetsInput = h("textarea", {
    placeholder: "192.168.1.10\n192.168.1.0/24\n10.0.0.1-10.0.0.200\n# comments are ignored",
  });

  const fileInput = h("input", { type: "file", accept: ".xlsx,.xls,.csv,.txt,.list,.json", hidden: "" });
  const dropzone = h(
    "div",
    { class: "dropzone" },
    "Drop an Excel / CSV / text / JSON target file here, or click to browse."
  );
  dropzone.addEventListener("click", () => fileInput.click());
  ["dragover", "dragleave", "drop"].forEach((type) =>
    dropzone.addEventListener(type, (evt) => {
      evt.preventDefault();
      dropzone.classList.toggle("dragover", type === "dragover");
      if (type === "drop" && evt.dataTransfer.files.length) handleFile(evt.dataTransfer.files[0]);
    })
  );
  fileInput.addEventListener("change", () => fileInput.files.length && handleFile(fileInput.files[0]));

  async function handleFile(file) {
    banner.replaceChildren();
    try {
      const parsed = await api.upload(file);
      targetsInput.value = parsed.targets.join("\n");
      banner.append(h("div", { class: "banner ok" }, `Loaded ${parsed.count} targets from ${parsed.filename}.`));
    } catch (err) {
      banner.append(h("div", { class: "banner err" }, `Upload failed: ${err.message}`));
    }
  }

  const numField = (label, name, value, attrs = {}) =>
    h("label", { class: "field" }, h("span", {}, label), h("input", { type: "number", name, value, ...attrs }));

  const form = h("form", {});
  const configGrid = h("div", { class: "grid", style: "grid-template-columns:repeat(auto-fit,minmax(130px,1fr))" });
  configGrid.append(
    numField("Ping count", "count", "1", { min: 1, max: 10 }),
    numField("Timeout (s)", "timeout", "2", { min: 1, max: 60 }),
    numField("Threads", "threads", "50", { min: 1, max: 500 }),
    numField("DNS cache TTL (s)", "dns_cache_ttl", "300", { min: 0, max: 86400 })
  );

  const resolveCheck = h("label", { class: "check" }, h("input", { type: "checkbox", name: "resolve" }), "Resolve hostnames (reverse DNS)");
  const submit = h("button", { class: "btn", type: "submit" }, "Start Scan");

  form.append(
    h("label", { class: "field" }, h("span", {}, "Targets"), targetsInput),
    configGrid,
    resolveCheck,
    submit
  );

  form.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    banner.replaceChildren();
    submit.disabled = true;
    try {
      const data = new FormData(form);
      const scan = await api.startScan({
        targets: targetsInput.value,
        source: "dashboard",
        count: Number(data.get("count")),
        timeout: Number(data.get("timeout")),
        threads: Number(data.get("threads")),
        dns_cache_ttl: Number(data.get("dns_cache_ttl")),
        resolve: data.get("resolve") === "on",
      });
      toast(`Scan #${scan.id} created successfully.`);
      location.hash = `#/monitor/${scan.id}`;
    } catch (err) {
      banner.append(h("div", { class: "banner err" }, `Could not start scan: ${err.message}`));
      submit.disabled = false;
    }
  });

  root.append(banner, h("div", { class: "card" }, dropzone, fileInput, form));
}

// ---------------------------------------------------------- live monitor

export async function monitorView(root, scanId) {
  root.append(h("h1", { class: "page-title" }, "Live Monitor"));

  let scan = null;
  if (scanId) {
    scan = await api.scan(scanId).catch(() => null);
  } else {
    const stats = await api.stats();
    scan = stats.running_scans[0] || stats.latest_scan;
  }

  if (!scan) {
    root.append(h("div", { class: "empty" }, "No scans yet — start one from “New Scan”."));
    return;
  }

  const counts = { ...(scan.status_counts || {}) };
  let completed = scan.completed;
  const total = scan.total;

  root.append(
    h(
      "p",
      { class: "page-sub" },
      `Scan #${scan.id} · started ${scan.started_at} · ${scan.source}`
    )
  );

  const fill = h("div", { class: "progress-fill" });
  const meta = h("div", { class: "progress-meta" });
  const progressCard = h("div", { class: "card" }, h("div", { class: "progress-track" }, fill), meta);

  const donutHost = h("div");
  const donutCard = h("div", { class: "card" }, h("h3", {}, "Status distribution"), donutHost);

  const tableHost = h("div");
  const tableCard = h("div", { class: "card", style: "margin-top:14px" }, h("h3", {}, "Results (live)"), tableHost);

  const cancelBtn = h("button", { class: "btn danger", type: "button" }, "Cancel scan");
  cancelBtn.addEventListener("click", () => api.cancelScan(scan.id).catch(() => {}));

  const statusLine = h("div", { class: "banner" });

  const rows = await api.results(scan.id).catch(() => []);
  rows.reverse();

  function redraw() {
    fill.style.width = total ? `${(completed / total) * 100}%` : "0%";
    meta.replaceChildren(
      h("span", {}, `${completed} / ${total} hosts`),
      h("span", {}, total ? `${((completed / total) * 100).toFixed(0)}%` : "")
    );
    donutHost.replaceChildren(statusDonut(counts));
    tableHost.replaceChildren(resultsTable(rows.slice(0, 100)));
  }

  function setFinished(status, duration) {
    statusLine.className = `banner ${status === "complete" ? "ok" : "err"}`;
    statusLine.replaceChildren(
      `Scan ${status}${duration ? ` in ${fmtDuration(duration)}` : ""} — `,
      h("a", { href: `#/scan/${scan.id}` }, "open full results")
    );
    cancelBtn.remove();
  }

  if (scan.status === "running") {
    root.append(statusLine, progressCard, h("div", { class: "toolbar", style: "margin-top:14px" }, cancelBtn));
    statusLine.textContent = "Scanning…";
  } else {
    setFinished(scan.status, scan.duration_s);
    root.append(statusLine, progressCard);
  }

  root.append(h("div", { class: "grid two-col", style: "margin-top:14px" }, donutCard), tableCard);
  redraw();

  const unsubscribe = onEvent((event) => {
    if (event.scan_id !== scan.id) return;
    if (event.type === "result") {
      completed = event.completed;
      counts[event.result.status] = (counts[event.result.status] || 0) + 1;
      rows.unshift(event.result);
      redraw();
    } else if (event.type === "scan_finished") {
      setFinished(event.status, event.duration_s);
    }
  });
  root.addEventListener("view:destroy", unsubscribe, { once: true });
}

// -------------------------------------------------------------- history

export async function historyView(root) {
  root.append(
    h("h1", { class: "page-title" }, "Scan History"),
    h("p", { class: "page-sub" }, "Every scan stored in the local database.")
  );
  const scans = await api.scans(100);
  root.append(
    h("div", { class: "card" }, scansTable(scans, { onOpen: (scan) => (location.hash = `#/scan/${scan.id}`) }))
  );
}

// -------------------------------------------------------------- changes

const SEVERITY_COLORS = {
  critical: "var(--st-inactive)",
  warning: "var(--st-timeout)",
  info: "var(--st-active)",
};

const DIFF_FORMATS = ["md", "json", "csv"];

function severityPill(severity, label) {
  const pill = h("span", { class: "pill" }, label);
  pill.style.setProperty("--pill-color", SEVERITY_COLORS[severity] || "var(--muted)");
  return pill;
}

function changesTable(changes) {
  if (!changes.length) return h("div", { class: "empty" }, "No changes between these scans.");
  return h(
    "div",
    { class: "table-wrap" },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, ...["Change", "IP Address", "Hostname", "Previous", "Current", "Delta"].map((t) => h("th", {}, t)))),
      h(
        "tbody",
        {},
        changes.map((change) =>
          h(
            "tr",
            {},
            h("td", {}, severityPill(change.severity, change.label)),
            h("td", {}, change.ip),
            h("td", {}, change.hostname || "—"),
            h("td", {}, change.previous ?? "—"),
            h("td", {}, change.current ?? "—"),
            h("td", {}, change.delta == null ? "—" : `${change.delta > 0 ? "+" : ""}${change.delta.toFixed(1)} ms`)
          )
        )
      )
    )
  );
}

function scanOption(scan) {
  return h("option", { value: scan.id }, `#${scan.id} · ${scan.started_at} · ${scan.source}`);
}

export async function changesView(root, targetId, baselineId) {
  root.append(
    h("h1", { class: "page-title" }, "Changes"),
    h("p", { class: "page-sub" }, "Compare two scans to spot new hosts, outages, and latency shifts.")
  );

  const scans = (await api.scans(100)).filter((scan) => scan.status === "complete" || scan.status === "cancelled");
  if (scans.length < 2) {
    root.append(h("div", { class: "empty" }, "At least two finished scans are needed to compare."));
    return;
  }

  const known = new Set(scans.map((scan) => scan.id));
  const target = h("select", {}, ...scans.map(scanOption));
  const baseline = h("select", {}, ...scans.map(scanOption));

  // Ignore ids from the URL that are not in the list, so the selects always
  // hold a valid scan.
  target.value = String(known.has(targetId) ? targetId : scans[0].id);
  const fallback = scans.find((scan) => String(scan.id) !== target.value);
  baseline.value = String(known.has(baselineId) ? baselineId : fallback.id);

  const threshold = h("input", { type: "number", min: 0, step: "0.5", value: "5", title: "Latency threshold (ms)" });

  const exports = h("span", { class: "exports" });
  const tiles = h("div", { class: "grid tiles" });
  const tableHost = h("div", { class: "card", style: "margin-top:14px" });

  const toolbar = h(
    "div",
    { class: "toolbar" },
    h("label", { class: "control" }, "Baseline", baseline),
    h("label", { class: "control" }, "Compare to", target),
    h("label", { class: "control" }, "Latency Δ (ms)", threshold),
    h("span", { class: "spacer" }),
    exports
  );

  async function refresh() {
    const options = { baseline: Number(baseline.value), latencyThreshold: Number(threshold.value) || 0 };
    tableHost.replaceChildren(h("div", { class: "empty" }, "Comparing…"));
    let diff;
    try {
      diff = await api.diff(Number(target.value), options);
    } catch (err) {
      tiles.replaceChildren();
      tableHost.replaceChildren(h("div", { class: "banner err" }, `Comparison failed: ${err.message}`));
      return;
    }

    const summary = diff.summary;
    tiles.replaceChildren(
      tile(String(summary.total_changes), "Changes"),
      tile(String(summary.severity_counts.critical || 0), "Critical"),
      tile(String(summary.severity_counts.warning || 0), "Warning"),
      tile(String(summary.unchanged_hosts), "Unchanged hosts"),
      tile(`${summary.baseline_hosts} → ${summary.current_hosts}`, "Hosts scanned")
    );

    exports.replaceChildren(
      ...DIFF_FORMATS.map((fmt) =>
        h(
          "a",
          { class: "ghost-btn", href: api.diffReportUrl(Number(target.value), fmt, options), download: "" },
          fmt.toUpperCase()
        )
      )
    );

    tableHost.replaceChildren(h("h3", {}, `Detected changes (${diff.changes.length})`), changesTable(diff.changes));
  }

  baseline.addEventListener("change", refresh);
  target.addEventListener("change", refresh);
  threshold.addEventListener("change", refresh);

  root.append(toolbar, tiles, tableHost);
  await refresh();
}

// ----------------------------------------------------------- scan detail

export async function scanDetailView(root, scanId) {
  const scan = await api.scan(scanId).catch(() => null);
  if (!scan) {
    root.append(h("div", { class: "empty" }, "Scan not found."));
    return;
  }

  root.append(
    h("h1", { class: "page-title" }, `Scan #${scan.id}`),
    h(
      "p",
      { class: "page-sub" },
      `${scan.started_at} · ${scan.source} · ${scan.status} · ${fmtDuration(scan.duration_s)}`
    )
  );

  const tiles = h("div", { class: "grid tiles" });
  tiles.append(
    tile(String(scan.total), "Hosts"),
    tile(String(scan.status_counts?.Active ?? 0), "Active"),
    tile(activeRate(scan), "Active rate"),
    tile(scan.avg_latency != null ? `${scan.avg_latency} ms` : "—", "Avg latency")
  );
  root.append(tiles);

  const toolbar = h("div", { class: "toolbar" });
  const search = h("input", { type: "text", placeholder: "Search IP or hostname…" });
  const statusFilter = h(
    "select",
    {},
    h("option", { value: "" }, "All statuses"),
    ...Object.keys(scan.status_counts || {}).map((status) => h("option", { value: status }, status))
  );
  toolbar.append(search, statusFilter, h("span", { class: "spacer" }));

  toolbar.append(h("a", { class: "ghost-btn", href: `#/changes/${scan.id}` }, "Compare"));

  for (const fmt of REPORT_FORMATS) {
    toolbar.append(
      h("a", { class: "ghost-btn", href: api.reportUrl(scan.id, fmt), download: "" }, fmt.toUpperCase())
    );
  }

  const deleteBtn = h("button", { class: "btn danger", type: "button" }, "Delete");
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete scan #${scan.id} and its results?`)) return;
    await api.deleteScan(scan.id);
    toast(`Scan #${scan.id} deleted.`);
    location.hash = "#/history";
  });
  toolbar.append(deleteBtn);

  const donutCard = h("div", { class: "card" }, h("h3", {}, "Status distribution"), statusDonut(scan.status_counts || {}));
  const tableHost = h("div", { class: "card", style: "margin-top:14px" });

  async function refreshTable() {
    const rows = await api.results(scan.id, {
      status: statusFilter.value || undefined,
      search: search.value || undefined,
    });
    tableHost.replaceChildren(h("h3", {}, `Results (${rows.length})`), resultsTable(rows));
  }

  let debounce;
  search.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(refreshTable, 250);
  });
  statusFilter.addEventListener("change", refreshTable);

  root.append(toolbar, h("div", { class: "grid two-col" }, donutCard), tableHost);
  await refreshTable();
}

// ------------------------------------------------------------ inventory

export async function inventoryView(root) {
  root.append(
    h("h1", { class: "page-title" }, "Inventory"),
    h("p", { class: "page-sub" }, "Every host seen across all stored scans.")
  );

  const assets = await api.assets();
  const toolbar = h("div", { class: "toolbar" });
  const search = h("input", { type: "text", placeholder: "Filter by IP or hostname…" });
  const exportBtn = h("button", { class: "ghost-btn", type: "button" }, "Export CSV");
  toolbar.append(search, h("span", { class: "spacer" }), exportBtn);

  const tableHost = h("div", { class: "card" });

  function matching() {
    const term = search.value.trim().toLowerCase();
    if (!term) return assets;
    return assets.filter(
      (asset) =>
        asset.ip.toLowerCase().includes(term) || (asset.hostname || "").toLowerCase().includes(term)
    );
  }

  function draw() {
    const rows = matching();
    if (!rows.length) {
      tableHost.replaceChildren(h("div", { class: "empty" }, "No hosts recorded yet."));
      return;
    }
    tableHost.replaceChildren(
      h(
        "div",
        { class: "table-wrap" },
        h(
          "table",
          {},
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              ...["IP Address", "Hostname", "Last status", "Avg latency", "Last seen active", "Last checked", "Scans"].map((t) => h("th", {}, t))
            )
          ),
          h(
            "tbody",
            {},
            rows.map((asset) =>
              h(
                "tr",
                {},
                h("td", {}, asset.ip),
                h("td", {}, asset.hostname || "—"),
                h("td", {}, statusPill(asset.status)),
                h("td", {}, fmtLatency(asset.avg_latency)),
                h("td", {}, asset.last_seen || "never"),
                h("td", {}, asset.last_checked || ""),
                h("td", {}, String(asset.scan_count))
              )
            )
          )
        )
      )
    );
  }

  search.addEventListener("input", draw);
  exportBtn.addEventListener("click", () => {
    const rows = matching();
    const header = "IP Address,Hostname,Last Status,Avg Latency,Last Seen Active,Last Checked,Scans";
    const csv = [
      header,
      ...rows.map((asset) =>
        [asset.ip, asset.hostname || "", asset.status, asset.avg_latency ?? "", asset.last_seen || "", asset.last_checked || "", asset.scan_count]
          .map((value) => `"${String(value).replaceAll('"', '""')}"`)
          .join(",")
      ),
    ].join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = "ipmg_inventory.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  });

  root.append(toolbar, tableHost);
  draw();
}
