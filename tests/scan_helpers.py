"""Shared helpers for tests that drive :func:`ipmg.services.scan_service.run_scan`."""

from types import SimpleNamespace


def scan_args(tmp_path, **overrides):
    args = dict(
        input=["targets.csv"],
        output=str(tmp_path / "results"),
        timeout=1,
        count=1,
        threads=2,
        formats=[],
        discover=False,
        resolve=False,
        interval=None,
        history=True,
        compare=False,
        compare_any_source=False,
        db=str(tmp_path / "history.db"),
        diff_formats=[],
        diff_output=str(tmp_path / "changes"),
        latency_threshold=5.0,
        latency_pct=25.0,
    )
    args.update(overrides)
    return SimpleNamespace(**args)
