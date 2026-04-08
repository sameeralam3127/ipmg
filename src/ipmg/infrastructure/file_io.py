from pathlib import Path
from typing import Iterable

import pandas as pd
from rich.panel import Panel

from ipmg.exceptions import FileIOError
from ipmg.core.ping import validate_ip
from ipmg.utils.helpers import console, timestamp_str


SUPPORTED_INPUT_SUFFIXES = {".xlsx", ".xls", ".csv", ".txt", ".list"}


def _deduplicate(targets: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(targets))


def _expand_cidr(target: str) -> list[str]:
    try:
        network = pd.notna(target) and target.strip()
        if not network:
            return []

        import ipaddress

        parsed = ipaddress.ip_network(target, strict=False)
    except ValueError as exc:
        raise FileIOError(f"Unsupported target input: {target}") from exc

    if parsed.num_addresses == 1:
        return [str(parsed.network_address)]

    return [str(ip) for ip in parsed.hosts()]


def _load_from_dataframe(df: pd.DataFrame, source: str) -> list[str]:
    if "IP Address" not in df.columns:
        raise FileIOError(f"Input file '{source}' must contain an 'IP Address' column.")

    targets: list[str] = []
    for raw_value in df["IP Address"].dropna().astype(str):
        value = raw_value.strip()
        if not value:
            continue
        if validate_ip(value):
            targets.append(value)
        elif "/" in value:
            targets.extend(_expand_cidr(value))

    if not targets:
        raise FileIOError(f"No valid IP targets were found in '{source}'.")

    return _deduplicate(targets)


def _load_from_text(path: str) -> list[str]:
    targets: list[str] = []
    with open(path, encoding="utf-8") as handle:
        for raw_line in handle:
            value = raw_line.strip()
            if not value or value.startswith("#"):
                continue
            if validate_ip(value):
                targets.append(value)
            elif "/" in value:
                targets.extend(_expand_cidr(value))

    if not targets:
        raise FileIOError(f"No valid IP targets were found in '{path}'.")

    return _deduplicate(targets)


def load_targets(source: str) -> list[str]:
    path = Path(source)

    if path.exists():
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            return _load_from_dataframe(pd.read_excel(path), source)
        if suffix == ".csv":
            return _load_from_dataframe(pd.read_csv(path), source)
        if suffix in {".txt", ".list"}:
            return _load_from_text(source)
        raise FileIOError(
            f"Unsupported input file type '{suffix or '<none>'}'. "
            f"Supported types: {', '.join(sorted(SUPPORTED_INPUT_SUFFIXES))}."
        )

    value = source.strip()
    if validate_ip(value):
        return [value]
    if "/" in value:
        return _expand_cidr(value)

    raise FileIOError(
        f"Input '{source}' is neither a readable file nor a valid IP/CIDR target."
    )


def load_ip_file(path: str) -> list[str]:
    return load_targets(path)


def create_sample_file(path: str) -> None:
    df = pd.DataFrame({"IP Address": ["8.8.8.8", "1.1.1.1"]})
    suffix = Path(path).suffix.lower()

    if suffix == ".csv":
        df.to_csv(path, index=False)
        return

    if suffix in {".txt", ".list"}:
        Path(path).write_text("8.8.8.8\n1.1.1.1\n", encoding="utf-8")
        return

    df.to_excel(path, index=False)


def save_results(df, base: str, formats: list[str]) -> list[str]:
    ts = timestamp_str()
    saved_paths: list[str] = []

    for fmt in formats:
        if fmt == "xlsx":
            output_path = f"{base}_{ts}.xlsx"
            df.to_excel(output_path, index=False)
        elif fmt == "csv":
            output_path = f"{base}_{ts}.csv"
            df.to_csv(output_path, index=False)
        elif fmt == "json":
            output_path = f"{base}_{ts}.json"
            df.to_json(output_path, orient="records")
        else:
            continue

        saved_paths.append(output_path)

    if saved_paths:
        console.print(
            Panel.fit(
                "\n".join(f"[success]-[/success] {path}" for path in saved_paths),
                title="[success]Saved Reports[/success]",
                border_style="success",
            )
        )

    return saved_paths
