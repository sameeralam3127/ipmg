// App shell: hash router, theme toggle, and WebSocket bootstrap.

import { connect } from "./api.js";
import {
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
  { pattern: /^#\/inventory$/, name: "inventory", view: inventoryView },
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

  try {
    await route.view(root, match && match[1] ? Number(match[1]) : undefined);
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

// -------------------------------------------------------------- boot

window.addEventListener("hashchange", render);
initTheme();
connect();
render();
