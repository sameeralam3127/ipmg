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

// What every scan recorded for one address, oldest first.
function hostHistory(ip) {
  return [...scans].reverse().flatMap((scan) => {
    const row = scanRows(scan).find((candidate) => candidate.ip === ip);
    return row ? [{ ...row, scan_id: scan.id, started_at: scan.started_at, source: scan.source, scan_status: scan.status, open_ports: "", method: "", mac: row.mac || "", vendor: row.vendor || "" }] : [];
  });
}

function notSeen() {
  const error = new Error("No scan has recorded this address");
  error.status = 404;
  return error;
}


// ---- host health (the demo's own small version of the server's maths)

const demoTime = (text) => new Date(`${text.replace(" ", "T")}${text.length === 16 ? ":00" : ""}`);
const demoStamp = (date) => {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};
const quantile = (values, q) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const low = Math.floor(pos);
  const high = Math.ceil(pos);
  return Number((sorted[low] + (sorted[high] - sorted[low]) * (pos - low)).toFixed(2));
};

let maintenanceWindows = [];
let slaTargets = {};

function demoHealth(ip, days) {
  const asset = demo.assets().find((candidate) => candidate.ip === ip);
  if (!asset) throw notSeen();
  const rows = hostHistory(ip);
  const end = demoTime(rows[rows.length - 1].checked_at);
  const start = new Date(end.getTime() - days * 86400000);
  const windows = maintenanceWindows.filter((w) => w.ip === null || w.ip === ip);
  const inWindow = (date) => windows.some((w) => demoTime(w.starts_at) <= date && date < demoTime(w.ends_at));
  const all = rows.map((row) => ({ ...row, at: demoTime(row.checked_at) })).filter((row) => row.at >= start && row.at <= end);
  const counted = all.filter((row) => !inWindow(row.at));
  const up = counted.filter((row) => row.status === "Active");
  const outages = [];
  let open = null;
  let failed = 0;
  for (const row of counted) {
    if (row.status !== "Active") { if (!open) { open = row; failed = 0; } failed += 1; }
    else if (open) { outages.push({ started_at: open.checked_at, ended_at: row.checked_at, duration_s: (row.at - open.at) / 1000, checks: failed, ongoing: false }); open = null; }
  }
  if (open) outages.push({ started_at: open.checked_at, ended_at: null, duration_s: (counted[counted.length - 1].at - open.at) / 1000, checks: failed, ongoing: true });
  const recovered = outages.filter((o) => !o.ongoing);
  const downtime = outages.reduce((n, o) => n + o.duration_s, 0);
  const span = counted.length ? (counted[counted.length - 1].at - counted[0].at) / 1000 : 0;
  const latencies = up.map((row) => row.latency).filter((v) => v != null);
  const byDay = new Map();
  for (const row of counted) byDay.set(row.checked_at.slice(0, 10), [...(byDay.get(row.checked_at.slice(0, 10)) || []), row]);
  const daily = [...byDay].sort(([a], [b]) => a.localeCompare(b)).map(([date, group]) => {
    const ok = group.filter((row) => row.status === "Active");
    return { date, checks: group.length, up: ok.length, availability_pct: Number(((ok.length * 100) / group.length).toFixed(4)), latency_p95: quantile(ok.map((row) => row.latency).filter((v) => v != null), 0.95) };
  });
  const availability = counted.length ? Number(((up.length * 100) / counted.length).toFixed(4)) : null;
  const target = slaTargets[ip];
  const sla = target && {
    availability_target: target.availability_target,
    latency_p95_ms: target.latency_p95_ms ?? null,
    availability_met: availability == null ? null : availability >= target.availability_target,
    latency_met: target.latency_p95_ms == null || quantile(latencies, 0.95) == null ? null : quantile(latencies, 0.95) <= target.latency_p95_ms,
    violations: daily.flatMap((day) => [
      ...(day.availability_pct < target.availability_target ? [{ date: day.date, kind: "availability", observed: day.availability_pct, target: target.availability_target }] : []),
      ...(target.latency_p95_ms != null && day.latency_p95 > target.latency_p95_ms ? [{ date: day.date, kind: "latency", observed: day.latency_p95, target: target.latency_p95_ms }] : []),
    ]),
  };
  return {
    ip, window: { starts_at: demoStamp(start), ends_at: demoStamp(end), days }, source: null,
    sources: [...new Set(all.map((row) => row.source))].sort(),
    checks: counted.length, up: up.length, down: counted.length - up.length, excluded: all.length - counted.length,
    availability_pct: availability,
    latency: { count: latencies.length, min: latencies.length ? Math.min(...latencies) : null, mean: latencies.length ? Number((latencies.reduce((n, v) => n + v, 0) / latencies.length).toFixed(2)) : null, p50: quantile(latencies, 0.5), p95: quantile(latencies, 0.95), p99: quantile(latencies, 0.99), max: latencies.length ? Math.max(...latencies) : null },
    outages: { count: outages.length, recovered: recovered.length, ongoing: outages.length - recovered.length, downtime_s: downtime, longest_s: Math.max(0, ...outages.map((o) => o.duration_s)), mttr_s: recovered.length ? recovered.reduce((n, o) => n + o.duration_s, 0) / recovered.length : null, mtbf_s: outages.length ? Math.max(span - downtime, 0) / outages.length : null },
    outage_list: [...outages].reverse(), outages_truncated: false, daily, sla,
    maintenance: windows, note: "Observed from scans, not a continuous probe: an outage between two scans is not seen, and durations have the resolution of the scan interval.",
  };
}

export const demo = {
  host: (ip) => {
    const asset = demo.assets().find((candidate) => candidate.ip === ip);
    if (!asset) throw notSeen();
    const active = hostHistory(ip).filter((row) => row.status === "Active");
    return { ...asset, mac: null, vendor: null, snmp_descr: null, first_seen: active[0]?.checked_at || null, last_scan_id: scans[0].id };
  },
  health: demoHealth,
  maintenance: (ip) => maintenanceWindows.filter((w) => w.ip === null || w.ip === ip),
  addMaintenance: (payload) => {
    const starts = demoTime(payload.starts_at.replace("T", " "));
    const ends = demoTime(payload.ends_at.replace("T", " "));
    if (Number.isNaN(starts.getTime()) || Number.isNaN(ends.getTime())) throw new Error("Not a time (use YYYY-MM-DD HH:MM)");
    if (ends <= starts) throw new Error("A maintenance window must end after it starts.");
    const window = { id: Math.max(0, ...maintenanceWindows.map((w) => w.id)) + 1, ip: payload.ip || null, starts_at: demoStamp(starts), ends_at: demoStamp(ends), reason: (payload.reason || "").trim(), created_at: demoStamp(new Date()) };
    maintenanceWindows = [...maintenanceWindows, window];
    return window;
  },
  deleteMaintenance: (id) => { maintenanceWindows = maintenanceWindows.filter((w) => w.id !== id); return null; },
  setSla: (ip, payload) => { slaTargets = { ...slaTargets, [ip]: { ip, ...payload } }; return slaTargets[ip]; },
  clearSla: (ip) => { const { [ip]: _removed, ...rest } = slaTargets; slaTargets = rest; return null; },
  availabilityReportUrl: (ip, _fmt, days) => `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(demoHealth(ip, days), null, 2))}`,
  hostResults: (ip) => hostHistory(ip).reverse(),
  hostChanges: (ip) => {
    const rows = hostHistory(ip);
    return rows.flatMap((row, index) => {
      const before = rows.slice(0, index).reverse().find((earlier) => earlier.source === row.source);
      if (!before) return [];
      const base = { ip, hostname: row.hostname, scan_id: row.scan_id, baseline_id: before.scan_id, started_at: row.started_at, source: row.source, delta: null };
      if (before.status !== row.status) {
        const online = row.status === "Active";
        return [{ ...base, type: online ? "host_online" : "host_offline", label: online ? "Host back online" : "Host offline", severity: online ? "info" : "critical", previous: before.status, current: row.status }];
      }
      if (row.latency && before.latency && Math.abs(row.latency - before.latency) >= 5) {
        return [{ ...base, type: "latency_changed", label: "Latency changed", severity: "info", previous: `${before.latency} ms`, current: `${row.latency} ms`, delta: row.latency - before.latency }];
      }
      return [];
    }).reverse();
  },
  hostSnmp: (ip) => [...scans].filter((scan) => scan.source === "branch-office.csv").flatMap((scan) => snmpDevices(scan).filter((device) => device.ip === ip).map((device) => ({ ...device, scan_id: scan.id }))),
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
