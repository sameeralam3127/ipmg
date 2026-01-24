from datetime import datetime

import pandas as pd

from ipmg.core.ping import validate_ip


def load_ip_file(path: str) -> list[str]:
    df = pd.read_excel(path)
    return [ip for ip in df["IP Address"].astype(str) if validate_ip(ip)]


def create_sample_file(path: str) -> None:
    df = pd.DataFrame({"IP Address": ["8.8.8.8", "1.1.1.1"]})
    df.to_excel(path, index=False)


def save_results(df, base: str, formats: list[str]) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for fmt in formats:
        if fmt == "xlsx":
            df.to_excel(f"{base}_{ts}.xlsx", index=False)
        elif fmt == "csv":
            df.to_csv(f"{base}_{ts}.csv", index=False)
        elif fmt == "json":
            df.to_json(f"{base}_{ts}.json", orient="records")
