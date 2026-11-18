"""Availability report for one host, as Markdown, JSON, or CSV."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from typing import Any

from ipmg.exceptions import ReportError
from ipmg.utils.helpers import markdown_cell, spreadsheet_escape

AVAILABILITY_FORMATS = ("md", "json", "csv")

AVAILABILITY_MEDIA_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "csv": "text/csv; charset=utf-8",
}


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    seconds = int(round(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    parts = [
        f"{days}d" if days else "",
        f"{hours}h" if hours else "",
        f"{minutes}m" if minutes else "",
    ]
    text = " ".join(part for part in parts if part)
    return text or f"{secs}s"


def _cell(value: object) -> str:
    """A Markdown table cell: one line, so a newline cannot start a heading or a new row."""
    return markdown_cell(" ".join(str(value).split()))


def _value(value: Any, unit: str = "") -> str:
    return "n/a" if value is None else f"{value}{unit}"


def _headline(health: dict[str, Any]) -> list[tuple[str, str]]:
    latency, outages = health["latency"], health["outages"]
    return [
        ("Availability", _value(health["availability_pct"], "%")),
        ("Checks", f"{health['checks']} ({health['up']} up, {health['down']} down)"),
        ("Excluded for maintenance", str(health["excluded"])),
        ("Latency P50", _value(latency["p50"], " ms")),
        ("Latency P95", _value(latency["p95"], " ms")),
        ("Latency P99", _value(latency["p99"], " ms")),
        ("Outages", f"{outages['count']} ({outages['ongoing']} ongoing)"),
        ("Downtime", _duration(outages["downtime_s"])),
        ("Longest outage", _duration(outages["longest_s"])),
        ("MTTR", _duration(outages["mttr_s"])),
        ("MTBF", _duration(outages["mtbf_s"])),
    ]


def _sla_line(sla: dict[str, Any] | None) -> str:
    if sla is None:
        return "No SLA target is set."
    met = {True: "met", False: "NOT met", None: "no data"}[sla["availability_met"]]
    text = f"Availability target {sla['availability_target']}%: {met}."
    if sla["latency_p95_ms"] is not None:
        latency = {True: "met", False: "NOT met", None: "no data"}[sla["latency_met"]]
        text += f" P95 limit {sla['latency_p95_ms']} ms: {latency}."
    return text


def availability_to_json(health: dict[str, Any]) -> str:
    return json.dumps(health, indent=2)


def availability_to_markdown(health: dict[str, Any]) -> str:
    window = health["window"]
    lines = [
        f"# Availability report: {_cell(health['ip'])}",
        "",
        f"{window['starts_at']} to {window['ends_at']} ({window['days']} days)"
        + (f", source: {_cell(health['source'])}" if health["source"] else ""),
        "",
        f"_{health['note']}_",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *(f"| {name} | {value} |" for name, value in _headline(health)),
        "",
        "## SLA",
        "",
        _sla_line(health["sla"]),
        "",
    ]
    violations = (health["sla"] or {}).get("violations", [])
    if violations:
        lines += ["| Day | Kind | Observed | Target |", "| --- | --- | --- | --- |"]
        lines += [
            f"| {v['date']} | {v['kind']} | {v['observed']} | {v['target']} |" for v in violations
        ]
        lines.append("")

    lines += ["## Outages", ""]
    if health["outage_list"]:
        lines += ["| Started | Ended | Duration | Failed checks |", "| --- | --- | --- | --- |"]
        lines += [
            f"| {o['started_at']} | {o['ended_at'] or 'ongoing'} | {_duration(o['duration_s'])} "
            f"| {o['checks']} |"
            for o in health["outage_list"]
        ]
        if health["outages_truncated"]:
            lines += ["", "Only the most recent outages are listed."]
    else:
        lines.append("No outages observed.")

    lines += ["", "## Maintenance windows", ""]
    if health["maintenance"]:
        lines += ["| From | To | Applies to | Reason |", "| --- | --- | --- | --- |"]
        lines += [
            f"| {m['starts_at']} | {m['ends_at']} | {_cell(m['ip'] or 'all hosts')} "
            f"| {_cell(m['reason'])} |"
            for m in health["maintenance"]
        ]
    else:
        lines.append("None in this period.")

    lines += ["", "## By day", ""]
    if health["daily"]:
        lines += [
            "| Day | Checks | Up | Availability | P95 latency |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {d['date']} | {d['checks']} | {d['up']} | {_value(d['availability_pct'], '%')} "
            f"| {_value(d['latency_p95'], ' ms')} |"
            for d in health["daily"]
        ]
    else:
        lines.append("No checks in this period.")
    return "\n".join(lines) + "\n"


def availability_to_csv(health: dict[str, Any]) -> str:
    """Blocks separated by a blank row: summary, outages, SLA violations, maintenance, days."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    def cells(*values: Any) -> list[str]:
        return [spreadsheet_escape("" if value is None else value) for value in values]

    window = health["window"]
    writer.writerow(["Metric", "Value"])
    writer.writerow(cells("IP Address", health["ip"]))
    writer.writerow(cells("From", window["starts_at"]))
    writer.writerow(cells("To", window["ends_at"]))
    writer.writerow(cells("Source", health["source"] or "all"))
    for name, value in _headline(health):
        writer.writerow(cells(name, value))
    writer.writerow(cells("SLA", _sla_line(health["sla"])))
    writer.writerow(cells("Note", health["note"]))

    writer.writerow([])
    writer.writerow(["Outage Started", "Outage Ended", "Duration (s)", "Failed Checks", "Ongoing"])
    for o in health["outage_list"]:
        writer.writerow(
            cells(o["started_at"], o["ended_at"], o["duration_s"], o["checks"], o["ongoing"])
        )

    writer.writerow([])
    writer.writerow(["SLA Violation Day", "Kind", "Observed", "Target"])
    for v in (health["sla"] or {}).get("violations", []):
        writer.writerow(cells(v["date"], v["kind"], v["observed"], v["target"]))

    writer.writerow([])
    writer.writerow(["Maintenance From", "Maintenance To", "Applies To", "Reason"])
    for m in health["maintenance"]:
        writer.writerow(cells(m["starts_at"], m["ends_at"], m["ip"] or "all hosts", m["reason"]))

    writer.writerow([])
    writer.writerow(["Day", "Checks", "Up", "Availability (%)", "P95 Latency (ms)"])
    for d in health["daily"]:
        writer.writerow(
            cells(d["date"], d["checks"], d["up"], d["availability_pct"], d["latency_p95"])
        )
    return buffer.getvalue()


_RENDERERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "md": availability_to_markdown,
    "json": availability_to_json,
    "csv": availability_to_csv,
}


def render_availability(health: dict[str, Any], fmt: str) -> str:
    try:
        return _RENDERERS[fmt](health)
    except KeyError:
        raise ReportError(
            f"Unsupported format: {fmt}. Supported: {', '.join(AVAILABILITY_FORMATS)}."
        ) from None
