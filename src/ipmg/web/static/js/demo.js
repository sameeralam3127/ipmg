// Seeded, browser-only data for the GitHub Pages demonstration. It mirrors the
// local API shape so views stay identical when a real dashboard is available.

const seeds = [
  { id: 24, started_at: "2026-08-07 09:40", source: "branch-office.csv", total: 18, completed: 18, status: "complete", avg_latency: 13.8, duration_s: 4.2, status_counts: { Active: 16, Timeout: 1, Inactive: 1 } },
  { id: 23, started_at: "2026-08-06 09:40", source: "branch-office.csv", total: 18, completed: 18, status: "complete", avg_latency: 11.7, duration_s: 4.0, status_counts: { Active: 16, Timeout: 2 } },
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

// How scan #23, the day before the latest, differed, so comparing #23 with #24
// shows a host going offline, one coming back, a latency jump, and a status move.
const dayBefore = { "10.24.8.33": ["Timeout", null], "10.24.8.42": ["Active", 4.1], "10.24.8.81": ["Active", 6.0] };

let scans = structuredClone(seeds);
let records = new Map();

function scanRows(scan) {
  if (records.has(scan.id)) return records.get(scan.id);
  const rows = hosts.slice(0, scan.total).map(([ip, hostname, status, latency], index) => {
    if (scan.id === 23 && dayBefore[ip]) {
      const [priorStatus, priorLatency] = dayBefore[ip];
      return { ip, hostname, status: priorStatus, latency: priorLatency, checked_at: scan.started_at };
    }
    const isPrior = scan.id !== 24 && index === 17 ? "Timeout" : status;
    const adjusted = latency == null ? null : Number((latency * (1 + (24 - scan.id) * 0.05)).toFixed(1));
    return { ip, hostname, status: isPrior, latency: isPrior === "Active" ? adjusted : null, checked_at: scan.started_at };
  });
  records.set(scan.id, rows);
  return rows;
}

// What `ipmg --snmp` polled on the branch-office scans: the gateway's backup
// WAN link is down in #24, so comparing #23 with #24 shows "Interface down".
function snmpDevices(scan) {
  const day = scan.id - 21;
  const port = (if_index, name, alias, oper, speed, traffic) => ({ if_index, name, description: name, alias, admin_status: "up", oper_status: oper, speed_mbps: speed, in_octets: traffic * (day + 1), out_octets: Math.round(traffic * 0.4) * (day + 1) });
  return [
    { ip: "10.24.8.1", ok: true, version: "2c", sys_name: "gateway-bom-01", sys_descr: "Cisco IOS XE Software, ISR4331, Version 17.9.4a", sys_object_id: "1.3.6.1.4.1.9.1.1861", sys_location: "Mumbai branch, rack A2", uptime_s: 3801600 + day * 86400, response_ms: 3.1, failure: "", error: "", polled_at: scan.started_at,
      interfaces: [port(1, "Gi0/0/0", "WAN uplink", "up", 1000, 912345678901), port(2, "Gi0/0/1", "LAN core", "up", 1000, 523456789012), port(3, "Gi0/0/2", "Backup WAN", scan.id === 24 ? "down" : "up", 100, 1234567890)] },
    { ip: "10.24.8.21", ok: true, version: "2c", sys_name: "reception-ap-01", sys_descr: "ArubaOS (MODEL: 515), Version 8.10.0.6", sys_object_id: "1.3.6.1.4.1.14823.1.2.111", sys_location: "Reception", uptime_s: 1209600 + day * 86400, response_ms: 5.4, failure: "", error: "", polled_at: scan.started_at,
      interfaces: [port(1, "eth0", "", "up", 2500, 45678901234), port(2, "radio0", "2.4 GHz", "up", 573, 3456789012), port(3, "radio1", "5 GHz", "up", 2402, 34567890123)] },
  ];
}

function csv(rows) {
  return ["IP Address,Hostname,Status,Latency,Checked", ...rows.map((r) => [r.ip, r.hostname, r.status, r.latency ?? "", r.checked_at].map((v) => `\"${String(v).replaceAll("\"", "\"\"")}\"`).join(","))].join("\n");
}

function statusCounts(rows) { return rows.reduce((out, row) => ({ ...out, [row.status]: (out[row.status] || 0) + 1 }), {}); }

// Schedules the demo page can create and pause; they never run.
let schedules = [
  { id: 1, name: "branch-office", source: "schedule:branch-office", targets: "10.24.8.0/27", interval_minutes: 15, cron: null, paused: false, created_at: "2026-08-01 09:00", next_run_at: "2026-08-07 09:55", last_run_at: "2026-08-07 09:40", last_scan_id: 24, last_status: "complete", last_skipped_at: null, last_skip_reason: null, config: {} },
];

export const demo = {
  schedules: () => schedules,
  createSchedule: (payload) => {
    const schedule = { id: Math.max(0, ...schedules.map((s) => s.id)) + 1, source: `schedule:${payload.name}`, paused: false, created_at: "2026-08-07 10:05", next_run_at: payload.cron ? "2026-08-07 11:00" : "2026-08-07 10:05", last_run_at: null, last_scan_id: null, last_status: null, last_skipped_at: null, last_skip_reason: null, config: {}, cron: null, interval_minutes: null, ...payload };
    schedules = [...schedules, schedule];
    return schedule;
  },
  pauseSchedule: (id, paused) => { schedules = schedules.map((s) => (s.id === id ? { ...s, paused, next_run_at: paused ? null : s.next_run_at || "2026-08-07 10:05" } : s)); return schedules.find((s) => s.id === id); },
  runSchedule: (id) => ({ id: demo.startScan({ targets: schedules.find((s) => s.id === id)?.targets || "", source: "demo schedule" }).id, total: 0 }),
  deleteSchedule: (id) => { schedules = schedules.filter((s) => s.id !== id); return null; },
  stats: () => ({ scan_count: scans.length, host_count: hosts.length, latest_scan: scans[0], running_scans: [], trend: [...scans].reverse().map((s) => ({ ...s, active: s.status_counts.Active || 0 })) }),
  snmp: (id) => { const scan = demo.scan(id); return scan && scan.source === "branch-office.csv" ? snmpDevices(scan) : []; },
  assets: () => hosts.map(([ip, hostname, status, latency], index) => ({ ip, hostname, status, snmp_name: { "10.24.8.1": "gateway-bom-01", "10.24.8.21": "reception-ap-01" }[ip] || null, avg_latency: latency, last_seen: status === "Active" ? "2026-08-07 09:40" : null, last_checked: "2026-08-07 09:40", scan_count: index < 16 ? 4 : 3 })),
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
  wake: (mac) => ({ mac, broadcast: "255.255.255.255", port: 9 }),
  upload: async (file) => ({ filename: file.name, count: (await file.text()).split(/\r?\n/).filter(Boolean).length, targets: (await file.text()).split(/\r?\n/).filter(Boolean) }),
  reportUrl: (id) => `data:text/csv;charset=utf-8,${encodeURIComponent(csv(demo.results(id)))}`,
  diff: (id, { baseline } = {}) => {
    const current = demo.results(id); const previous = demo.results(baseline || scans.find((s) => s.id !== Number(id)).id);
    const before = new Map(previous.map((row) => [row.ip, row]));
    const changes = current.flatMap((row) => { const old = before.get(row.ip); if (!old) return [{ severity: "warning", label: "New host", ip: row.ip, hostname: row.hostname, previous: null, current: row.status }]; if (old.status !== row.status) { const [severity, label] = old.status === "Active" ? ["critical", "Host offline"] : row.status === "Active" ? ["info", "Host back online"] : ["warning", "Status changed"]; return [{ severity, label, ip: row.ip, hostname: row.hostname, previous: old.status, current: row.status }]; } if (row.latency && old.latency && Math.abs(row.latency - old.latency) >= 5) return [{ severity: "info", label: "Latency changed", ip: row.ip, hostname: row.hostname, previous: `${old.latency} ms`, current: `${row.latency} ms`, delta: row.latency - old.latency }]; return []; });
    if (Number(id) === 24 && Number(baseline || 23) === 23) changes.push({ severity: "warning", label: "Interface down", ip: "10.24.8.1", hostname: "gateway-bom-01", previous: null, current: "Gi0/0/2 (Backup WAN)" });
    return { changes, summary: { total_changes: changes.length, severity_counts: statusCounts(changes.map((c) => ({ status: c.severity }))), unchanged_hosts: current.length - changes.length, baseline_hosts: previous.length, current_hosts: current.length } };
  },
  diffReportUrl: (id, _fmt, options) => `data:text/csv;charset=utf-8,${encodeURIComponent(csv(demo.results(id, options)))}`,
};
