// App shell: hash router, theme toggle, and WebSocket bootstrap.

import { connect } from "./api.js";
import {
  aboutView,
  changesView,
  dashboardView,
  historyView,
  inventoryView,
  monitorView,
  newScanView,
  scanDetailView,
} from "./views.js";

const routes = [
  { pattern: /^#?\/?$/, name: "dashboard", view: dashboardView },
  { pattern: /^#\/new$/, name: "new", view: newScanView },
  { pattern: /^#\/monitor(?:\/(\d+))?$/, name: "monitor", view: monitorView },
  { pattern: /^#\/history$/, name: "history", view: historyView },
  { pattern: /^#\/scan\/(\d+)$/, name: "history", view: scanDetailView },
  { pattern: /^#\/changes(?:\/(\d+))?(?:\/(\d+))?$/, name: "changes", view: changesView },
  { pattern: /^#\/inventory$/, name: "inventory", view: inventoryView },
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

  const params = (match ? match.slice(1) : []).map((value) =>
    value === undefined ? undefined : Number(value)
  );

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
  const isDemo = location.hostname.endsWith("github.io") || new URLSearchParams(location.search).has("demo");
  document.querySelector(".demo-badge").hidden = !isDemo;
}

// -------------------------------------------------------------- boot

window.addEventListener("hashchange", render);
initTheme();
initDemoBadge();
connect();
render();
