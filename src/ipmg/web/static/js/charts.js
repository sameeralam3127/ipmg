// Hand-rolled SVG charts: status donut and latency trend. No libraries.

const SVG_NS = "http://www.w3.org/2000/svg";

// Fixed status order — the CVD-validated adjacency for donut segments.
export const STATUS_ORDER = [
  "Active",
  "Timeout",
  "Inactive",
  "Error",
  "Unreachable",
  "Invalid IP",
];

export const STATUS_COLORS = {
  Active: "var(--st-active)",
  Timeout: "var(--st-timeout)",
  Inactive: "var(--st-inactive)",
  Error: "var(--st-error)",
  Unreachable: "var(--st-unreachable)",
  "Invalid IP": "var(--st-invalid)",
};

function el(name, attrs = {}) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

const tooltip = () => document.getElementById("tooltip");

export function showTooltip(evt, title, sub) {
  const tip = tooltip();
  if (!tip) return;
  tip.innerHTML = "";
  const titleEl = document.createElement("div");
  titleEl.className = "t-title";
  titleEl.textContent = title;
  tip.appendChild(titleEl);
  if (sub) {
    const subEl = document.createElement("div");
    subEl.className = "t-sub";
    subEl.textContent = sub;
    tip.appendChild(subEl);
  }
  tip.hidden = false;
  const pad = 12;
  const rect = tip.getBoundingClientRect();
  let x = evt.clientX + pad;
  let y = evt.clientY + pad;
  if (x + rect.width > window.innerWidth - pad) x = evt.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight - pad) y = evt.clientY - rect.height - pad;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}

export function hideTooltip() {
  const tip = tooltip();
  if (tip) tip.hidden = true;
}

/**
 * Donut of status counts with a centered total, plus a legend listing every
 * status with its count (identity is never carried by color alone).
 */
export function statusDonut(counts, { centerLabel = "hosts" } = {}) {
  const entries = STATUS_ORDER.filter((status) => counts[status] > 0).map(
    (status) => [status, counts[status]]
  );
  const total = entries.reduce((sum, [, count]) => sum + count, 0);

  const size = 160;
  const radius = 62;
  const stroke = 22;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;

  const svg = el("svg", {
    viewBox: `0 0 ${size} ${size}`,
    width: size,
    height: size,
    role: "img",
    "aria-label": `Status distribution for ${total} hosts`,
  });

  if (total === 0) {
    const track = el("circle", {
      cx: center,
      cy: center,
      r: radius,
      fill: "none",
      stroke: "var(--grid)",
      "stroke-width": stroke,
    });
    svg.appendChild(track);
  }

  let offset = -circumference / 4; // start at 12 o'clock
  for (const [status, count] of entries) {
    const fraction = count / total;
    const arc = el("circle", {
      cx: center,
      cy: center,
      r: radius,
      fill: "none",
      stroke: STATUS_COLORS[status] || "var(--st-invalid)",
      "stroke-width": stroke,
      "stroke-dasharray": `${fraction * circumference} ${circumference}`,
      "stroke-dashoffset": -offset,
      // 2px surface gap between segments
      "stroke-linecap": "butt",
    });
    const gap = el("circle", {
      cx: center,
      cy: center,
      r: radius,
      fill: "none",
      stroke: "var(--surface)",
      "stroke-width": stroke + 2,
      "stroke-dasharray": `2 ${circumference - 2}`,
      "stroke-dashoffset": -offset,
    });
    arc.addEventListener("mousemove", (evt) =>
      showTooltip(evt, `${status}: ${count}`, `${((count / total) * 100).toFixed(1)}% of ${total}`)
    );
    arc.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(arc);
    if (entries.length > 1) svg.appendChild(gap);
    offset += fraction * circumference;
  }

  const value = el("text", {
    x: center,
    y: center - 2,
    "text-anchor": "middle",
    class: "donut-center-value",
  });
  value.textContent = String(total);
  const label = el("text", {
    x: center,
    y: center + 16,
    "text-anchor": "middle",
    class: "donut-center-label",
  });
  label.textContent = centerLabel;
  svg.append(value, label);

  const legend = document.createElement("div");
  legend.className = "legend";
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "legend-item";
    empty.textContent = "No results yet";
    legend.appendChild(empty);
  }
  for (const [status, count] of entries) {
    const item = document.createElement("div");
    item.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = STATUS_COLORS[status];
    const name = document.createElement("span");
    name.textContent = status;
    const countEl = document.createElement("span");
    countEl.className = "count";
    countEl.textContent = String(count);
    item.append(swatch, name, countEl);
    legend.appendChild(item);
  }

  const wrap = document.createElement("div");
  wrap.className = "chart-row";
  wrap.append(svg, legend);
  return wrap;
}

/**
 * Single-series trend line (average active latency per completed scan).
 * One axis, hairline grid, hover dots with tooltips, last point labeled.
 */
export function latencyTrend(points) {
  const data = points.filter((point) => point.avg_latency != null);
  const width = 460;
  const height = 170;
  const margin = { top: 14, right: 44, bottom: 22, left: 40 };

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    width: "100%",
    role: "img",
    "aria-label": "Average latency per scan",
    preserveAspectRatio: "xMidYMid meet",
  });

  if (data.length < 2) {
    const note = el("text", {
      x: width / 2,
      y: height / 2,
      "text-anchor": "middle",
      class: "axis-label",
    });
    note.textContent = "Run two or more scans to see the latency trend.";
    svg.appendChild(note);
    return svg;
  }

  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const maxY = Math.max(...data.map((point) => point.avg_latency)) * 1.15 || 1;

  const x = (index) => margin.left + (index / (data.length - 1)) * plotW;
  const y = (value) => margin.top + plotH - (value / maxY) * plotH;

  for (let tick = 0; tick <= 3; tick += 1) {
    const value = (maxY / 3) * tick;
    const gy = y(value);
    svg.appendChild(
      el("line", { x1: margin.left, y1: gy, x2: width - margin.right, y2: gy, class: "gridline" })
    );
    const tickLabel = el("text", {
      x: margin.left - 6,
      y: gy + 3.5,
      "text-anchor": "end",
      class: "axis-label",
    });
    tickLabel.textContent = value >= 10 ? Math.round(value) : value.toFixed(1);
    svg.appendChild(tickLabel);
  }

  const path = data
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(point.avg_latency).toFixed(1)}`)
    .join(" ");
  svg.appendChild(el("path", { d: path, class: "trend-line" }));

  data.forEach((point, index) => {
    const dot = el("circle", {
      cx: x(index),
      cy: y(point.avg_latency),
      r: 4,
      class: "trend-dot",
    });
    const hit = el("circle", {
      cx: x(index),
      cy: y(point.avg_latency),
      r: 11,
      fill: "transparent",
    });
    hit.addEventListener("mousemove", (evt) =>
      showTooltip(
        evt,
        `${point.avg_latency.toFixed(1)} ms avg`,
        `Scan #${point.id} — ${point.started_at} — ${point.active}/${point.total} active`
      )
    );
    hit.addEventListener("mouseleave", hideTooltip);
    svg.append(dot, hit);
  });

  const last = data[data.length - 1];
  const lastLabel = el("text", {
    x: x(data.length - 1) + 8,
    y: y(last.avg_latency) + 4,
    class: "trend-label",
  });
  lastLabel.textContent = `${last.avg_latency.toFixed(1)} ms`;
  svg.appendChild(lastLabel);

  const axisTitle = el("text", {
    x: margin.left,
    y: height - 6,
    class: "axis-label",
  });
  axisTitle.textContent = `Avg active latency (ms), last ${data.length} scans`;
  svg.appendChild(axisTitle);

  return svg;
}
