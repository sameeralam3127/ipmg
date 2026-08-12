// Seeded, browser-only data for the GitHub Pages demonstration. It mirrors the
// local API shape so views stay identical when a real dashboard is available.

const seeds = [
  { id: 24, started_at: "2026-08-07 09:40", source: "branch-office.csv", total: 18, completed: 18, status: "complete", avg_latency: 13.8, duration_s: 4.2, status_counts: { Active: 16, Timeout: 1, Inactive: 1 } },
  { id: 23, started_at: "2026-08-06 09:40", source: "branch-office.csv", total: 18, completed: 18, status: "complete", avg_latency: 11.7, duration_s: 4.0, status_counts: { Active: 17, Timeout: 1 } },
  { id: 22, started_at: "2026-08-05 18:15", source: "datacenter-core.txt", total: 12, completed: 12, status: "complete", avg_latency: 8.9, duration_s: 3.1, status_counts: { Active: 12 } },
  { id: 21, started_at: "2026-08-04 09:40", source: "branch-office.csv", total: 18, completed: 18, status: "complete", avg_latency: 12.4, duration_s: 4.1, status_counts: { Active: 16, Timeout: 2 } },
];

const hosts = [
  ["10.24.8.1", "gateway-bom-01", "Active", 1.2], ["10.24.8.10", "finance-printer-01", "Active", 4.6],
  ["10.24.8.11", "finance-nas-01", "Active", 3.8], ["10.24.8.21", "reception-ap-01", "Active", 8.1],
  ["10.24.8.22", "meeting-room-ap", "Active", 9.4], ["10.24.8.31", "eng-mbp-01", "Active", 12.5],
  ["10.24.8.32", "eng-mbp-02", "Active", 14.2], ["10.24.8.33", "build-agent-01", "Active", 18.8],
  ["10.24.8.41", "cctv-nvr-01", "Active", 7.1], ["10.24.8.42", "cctv-cam-east", "Active", 10.3],
  ["10.24.8.51", "hr-workstation-03", "Active", 15.7], ["10.24.8.52", "hr-workstation-04", "Active", 14.8],
  ["10.24.8.61", "warehouse-scanner", "Active", 22.4], ["10.24.8.62", "label-printer-02", "Active", 19.1],
  ["10.24.8.71", "conference-display", "Active", 11.4], ["10.24.8.72", "visitor-kiosk", "Active", 16.6],
  ["10.24.8.81", "access-controller", "Timeout", null], ["10.24.8.91", "backup-appliance", "Inactive", null],
];

let scans = structuredClone(seeds);
let records = new Map();

function scanRows(scan) {
  if (records.has(scan.id)) return records.get(scan.id);
  const rows = hosts.slice(0, scan.total).map(([ip, hostname, status, latency], index) => {
    const isPrior = scan.id !== 24 && index === 17 ? "Timeout" : status;
    const adjusted = latency == null ? null : Number((latency * (1 + (24 - scan.id) * 0.05)).toFixed(1));
    return { ip, hostname, status: isPrior, latency: isPrior === "Active" ? adjusted : null, checked_at: scan.started_at };
  });
  records.set(scan.id, rows);
  return rows;
}

function csv(rows) {
  return ["IP Address,Hostname,Status,Latency,Checked", ...rows.map((r) => [r.ip, r.hostname, r.status, r.latency ?? "", r.checked_at].map((v) => `\"${String(v).replaceAll("\"", "\"\"")}\"`).join(","))].join("\n");
}

function statusCounts(rows) { return rows.reduce((out, row) => ({ ...out, [row.status]: (out[row.status] || 0) + 1 }), {}); }

export const demo = {
  stats: () => ({ scan_count: scans.length, host_count: hosts.length, latest_scan: scans[0], running_scans: [], trend: [...scans].reverse().map((s) => ({ ...s, active: s.status_counts.Active || 0 })) }),
  assets: () => hosts.map(([ip, hostname, status, latency], index) => ({ ip, hostname, status, avg_latency: latency, last_seen: status === "Active" ? "2026-08-07 09:40" : null, last_checked: "2026-08-07 09:40", scan_count: index < 16 ? 4 : 3 })),
  scans: (limit = 50) => scans.slice(0, limit),
  scan: (id) => scans.find((scan) => scan.id === Number(id)) || null,
  results: (id, { status, search } = {}) => scanRows(demo.scan(id)).filter((row) => (!status || row.status === status) && (!search || `${row.ip} ${row.hostname}`.toLowerCase().includes(search.toLowerCase()))),
  startScan: (payload) => {
    const supplied = (payload.targets || "").split(/\r?\n/).map((v) => v.trim()).filter((v) => v && !v.startsWith("#"));
    const source = payload.source === "dashboard" ? "manual dashboard scan" : payload.source || "manual dashboard scan";
    const id = Math.max(...scans.map((s) => s.id)) + 1;
    const rows = (supplied.length ? supplied.map((ip, i) => ({ ip, hostname: `managed-host-${String(i + 1).padStart(2, "0")}`, status: i % 7 === 6 ? "Timeout" : "Active", latency: i % 7 === 6 ? null : 6 + i * 1.3, checked_at: "2026-08-07 10:05" })) : scanRows(scans[0])).slice(0, 100);
    const scan = { id, started_at: "2026-08-07 10:05", source, total: rows.length, completed: rows.length, status: "complete", avg_latency: Number((rows.filter((r) => r.latency != null).reduce((n, r) => n + r.latency, 0) / Math.max(1, rows.filter((r) => r.latency != null).length)).toFixed(1)), duration_s: 2.8, status_counts: statusCounts(rows) };
    records.set(id, rows); scans.unshift(scan); return scan;
  },
  deleteScan: (id) => { scans = scans.filter((s) => s.id !== Number(id)); records.delete(Number(id)); return null; },
  cancelScan: (id) => ({ id, cancelling: true }),
  upload: async (file) => ({ filename: file.name, count: (await file.text()).split(/\r?\n/).filter(Boolean).length, targets: (await file.text()).split(/\r?\n/).filter(Boolean) }),
  reportUrl: (id) => `data:text/csv;charset=utf-8,${encodeURIComponent(csv(demo.results(id)))}`,
  diff: (id, { baseline } = {}) => {
    const current = demo.results(id); const previous = demo.results(baseline || scans.find((s) => s.id !== Number(id)).id);
    const before = new Map(previous.map((row) => [row.ip, row]));
    const changes = current.flatMap((row) => { const old = before.get(row.ip); if (!old) return [{ severity: "warning", label: "New host", ip: row.ip, hostname: row.hostname, previous: null, current: row.status }]; if (old.status !== row.status) return [{ severity: row.status === "Inactive" ? "critical" : "warning", label: "Service changed", ip: row.ip, hostname: row.hostname, previous: old.status, current: row.status }]; if (row.latency && old.latency && Math.abs(row.latency - old.latency) >= 5) return [{ severity: "info", label: "Latency changed", ip: row.ip, hostname: row.hostname, previous: `${old.latency} ms`, current: `${row.latency} ms`, delta: row.latency - old.latency }]; return []; });
    return { changes, summary: { total_changes: changes.length, severity_counts: statusCounts(changes.map((c) => ({ status: c.severity }))), unchanged_hosts: current.length - changes.length, baseline_hosts: previous.length, current_hosts: current.length } };
  },
  diffReportUrl: (id, _fmt, options) => `data:text/csv;charset=utf-8,${encodeURIComponent(csv(demo.results(id, options)))}`,
};
