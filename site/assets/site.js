// IPMG project site: theme, live project data, and the interactive widgets.
// Dependency-free. Every section is readable without JavaScript or network
// access; this file only adds motion, live data, and interactivity.

const REPO = "sameeralam3127/ipmg";
const FALLBACK_VERSION = "1.13.1";
const CACHE_MS = 30 * 60 * 1000;

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

const store = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* storage blocked or full */
    }
  },
};

function announce(message) {
  const region = $("#sr-status");
  if (region) region.textContent = message;
}

// ------------------------------------------------------------ theme

function initTheme() {
  $("[data-theme-toggle]")?.addEventListener("click", () => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const current = document.documentElement.dataset.theme || (systemDark ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set("ipmg-theme", next); // shared with the dashboard demo
  });
}

// ----------------------------------------------------------- header

function initHeader() {
  const bar = $(".topbar");
  const update = () => bar.classList.toggle("scrolled", window.scrollY > 8);
  update();
  window.addEventListener("scroll", update, { passive: true });

  if (!("IntersectionObserver" in window)) return;
  const links = $$(".topnav a[href^='#']");
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        links.forEach((link) => link.classList.toggle("active", link.hash === `#${entry.target.id}`));
      }
    },
    { rootMargin: "-40% 0px -55% 0px" }
  );
  links.map((link) => $(link.hash)).filter(Boolean).forEach((section) => observer.observe(section));
}

// ----------------------------------------------------------- motion

function initReveal() {
  const items = $$(".reveal");
  if (reduceMotion || !("IntersectionObserver" in window)) {
    items.forEach((item) => item.classList.add("in"));
    return;
  }
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("in");
        observer.unobserve(entry.target);
      }
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );
  items.forEach((item) => observer.observe(item));
}

function initCounters() {
  if (reduceMotion || !("IntersectionObserver" in window)) return; // static text is already correct
  const format = new Intl.NumberFormat("en-US");
  const run = (node) => {
    const target = Number(node.dataset.count);
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / 1200);
      node.textContent = format.format(Math.round(target * (1 - (1 - progress) ** 3)));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        run(entry.target);
        observer.unobserve(entry.target);
      }
    },
    { threshold: 0.6 }
  );
  $$("[data-count]").forEach((node) => observer.observe(node));
}

// ------------------------------------------------------------- copy

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = el("textarea", "sr-only");
    area.value = text;
    area.setAttribute("readonly", "");
    document.body.append(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}

function initCopy() {
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy], [data-copy-from]");
    if (!button) return;
    const text = button.dataset.copy ?? $(button.dataset.copyFrom)?.textContent ?? "";
    const ok = await copyText(text.trim());
    button.dataset.label ??= button.textContent;
    button.dataset.state = ok ? "copied" : "failed";
    button.textContent = ok ? "Copied" : "Press ⌘/Ctrl+C";
    announce(ok ? "Copied to clipboard" : "Copy failed");
    clearTimeout(Number(button.dataset.timer));
    button.dataset.timer = String(
      setTimeout(() => {
        button.textContent = button.dataset.label;
        delete button.dataset.state;
      }, 1600)
    );
  });
}

// ------------------------------------------------------------- tabs

function initTabs() {
  $$("[data-tabs]").forEach((group) => {
    const tabs = $$("[role='tab']", group);
    const select = (tab, { focus = false, remember = true } = {}) => {
      tabs.forEach((candidate) => {
        const selected = candidate === tab;
        candidate.setAttribute("aria-selected", String(selected));
        candidate.tabIndex = selected ? 0 : -1;
        document.getElementById(candidate.getAttribute("aria-controls")).hidden = !selected;
      });
      if (focus) tab.focus();
      if (remember) store.set("ipmg-install-tab", tab.id);
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", (event) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (!step) return;
        event.preventDefault();
        select(tabs[(index + step + tabs.length) % tabs.length], { focus: true });
      });
    });

    const saved = tabs.find((tab) => tab.id === store.get("ipmg-install-tab"));
    const platform = navigator.userAgentData?.platform || navigator.platform || "";
    const windows = /win/i.test(platform) ? tabs.find((tab) => tab.dataset.os === "windows") : null;
    select(saved || windows || tabs[0], { remember: false });
  });
}

// --------------------------------------------------------- terminal

const DEMO_HOSTS = [
  { at: 14, ip: "192.168.1.1", name: "gateway.lan", ms: 0.9 },
  { at: 42, ip: "192.168.1.10", name: "nas.lan", ms: 2.4 },
  { at: 77, ip: "192.168.1.24", name: "printer.lan", ms: 3.1 },
  { at: 121, ip: "192.168.1.42", name: "office-ap.lan", ms: 5.6 },
  { at: 166, ip: "192.168.1.87", name: "build-01.lan", ms: 1.8 },
  { at: 219, ip: "192.168.1.120", name: "cam-front.lan", ms: 12.4 },
];
const TOTAL_HOSTS = 254;
const SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏";
let terminalVersion = FALLBACK_VERSION;
let terminalRun = 0;

function termLine(...parts) {
  const line = el("div");
  for (const part of parts) {
    if (part instanceof Node) {
      line.append(part);
      continue;
    }
    const [text, className] = Array.isArray(part) ? part : [part, null];
    line.append(className ? el("span", className, text) : document.createTextNode(text));
  }
  return line;
}

function bar(fraction, width = 22) {
  const filled = Math.round(fraction * width);
  return [["━".repeat(filled), "t-accent"], ["─".repeat(width - filled), "t-dim"]];
}

function reportName(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `results_${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}.xlsx`;
}

async function playTerminal() {
  const body = $("[data-terminal]");
  if (!body) return;
  const run = ++terminalRun;
  const instant = reduceMotion;
  const alive = () => run === terminalRun;
  const wait = async (ms) => {
    if (instant) return alive();
    await sleep(ms);
    while (document.hidden && alive()) await sleep(400);
    return alive();
  };
  const add = (line) => {
    body.append(line);
    return line;
  };

  body.replaceChildren();
  const command = "ipmg --input 192.168.1.0/24 --stream --resolve";
  const typed = el("span");
  const cursor = el("span", "t-cursor");
  add(termLine(["$ ", "t-accent"], typed, cursor));
  if (instant) typed.textContent = command;
  for (let i = 1; !instant && i <= command.length; i += 1) {
    typed.textContent = command.slice(0, i);
    if (!(await wait(i < 5 ? 90 : 28 + Math.random() * 40))) return;
  }
  if (!(await wait(420))) return;
  cursor.remove();

  const columns = (status, host, name, latency) =>
    `${status.padEnd(10)}${host.padEnd(16)}${name.padEnd(15)}${latency.padStart(8)}`;

  [
    termLine(""),
    termLine("  ", [`ipmg ${terminalVersion}`, "t-bold"], ["  ·  scan", "t-dim"]),
    termLine(["  ICMP probes only — scan only networks you are authorized to scan.", "t-dim"]),
    termLine(""),
    termLine(["  Source   ", "t-dim"], "192.168.1.0/24"),
    termLine(["  Targets  ", "t-dim"], `${TOTAL_HOSTS} hosts`),
    termLine(["  Config   ", "t-dim"], "50 threads · 2s timeout · 1 ping · reverse DNS"),
    termLine(""),
    termLine(["  Live", "t-bold"]),
    termLine(["  " + columns("Status", "Host", "Name", "Latency"), "t-dim"]),
  ].forEach(add);
  if (!(await wait(260))) return;

  const progress = add(termLine(""));
  let shown = 0;
  const frames = instant ? [TOTAL_HOSTS] : Array.from({ length: 48 }, (_, i) => Math.round(((i + 1) / 48) * TOTAL_HOSTS));
  for (const [frame, done] of frames.entries()) {
    while (shown < DEMO_HOSTS.length && DEMO_HOSTS[shown].at <= done) {
      const host = DEMO_HOSTS[shown];
      const row = columns("", host.ip, host.name, `${host.ms.toFixed(1)} ms`).slice(10);
      body.insertBefore(termLine("  ", ["●", "t-green"], " Active".padEnd(10), row), progress);
      shown += 1;
    }
    const pct = String(Math.round((done / TOTAL_HOSTS) * 100)).padStart(3);
    const secs = String(Math.floor((done / TOTAL_HOSTS) * 6)).padStart(2, "0");
    progress.replaceChildren(
      ...termLine(
        "   ",
        [SPINNER[frame % SPINNER.length], "t-accent"],
        " Scanning ",
        ...bar(done / TOTAL_HOSTS),
        ` ${pct}% ${String(done).padStart(3)}/${TOTAL_HOSTS} 0:00:${secs} `,
        [`${shown} up`, "t-green"]
      ).childNodes
    );
    if (!(await wait(62))) return;
  }
  progress.remove();

  const active = DEMO_HOSTS.length;
  const avg = DEMO_HOSTS.reduce((sum, host) => sum + host.ms, 0) / active;
  const activePct = (active / TOTAL_HOSTS) * 100;
  const summary = [
    termLine(""),
    termLine(["  Results", "t-bold"]),
    termLine("  ", ["●", "t-green"], " Active   ", String(active).padStart(3), "  ", ...bar(active / TOTAL_HOSTS), `  ${activePct.toFixed(1).padStart(5)}%`),
    termLine("  ", ["●", "t-yellow"], " Timeout  ", String(TOTAL_HOSTS - active).padStart(3), "  ", ...bar(1 - active / TOTAL_HOSTS), `  ${(100 - activePct).toFixed(1).padStart(5)}%`),
    termLine(""),
    termLine("  ", [`${TOTAL_HOSTS} hosts`, "t-bold"], ["  ·  ", "t-dim"], `${activePct.toFixed(1)}% active`, ["  ·  ", "t-dim"], `${avg.toFixed(1)} ms avg`, ["  ·  ", "t-dim"], "6.12s"),
    termLine(""),
    termLine(["  Saved    ", "t-dim"], [reportName(), "t-accent"]),
    termLine(""),
    termLine(["$ ", "t-accent"], el("span", "t-cursor")),
  ];
  for (const line of summary) {
    add(line);
    if (!(await wait(90))) return;
  }

  if (!instant && (await wait(9000))) playTerminal();
}

function initTerminal() {
  $("[data-replay]")?.addEventListener("click", () => playTerminal());
  playTerminal();
}

// ---------------------------------------------------------- builder

// Shell-quotes a value, leaving plain paths (including a leading ~/) readable.
function shellQuote(value) {
  if (/^(~\/)?[\w.\/:,@%+=-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function describeTarget(target) {
  if (/\.(xlsx|xls|csv)$/i.test(target)) return "Read hosts from the “IP Address” column of this spreadsheet, which must already exist.";
  if (/\.(txt|list)$/i.test(target)) return "Read one IP, CIDR block, or range per line from this file, which must already exist.";
  if (target.includes("/")) return "Scan every host in this CIDR block.";
  if (target.includes("-")) return "Scan every address in this range.";
  return "Scan this single host.";
}

function integerIn(value, fallback, { min = 1, max = 1e9 } = {}) {
  const number = Number(value);
  return String(value).trim() !== "" && Number.isInteger(number) && number >= min && number <= max ? number : fallback;
}

function decimalIn(value, fallback, { min = 0, max = 1e9 } = {}) {
  const number = Number(value);
  return String(value).trim() !== "" && Number.isFinite(number) && number >= min && number <= max ? number : fallback;
}

const FORMAT_NAMES = { xlsx: "Excel", csv: "CSV", json: "JSON", md: "Markdown" };
const DEFAULT_PORTS = "21,22,25,53,80,443,445,1433,3306,3389,5432";
const listPhrase = (items) => (items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : items[0]);
const formatPhrase = (formats) => listPhrase(formats.map((format) => FORMAT_NAMES[format]));

function parsePorts(text) {
  const cleaned = text.replace(/\s+/g, "");
  if (!cleaned) return { ports: null };
  const parts = cleaned.split(",");
  const valid = parts.every((part) => /^\d{1,5}$/.test(part) && Number(part) >= 1 && Number(part) <= 65535);
  return valid ? { ports: parts.map(Number).join(",") } : { error: true };
}

// Collects the command's tokens and a plain-language note for each flag.
function commandLine(...words) {
  const tokens = words.map((word) => [word, "tok-cmd"]);
  const notes = [];
  return {
    tokens,
    notes,
    flag(name, note, value) {
      tokens.push([name, "tok-flag"]);
      if (value != null) tokens.push([String(value), "tok-val"]);
      notes.push({ key: value != null ? `${name} ${value}` : name, note });
    },
    args(values, note) {
      values.forEach((value) => tokens.push([String(value), "tok-val"]));
      notes.push({ key: values.join(" "), note });
    },
    info(note, key = "(default)") {
      notes.push({ key, note });
    },
    warn(note) {
      notes.push({ key: "heads-up", note, warn: true });
    },
  };
}

function addLatency(form, line, prefix) {
  const ms = decimalIn(form.value(`${prefix}-latencyMs`), 5);
  const pct = decimalIn(form.value(`${prefix}-latencyPct`), 25);
  if (ms !== 5) line.flag("--latency-threshold", `Report a latency change only if it moved by at least ${ms} ms (and by the percentage).`, ms);
  if (pct !== 25) line.flag("--latency-pct", `Report a latency change only if it moved by at least ${pct}% (and by the milliseconds).`, pct);
}

function addCommon(form, line, prefix) {
  const db = form.value(`${prefix}-db`);
  if (db) line.flag("--db", "Use this history database instead of ~/.ipmg/dashboard.db.", shellQuote(db));
  if (form.on(`${prefix}-verbose`)) line.flag("--verbose", "Print debug logging.");
}

const BUILDERS = {
  scan(form, line) {
    if (form.value("scan-mode") === "discover") {
      line.flag("--discover", "Find this machine's address and scan the /24 network around it.");
    } else {
      const target = form.target() || "192.168.1.0/24";
      line.flag("--input", describeTarget(target), shellQuote(target));
    }

    if (form.on("scan-resolve")) {
      line.flag("--resolve", "Look up each host's name with reverse DNS.");
      const ttl = integerIn(form.value("scan-dnsTtl"), 300, { min: 0, max: 86400 });
      if (ttl !== 300) line.flag("--dns-cache-ttl", ttl === 0 ? "Don't cache names; look each one up again." : `Cache looked-up names for ${ttl} seconds.`, ttl);
    }

    if (form.on("scan-scanPorts")) {
      line.flag("--scan-ports", "Check TCP ports on every host that answers the ping.");
      const { ports, error } = parsePorts(form.value("scan-ports"));
      if (error) line.warn("Ports must be comma-separated numbers from 1 to 65535, so the default list is used.");
      else if (ports && ports !== DEFAULT_PORTS) line.flag("--ports", `Probe only port${ports.includes(",") ? "s" : ""} ${ports.replaceAll(",", ", ")}.`, ports);
      else line.info("Probe FTP, SSH, SMTP, DNS, HTTP, HTTPS, SMB, SQL Server, MySQL, RDP, and PostgreSQL.", "(default ports)");
      const portTimeout = decimalIn(form.value("scan-portTimeout"), 1, { min: 0.1, max: 60 });
      if (portTimeout !== 1) line.flag("--port-timeout", `Give each port ${portTimeout} s to accept a connection.`, portTimeout);
    }

    const streamAll = form.on("scan-streamAll");
    const streaming = streamAll || form.on("scan-stream");
    if (streamAll) line.flag("--stream-all", "Print every result as it arrives, including hosts that didn't answer.");
    else if (streaming) line.flag("--stream", "Print each host that answers the moment its probe finishes.");
    if (streaming) {
      const refresh = decimalIn(form.value("scan-refresh"), 0.25, { min: 0.05, max: 5 });
      if (refresh !== 0.25) line.flag("--stream-refresh", `Redraw the progress bar every ${refresh} s.`, refresh);
    }

    if (form.on("scan-compare")) {
      line.flag("--compare", "After the scan, report what changed since the previous scan of the same input.");
      if (form.on("scan-anySource")) line.flag("--compare-any-source", "Compare with the previous scan even if it scanned a different input.");
      const diffFormats = form.all("scan-diffFormats");
      if (diffFormats.length) line.flag("--diff-formats", `Also save the change summary as ${formatPhrase(diffFormats)}.`, diffFormats.join(" "));
      addLatency(form, line, "scan");
    }

    if (form.on("scan-noHistory")) {
      line.flag("--no-history", "Don't store this scan in the history database.");
      if (form.on("scan-compare")) line.warn("Change detection needs scan history, so --compare is skipped when --no-history is set.");
    }

    const formats = form.all("scan-formats");
    const defaultFormat = !formats.length || (formats.length === 1 && formats[0] === "xlsx");
    if (!defaultFormat) line.flag("--formats", `Write the report as ${formatPhrase(formats)}.`, formats.join(" "));
    const prefix = form.value("scan-output") || "results";
    if (prefix !== "results") {
      const folder = prefix.includes("/") ? " The folder must already exist." : "";
      line.flag("--output", `Name the report files ${prefix}_<timestamp>.<format>.${folder}`, shellQuote(prefix));
    }

    const threads = integerIn(form.value("scan-threads"), 50, { max: 1000 });
    const timeout = integerIn(form.value("scan-timeout"), 2, { max: 60 });
    const count = integerIn(form.value("scan-count"), 1, { max: 20 });
    const interval = integerIn(form.value("scan-interval"), 0, { min: 0, max: 1440 });
    if (threads !== 50) line.flag("--threads", `Probe ${threads} hosts at once.`, threads);
    if (timeout !== 2) line.flag("--timeout", `Wait up to ${timeout} second${timeout === 1 ? "" : "s"} for each reply.`, timeout);
    if (count !== 1) line.flag("--count", `Send ${count} pings to each host.`, count);
    if (interval > 0) line.flag("--interval", `Repeat the whole scan every ${interval} minute${interval === 1 ? "" : "s"}, until Ctrl+C.`, interval);

    addCommon(form, line, "scan");
    if (defaultFormat) line.info(`An Excel report is saved as ${prefix}_<timestamp>.xlsx when the scan finishes.`);
  },

  diff(form, line) {
    const target = integerIn(form.value("diff-target"), null);
    const baseline = integerIn(form.value("diff-baseline"), null);
    if (target && baseline) {
      line.args([baseline, target], `Compare scan ${baseline} (the baseline) with scan ${target}.`);
    } else if (target) {
      line.args([target], `Compare scan ${target} with the scan before it.`);
    } else {
      line.info("Compare the two most recent scans.");
      if (baseline) line.warn("Fill in “Scan id” too: a baseline needs a scan to compare it with.");
    }

    const source = form.value("diff-source");
    if (source && !(target && baseline)) line.flag("--source", `Only consider scans of ${source} when picking scans automatically.`, shellQuote(source));

    const limit = integerIn(form.value("diff-limit"), 0, { min: 0 });
    if (limit > 0) line.flag("--limit", `Print at most ${limit} change${limit === 1 ? "" : "s"}; exports still include every change.`, limit);
    if (form.on("diff-failOnChange")) line.flag("--fail-on-change", "Exit with code 2 when anything changed, so cron or CI can react.");

    const formats = form.all("diff-formats");
    if (formats.length) {
      line.flag("--diff-formats", `Save the change summary as ${formatPhrase(formats)}.`, formats.join(" "));
      const name = form.value("diff-output") || "changes";
      if (name !== "changes") line.flag("--diff-output", `Name the exports ${name}_<timestamp>.<format>.`, shellQuote(name));
    }

    addLatency(form, line, "diff");
    addCommon(form, line, "diff");
  },

  history(form, line) {
    const limit = integerIn(form.value("history-limit"), 20);
    if (limit === 20) line.info("List the 20 most recent scans.");
    else line.flag("--limit", `List the ${limit} most recent scan${limit === 1 ? "" : "s"}.`, limit);
    const source = form.value("history-source");
    if (source) line.flag("--source", `Only list scans of ${source}.`, shellQuote(source));
    addCommon(form, line, "history");
  },

  dashboard(form, line) {
    const port = integerIn(form.value("dash-port"), 8080, { max: 65535 });
    if (form.value("dash-host") === "0.0.0.0") {
      line.flag("--host", "Listen on every network interface, not only this machine.", "0.0.0.0");
      line.warn("The dashboard has no login: anyone who can reach this machine can start scans and read results. Prefer an SSH tunnel, or put an authenticating reverse proxy in front.");
    }
    if (port !== 8080) line.flag("--port", `Serve on port ${port}.`, port);
    if (form.on("dash-noBrowser")) line.flag("--no-browser", "Don't open a browser, for servers and SSH sessions.");
    addCommon(form, line, "dash");
    line.info(`Then open http://127.0.0.1:${port} in a browser on this machine.`, "then");
  },
};

function initBuilder() {
  const form = $("[data-builder]");
  if (!form) return;
  const output = $("[data-command]");
  const explain = $("[data-explain]");
  const panels = $$("[data-panel]", form);
  const targetInput = form.elements["scan-target"];
  let previous = null;

  const render = () => {
    const data = new FormData(form);
    const reader = {
      value: (name) => String(data.get(name) ?? "").trim(),
      on: (name) => data.has(name),
      all: (name) => data.getAll(name).map(String),
      target: () => targetInput.value.trim(), // read directly: disabled inputs are left out of FormData
    };

    const command = reader.value("command") || "scan";
    panels.forEach((panel) => {
      panel.hidden = panel.dataset.panel !== command;
    });
    $$("[data-show-if]", form).forEach((node) => {
      node.hidden = !reader.on(node.dataset.showIf);
    });
    targetInput.disabled = reader.value("scan-mode") === "discover";

    const line = commandLine(...(command === "scan" ? ["ipmg"] : ["ipmg", command]));
    BUILDERS[command](reader, line);

    const pieces = [];
    line.tokens.forEach(([text, className], index) => {
      if (index) pieces.push(document.createTextNode(" "));
      pieces.push(el("span", className, text));
    });
    output.replaceChildren(...pieces);

    const keys = line.notes.map((note) => `${command}:${note.key}`);
    explain.replaceChildren(
      ...line.notes.map((note, index) => {
        const isNew = previous && !previous.has(keys[index]) && !reduceMotion;
        const item = el("li", [note.warn ? "warn" : "", isNew ? "enter" : ""].filter(Boolean).join(" "));
        item.append(el("code", "", note.key), el("span", "", note.note));
        return item;
      })
    );
    previous = new Set(keys);
  };

  form.addEventListener("input", render);
  form.addEventListener("change", render);
  form.addEventListener("submit", (event) => event.preventDefault());
  $$("[data-target]", form).forEach((chip) =>
    chip.addEventListener("click", () => {
      form.elements["scan-mode"].value = "input";
      targetInput.value = chip.dataset.target;
      render();
      targetInput.focus();
    })
  );
  render();
}

// ---------------------------------------------------------- changes

function initChangeFilter() {
  const chips = $$("[data-severity-filter]");
  const rows = $$("[data-severity]");
  chips.forEach((chip) =>
    chip.addEventListener("click", () => {
      const wanted = chip.dataset.severityFilter;
      chips.forEach((candidate) => candidate.setAttribute("aria-pressed", String(candidate === chip)));
      rows.forEach((row) => {
        row.hidden = wanted !== "all" && row.dataset.severity !== wanted;
      });
    })
  );
}

// -------------------------------------------------------- live data

async function cachedJson(key, url, pick) {
  const cached = store.get(key);
  if (cached) {
    try {
      const { at, data } = JSON.parse(cached);
      if (Date.now() - at < CACHE_MS) return data;
    } catch {
      /* corrupt cache entry: refetch */
    }
  }
  const response = await fetch(url, { headers: { Accept: "application/json" }, referrerPolicy: "no-referrer" });
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  const data = pick(await response.json());
  store.set(key, JSON.stringify({ at: Date.now(), data }));
  return data;
}

function relativeDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const days = Math.round((date.getTime() - Date.now()) / 86400000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(days) < 30) return rtf.format(days, "day");
  if (Math.abs(days) < 365) return rtf.format(Math.round(days / 30), "month");
  return rtf.format(Math.round(days / 365), "year");
}

async function loadVersion() {
  try {
    const { version, released } = await cachedJson("ipmg-site-pypi", "https://pypi.org/pypi/ipmg/json", (json) => ({
      version: String(json.info?.version || ""),
      released: json.urls?.[0]?.upload_time_iso_8601 || null,
    }));
    if (!/^\d+\.\d+\.\d+/.test(version)) return;
    terminalVersion = version;
    const when = released ? ` · released ${relativeDate(released)}` : "";
    $("[data-release-label]").textContent = `v${version} on PyPI${when}`;
    const chip = $("[data-version]");
    chip.textContent = `latest: ${version}`;
    chip.hidden = false;
    $("[data-version-footer]").textContent = `v${version}`;
  } catch {
    /* keep the static label */
  }
}

async function loadStars() {
  try {
    const { stars } = await cachedJson("ipmg-site-repo", `https://api.github.com/repos/${REPO}`, (json) => ({
      stars: Number(json.stargazers_count),
    }));
    if (!Number.isFinite(stars)) return;
    const node = $("[data-stars]");
    node.textContent = new Intl.NumberFormat("en-US", { notation: "compact" }).format(stars);
    node.setAttribute("aria-label", `${stars} stars`);
    node.hidden = false;
  } catch {
    /* rate-limited or offline: the link still works */
  }
}

// Release notes are written by semantic-release: "### Section" headings with
// "- **scope**: text ([#12](url), [`sha`](url))" bullets, sometimes wrapped.
function parseNotes(body = "") {
  const sections = [];
  let section = null;
  let item = null;
  for (const raw of body.split(/\r?\n/)) {
    const heading = raw.match(/^###\s+(.+)/);
    if (heading) {
      section = { title: heading[1].trim(), items: [] };
      sections.push(section);
      item = null;
      continue;
    }
    if (!section) continue;
    const bullet = raw.match(/^\s*[-*]\s+(.*)/);
    if (bullet) {
      item = { text: bullet[1] };
      section.items.push(item);
    } else if (item && /^\s+\S/.test(raw)) {
      item.text += ` ${raw.trim()}`;
    } else if (!raw.trim()) {
      item = null;
    }
  }
  return sections
    .map(({ title, items }) => ({ title, items: items.map(({ text }) => cleanNote(text)) }))
    .filter(({ items }) => items.length);
}

function cleanNote(text) {
  const pr = text.match(/\[#(\d+)\]/)?.[1] || null;
  let plain = text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\s*\((?:#\d+,?\s*)?`?[0-9a-f]{7,40}`?\)\s*$/, "")
    .replace(/\s*\(#\d+\)\s*$/, "");
  const scope = plain.match(/^\*\*([^*]+)\*\*:\s*/);
  if (scope) plain = plain.slice(scope[0].length);
  return { scope: scope ? scope[1] : null, text: plain.replace(/[*_`]/g, "").trim(), pr };
}

async function loadReleases() {
  const grid = $("[data-releases]");
  if (!grid) return;
  try {
    const releases = await cachedJson("ipmg-site-releases", `https://api.github.com/repos/${REPO}/releases?per_page=3`, (json) =>
      json.map((release) => ({
        tag: String(release.tag_name),
        url: String(release.html_url),
        published: release.published_at,
        sections: parseNotes(release.body || ""),
      }))
    );
    if (!releases.length) throw new Error("no releases");

    grid.replaceChildren(
      ...releases.map((release, index) => {
        const card = el("article", index === 0 ? "release latest" : "release");
        const top = el("div", "release-top");
        const link = el("a", "", release.tag);
        link.href = release.url.startsWith("https://github.com/") ? release.url : `https://github.com/${REPO}/releases`;
        link.rel = "noopener";
        const time = el("time", "", relativeDate(release.published));
        time.dateTime = release.published;
        top.append(link, time);
        card.append(top);

        let budget = 4;
        for (const section of release.sections) {
          if (budget <= 0) break;
          const list = el("ul");
          for (const note of section.items.slice(0, budget)) {
            const li = el("li");
            if (note.scope) li.append(el("span", "scope", note.scope));
            li.append(document.createTextNode(note.text));
            if (note.pr && /^\d+$/.test(note.pr)) {
              const pr = el("a", "", `#${note.pr}`);
              pr.href = `https://github.com/${REPO}/pull/${note.pr}`;
              pr.rel = "noopener";
              li.append(pr);
            }
            list.append(li);
            budget -= 1;
          }
          card.append(el("h4", "", section.title), list);
        }
        if (!release.sections.length) card.append(el("p", "muted", "Maintenance release."));
        return card;
      })
    );
  } catch {
    const message = el("p", "release-error", "Release notes couldn't be loaded right now. ");
    const link = el("a", "", "See every release on GitHub.");
    link.href = `https://github.com/${REPO}/releases`;
    message.append(link);
    grid.replaceChildren(message);
  }
}

// ------------------------------------------------------------- boot

initTheme();
initHeader();
initReveal();
initCounters();
initCopy();
initTabs();
initBuilder();
initChangeFilter();
initTerminal();
loadVersion();
loadStars();
loadReleases();
