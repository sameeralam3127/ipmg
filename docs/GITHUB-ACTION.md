# IPMG in GitHub Actions

This repository is also a GitHub Action: a pipeline step that checks your
infrastructure is reachable and fails the job when it is not. It installs IPMG
with uv, scans, writes a summary of the hosts that are down to the job page,
and uploads the reports as an artifact, even when the step fails.

Before a deploy:

```yaml
- name: Check the database and cache hosts are up
  uses: sameeralam3127/ipmg@vX.Y.Z      # any IPMG release tag
  with:
    targets: 10.0.4.10 10.0.4.11 10.0.5.0/28
    fail-on-down: true
    args: --probe icmp,tcp --ports 5432,6379
```

On a schedule, with the reports kept and a Slack alert for changes (the
history lives in the cached database):

```yaml
on:
  schedule: [{ cron: "*/30 * * * *" }]
jobs:
  reachability:
    runs-on: [self-hosted, office-lan]
    steps:
      - uses: actions/checkout@v7
      - uses: actions/cache@v6
        with: { path: ipmg-history, key: "ipmg-${{ github.run_id }}", restore-keys: ipmg- }
      - uses: sameeralam3127/ipmg@vX.Y.Z
        with:
          targets: targets.txt
          args: --db ipmg-history/history.db --compare --notify-slack
          formats: csv md
        env:
          IPMG_NOTIFY_SLACK: ${{ secrets.SLACK_WEBHOOK }}
```

| Input | Default | Meaning |
| --- | --- | --- |
| `targets` | (required) | IPs, CIDR blocks, ranges, or target files, separated by spaces or newlines |
| `args` | | Extra IPMG flags, split on whitespace |
| `version` | `latest` | The IPMG release to install, such as `3.2.0` |
| `fail-on-down` | `false` | Fail the step when any target is not Active |
| `formats` | `csv json md` | Report formats to write |
| `upload-artifact` | `true` | Upload the reports as an artifact |
| `artifact-name` | `ipmg-reports` | The artifact's name |

Outputs: `active` and `total` host counts, `report-path`, and `exit-code`.

GitHub-hosted runners generally cannot ping hosts outside GitHub's network,
and cannot reach your private networks at all. For a LAN or a VPC, use a
[self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners)
inside it; for public hosts that drop ICMP, add `--probe tcp` or `--probe
icmp,tcp` to `args`, or check the service itself with `--http-check`.
