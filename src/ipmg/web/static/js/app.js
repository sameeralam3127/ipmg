// App shell: hash router, theme toggle, and WebSocket bootstrap.

import { connect } from "./api.js?v=20261118.2";
import {
  aboutView,
  changesView,
  dashboardView,
  historyView,
  hostView,
  inventoryView,
  monitorView,
  newScanView,
  scanDetailView,
  schedulesView,
} from "./views.js?v=20261118.2";

// The GitHub Pages demo opens on the seeded dashboard so visitors see data
// immediately; a real local dashboard opens straight into a new scan.
const isDemo =
  location.hostname.endsWith(".github.io") || new URLSearchParams(location.search).has("demo");

const routes = [
  isDemo
    ? { pattern: /^#?\/?$/, name: "dashboard", view: dashboardView }
    : { pattern: /^#?\/?$/, name: "new", view: newScanView },
  { pattern: /^#\/dashboard$/, name: "dashboard", view: dashboardView },
  { pattern: /^#\/new$/, name: "new", view: newScanView },
  { pattern: /^#\/monitor(?:\/(\d+))?$/, name: "monitor", view: monitorView },
  { pattern: /^#\/schedules$/, name: "schedules", view: schedulesView },
  { pattern: /^#\/history$/, name: "history", view: historyView },
  { pattern: /^#\/scan\/(\d+)$/, name: "history", view: scanDetailView },
  { pattern: /^#\/changes(?:\/(\d+))?(?:\/(\d+))?$/, name: "changes", view: changesView },
  { pattern: /^#\/inventory$/, name: "inventory", view: inventoryView },
  // The address stays text: it is not a number, and IPv6 is percent-encoded.
  { pattern: /^#\/host\/([^/]+)$/, name: "inventory", view: hostView, text: true },
  { pattern: /^#\/about$/, name: "about", view: aboutView },
];

async function render() {
  const root = document.getElementById("view");
  // Let the previous view tear down its subscriptions.
  root.dispatchEvent(new CustomEvent("view:destroy"));
  root.replaceChildren();

  const hash = location.hash || "#/";
  const route = routes.find((candidate) => candidate.pattern.test(hash)) || routes[0];
  const match = hash.match(route.pattern);

  document.querySelectorAll(".nav a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === route.name);
  });

  const params = (match ? match.slice(1) : []).map((value) => {
    if (value === undefined) return undefined;
    if (!route.text) return Number(value);
    try {
      return decodeURIComponent(value);
    } catch {
      return value; // a stray "%": the API will say it is not an address
    }
  });

  try {
    await route.view(root, ...params);
  } catch (err) {
    root.replaceChildren();
    const banner = document.createElement("div");
    banner.className = "banner err";
    banner.textContent = `Failed to load page: ${err.message}`;
    root.appendChild(banner);
  }
}

// ------------------------------------------------------------ theme

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
}

function initTheme() {
  applyTheme(localStorage.getItem("ipmg-theme"));
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const current = document.documentElement.dataset.theme || (systemDark ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem("ipmg-theme", next);
    applyTheme(next);
  });
}

function initDemoBadge() {
  document.querySelector(".demo-badge").hidden = !isDemo;
}

// -------------------------------------------------------------- boot

window.addEventListener("hashchange", render);
initTheme();
initDemoBadge();
connect();
render();
