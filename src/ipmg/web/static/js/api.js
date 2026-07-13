// REST + WebSocket client for the local IPMG API. No external dependencies.

const BASE = "/api/v1";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options);
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
  stats: () => request("/stats"),
  assets: () => request("/assets"),
  scans: (limit = 50) => request(`/scans?limit=${limit}`),
  scan: (id) => request(`/scans/${id}`),
  results: (id, { status, search } = {}) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    const suffix = params.toString() ? `?${params}` : "";
    return request(`/scans/${id}/results${suffix}`);
  },
  startScan: (payload) =>
    request("/scans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  cancelScan: (id) => request(`/scans/${id}/cancel`, { method: "POST" }),
  deleteScan: (id) => request(`/scans/${id}`, { method: "DELETE" }),
  upload: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/upload", { method: "POST", body: form });
  },
  reportUrl: (id, fmt) => `${BASE}/scans/${id}/report?fmt=${fmt}`,
};

// ------------------------------------------------------------ websocket

const listeners = new Set();
let socket = null;
let reconnectDelay = 1000;

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
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${protocol}//${location.host}${BASE}/ws`);
  setConnState("connecting");

  socket.onopen = () => {
    reconnectDelay = 1000;
    setConnState("open");
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
