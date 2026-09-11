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

function shellQuote(value) {
  return /^[\w.\/:,@%+=-]+$/.test(value) ? value : `'${value.replaceAll("'", "'\\''")}'`;
}

function describeTarget(target) {
  if (/\.(xlsx|xls|csv)$/i.test(target)) return "Read hosts from the “IP Address” column of this spreadsheet.";
  if (/\.(txt|list)$/i.test(target)) return "Read one IP or CIDR per line from this file.";
  if (target.includes("/")) return "Scan every host in this CIDR block.";
  if (target.includes("-")) return "Scan every address in this range.";
  return "Scan this single host.";
}

function positiveInt(value, fallback, { min = 1, max = 100000 } = {}) {
  const number = Number.parseInt(value, 10);
  return Number.isFinite(number) && number >= min && number <= max ? number : fallback;
}

const FORMAT_NAMES = { xlsx: "Excel", csv: "CSV", json: "JSON", md: "Markdown" };

function initBuilder() {
  const form = $("[data-builder]");
  if (!form) return;
  const output = $("[data-command]");
  const explain = $("[data-explain]");
  const targetInput = form.elements.target;
  let previous = new Set();

  const render = () => {
    const data = new FormData(form);
    const tokens = [["ipmg", "tok-cmd"]];
    const notes = [];
    const flag = (name, note, value) => {
      tokens.push([name, "tok-flag"]);
      if (value != null) tokens.push([String(value), "tok-val"]);
      notes.push([value != null ? `${name} ${value}` : name, note]);
    };

    const discover = data.get("mode") === "discover";
    targetInput.disabled = discover;
    if (discover) {
      flag("--discover", "Find this machine's address and scan the /24 network around it.");
    } else {
      const target = String(data.get("target") || "").trim() || "192.168.1.0/24";
      flag("--input", describeTarget(target), shellQuote(target));
    }

    if (data.has("resolve")) flag("--resolve", "Look up each host's name with reverse DNS.");
    if (data.has("stream")) flag("--stream", "Print each host that answers the moment its probe finishes.");
    if (data.has("scanPorts")) flag("--scan-ports", "Probe common TCP ports (SSH, HTTP, HTTPS, RDP, SMB, databases) on hosts that answer.");
    if (data.has("compare")) flag("--compare", "After the scan, report what changed since the previous scan of the same targets.");

    const formats = data.getAll("formats");
    if (formats.length && !(formats.length === 1 && formats[0] === "xlsx")) {
      const names = formats.map((format) => FORMAT_NAMES[format]);
      const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names[0];
      flag("--formats", `Write the report as ${list}.`, formats.join(" "));
    }

    const threads = positiveInt(data.get("threads"), 50, { max: 1000 });
    const timeout = positiveInt(data.get("timeout"), 2, { max: 60 });
    const count = positiveInt(data.get("count"), 1, { max: 20 });
    const interval = positiveInt(data.get("interval"), 0, { min: 0, max: 1440 });
    if (threads !== 50) flag("--threads", `Probe ${threads} hosts at once.`, threads);
    if (timeout !== 2) flag("--timeout", `Wait up to ${timeout} seconds for each reply.`, timeout);
    if (count !== 1) flag("--count", `Send ${count} pings to each host.`, count);
    if (interval > 0) flag("--interval", `Repeat the whole scan every ${interval} minute${interval === 1 ? "" : "s"}.`, interval);

    if (!formats.length || (formats.length === 1 && formats[0] === "xlsx")) {
      notes.push(["report", "An Excel report is saved when the scan finishes (the default)."]);
    }

    const pieces = [];
    tokens.forEach(([text, className], index) => {
      if (index) pieces.push(document.createTextNode(" "));
      pieces.push(el("span", className, text));
    });
    output.replaceChildren(...pieces);

    const current = new Set(notes.map(([key]) => key));
    explain.replaceChildren(
      ...notes.map(([key, note]) => {
        const item = el("li", previous.has(key) || reduceMotion ? "" : "enter");
        item.append(el("code", "", key === "report" ? "(default)" : key), el("span", "", note));
        return item;
      })
    );
    previous = current;
  };

  form.addEventListener("input", render);
  form.addEventListener("change", render);
  form.addEventListener("submit", (event) => event.preventDefault());
  $$("[data-target]", form).forEach((chip) =>
    chip.addEventListener("click", () => {
      form.elements.mode.value = "input";
      targetInput.value = chip.dataset.target;
      render();
      targetInput.focus();
    })
  );
  previous = new Set(["--input", "--stream", "report"]);
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
