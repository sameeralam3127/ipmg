// REST + WebSocket client for the local IPMG API. No external dependencies.

import { demo } from "./demo.js";

const BASE = "/api/v1";
// Pages has no Python process. `?demo=1` is also useful for reviewing the
// static experience locally without starting a scanner.
const useDemo = location.hostname.endsWith(".github.io") || new URLSearchParams(location.search).has("demo");

// `ipmg web` opens the page as /#token=…. A URL fragment is never sent to the
// server, so the token stays out of access logs and proxies. Keep it for API
// calls (and for other tabs until the server restarts with a new one), then
// swap the fragment for the home route. This module runs before the router.
const TOKEN_KEY = "ipmg-token";
const token = useDemo ? "" : takeToken();

function takeToken() {
  const match = location.hash.match(/^#token=([A-Za-z0-9._~-]+)$/);
  if (match) {
    try {
      localStorage.setItem(TOKEN_KEY, match[1]);
    } catch {
      /* storage blocked: the token lives for this page only */
    }
    history.replaceState(null, "", `${location.pathname}${location.search}#/`);
    return match[1];
  }
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

const authHeader = () => ({ Authorization: `Bearer ${token}` });

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}), ...authHeader() };
  const response = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  stats: () => useDemo ? demo.stats() : request("/stats"),
  assets: () => useDemo ? demo.assets() : request("/assets"),
  scans: (limit = 50) => useDemo ? demo.scans(limit) : request(`/scans?limit=${limit}`),
  scan: (id) => useDemo ? Promise.resolve(demo.scan(id)) : request(`/scans/${id}`),
  results: (id, { status, search } = {}) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    const suffix = params.toString() ? `?${params}` : "";
    return useDemo ? Promise.resolve(demo.results(id, { status, search })) : request(`/scans/${id}/results${suffix}`);
  },
  startScan: (payload) =>
    useDemo ? Promise.resolve(demo.startScan(payload)) : request("/scans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  cancelScan: (id) => useDemo ? Promise.resolve(demo.cancelScan(id)) : request(`/scans/${id}/cancel`, { method: "POST" }),
  deleteScan: (id) => useDemo ? Promise.resolve(demo.deleteScan(id)) : request(`/scans/${id}`, { method: "DELETE" }),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return useDemo ? demo.upload(file) : request("/upload", { method: "POST", body: form });
  },
  reportUrl: (id, fmt) => useDemo ? demo.reportUrl(id, fmt) : `${BASE}/scans/${id}/report?fmt=${fmt}`,
  diff: (id, { baseline, latencyThreshold, latencyPct } = {}) =>
    useDemo ? Promise.resolve(demo.diff(id, { baseline, latencyThreshold, latencyPct })) : request(`/scans/${id}/diff${diffQuery({ baseline, latencyThreshold, latencyPct })}`),
  diffReportUrl: (id, fmt, options = {}) =>
    useDemo ? demo.diffReportUrl(id, fmt, options) : `${BASE}/scans/${id}/diff/report?fmt=${fmt}${diffQuery(options).replace("?", "&")}`,
  download,
};

// Report links need the token too, so fetch them with the header and save
// the response, rather than navigating to a URL that would have to carry it.
async function download(url) {
  if (url.startsWith("data:")) {
    saveHref(url, "");
    return;
  }
  const response = await fetch(url, { headers: authHeader() });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const disposition = response.headers.get("Content-Disposition") || "";
  const name = (disposition.match(/filename="([^"]+)"/) || [])[1] || "ipmg-report";
  const objectUrl = URL.createObjectURL(await response.blob());
  saveHref(objectUrl, name);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
}

function saveHref(href, name) {
  const link = document.createElement("a");
  link.href = href;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
}

function diffQuery({ baseline, latencyThreshold, latencyPct } = {}) {
  const params = new URLSearchParams();
  if (baseline != null) params.set("baseline", baseline);
  if (latencyThreshold != null) params.set("latency_threshold", latencyThreshold);
  if (latencyPct != null) params.set("latency_pct", latencyPct);
  return params.toString() ? `?${params}` : "";
}

// ------------------------------------------------------------ websocket

const listeners = new Set();
let socket = null;
let reconnectDelay = 1000;
let hasConnected = false;

export function onEvent(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

function setConnState(state) {
  const el = document.getElementById("conn-status");
  if (el) {
    el.dataset.state = state;
    el.textContent = state === "open" ? "live" : state;
  }
}

export function connect() {
  if (useDemo) {
    setConnState("demo");
    return;
  }
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  // Browsers cannot set headers on a WebSocket, so the token rides in the
  // subprotocol list; the server answers with the plain "ipmg" protocol.
  socket = new WebSocket(`${protocol}//${location.host}${BASE}/ws`, ["ipmg", `ipmg.token.${token}`]);
  setConnState("connecting");

  socket.onopen = () => {
    reconnectDelay = 1000;
    setConnState("open");
    // Events sent while the socket was down (or dropped because this tab fell
    // behind) are gone; tell views to reload their state from the API.
    if (hasConnected) listeners.forEach((handler) => handler({ type: "reconnected" }));
    hasConnected = true;
  };

  socket.onmessage = (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      return;
    }
    listeners.forEach((handler) => handler(event));
  };

  socket.onclose = () => {
    setConnState("closed");
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 15000);
  };

  socket.onerror = () => socket.close();
}
