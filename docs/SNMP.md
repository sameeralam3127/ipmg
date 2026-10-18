# SNMP polling

A switch or router usually answers ping, which says little about its health.
`--snmp` asks the devices that answered for what ping cannot tell you: their
name and model, how long they have been up, and the state of every interface.
Kept in the scan history, that becomes change detection for network gear:
**a device rebooted**, **an uplink went down**, **an agent stopped answering**.

```bash
export IPMG_SNMP_COMMUNITY=your-community        # v2c; the default is "public"
ipmg --input switches.txt --snmp                 # poll every switch that answers
ipmg --input switches.txt --snmp --compare --interval 15 --notify-slack   # and watch them
```

> Only poll devices you are authorized to manage. SNMP reads configuration
> details that the device's owner may consider sensitive.

**Contents**

[What is polled](#what-is-polled) ·
[Credentials](#credentials) ·
[SNMPv3](#snmpv3) ·
[Flags](#flags) ·
[Results and reports](#results-and-reports) ·
[Changes](#changes) ·
[IPMG Web](#ipmg-web) ·
[Troubleshooting](#troubleshooting) ·
[How it works](#how-it-works)

---

## What is polled

Only hosts that answered the scan are polled, after the sweep, at most
`--threads` at a time. Add `--probe icmp,tcp` if some of your devices block
ping. For each device, IPMG reads the MIB-II objects every agent has:

| Object | What you get |
| --- | --- |
| `sysName`, `sysDescr`, `sysObjectID`, `sysLocation` | The device's own name, model and software, vendor ID, and location |
| `sysUpTime` | How long the agent has been running; a reboot starts it again from zero |
| `ifTable` and `ifXTable` | Every interface: name (`ifName`, else `ifDescr`), description (`ifAlias`), admin and operational status, speed, and traffic counters (64-bit where the agent has them) |

Interfaces are walked with GETBULK, several columns per request, up to 2,048
per device. `--snmp-no-interfaces` reads only the system group: one request per
device, for very large or very slow agents.

---

## Credentials

Credentials never go on the command line, where they would end up in your
shell history, in process listings, and in the settings stored with each scan.
They come from environment variables or from your own config file, and the
environment wins when both are set:

| Environment variable | `[snmp-credentials]` key | Meaning |
| --- | --- | --- |
| `IPMG_SNMP_COMMUNITY` | `community` | v2c community string (default: `public`) |
| `IPMG_SNMP_USER` | `user` | v3 user name |
| `IPMG_SNMP_AUTH_PROTOCOL` | `auth-protocol` | `MD5`, `SHA` (the default), `SHA224`, `SHA256`, `SHA384`, or `SHA512` |
| `IPMG_SNMP_AUTH_KEY` | `auth-key` | v3 authentication passphrase (at least 8 characters) |
| `IPMG_SNMP_PRIV_PROTOCOL` | `priv-protocol` | `AES` (AES-128, the only one offered) |
| `IPMG_SNMP_PRIV_KEY` | `priv-key` | v3 privacy (encryption) passphrase |
| `IPMG_SNMP_CONTEXT` | `context` | v3 context name, for agents that serve several (a VRF, a VLAN) |

In `~/.config/ipmg/config.toml`, or a file you pass with `--config`:

```toml
snmp = true
snmp-version = "3"

[snmp-credentials]
user = "netops"
auth-protocol = "SHA256"
auth-key = "..."
priv-key = "..."
```

A project's `./ipmg.toml` may set `snmp` and the other flags, but not
`[snmp-credentials]`: that file usually lives next to the code and gets
committed with it, so IPMG refuses it there. Keep the file with your
credentials readable only by you (`chmod 600`).

The scan's Config line says which credentials are in use without showing them:
`community from the environment`, or `user netops, authPriv (SHA256, AES)`.
Community strings and keys never appear in output, logs, reports, or history.

---

## SNMPv3

```bash
export IPMG_SNMP_USER=netops IPMG_SNMP_AUTH_KEY='...' IPMG_SNMP_PRIV_KEY='...'
ipmg --input core.txt --snmp --snmp-version 3
```

The security level follows from what you set: a user alone is
`noAuthNoPriv`, a user and an authentication key `authNoPriv`, and both keys
`authPriv`. IPMG discovers each agent's engine ID, localizes the keys to it
(RFC 3414), authenticates with HMAC-MD5, HMAC-SHA, or the SHA-2 family
(RFC 7860), and encrypts with AES-128 (RFC 3826). DES is not offered: it has
been broken for decades.

Encryption needs the `cryptography` package, from the `snmp` extra:

```bash
pip install "ipmg[snmp]"                          # or "ipmg[web,snmp]", or "ipmg[all]"
uv tool install --force --python ">=3.10" "ipmg[web,snmp]"
```

SNMP v2c and v3 without encryption need nothing extra. Without the package, an
encrypted poll fails with a message that names the extra instead of failing
the scan.

---

## Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `--snmp` | off | Poll every host that answered |
| `--snmp-version 2c\|3` | `2c` | SNMP version |
| `--snmp-port PORT` | `161` | Agent UDP port |
| `--snmp-timeout SECONDS` | `2` | Wait for each answer (0.1-60) |
| `--snmp-retries N` | `1` | Resend an unanswered request up to N times (0-5) |
| `--snmp-no-interfaces` | off | Read only the system group |

Each can be a default in `ipmg.toml` (`snmp = true`, `snmp-timeout = 5`...),
like every other scan flag.

---

## Results and reports

The scan prints an SNMP table after the host summary:

```text
  SNMP
            Host          Name          Uptime      Interfaces  Detail
  ✓ OK      10.0.0.2      core-sw-01    41d 3h  46 up · 1 down  down: Gi1/0/24
  ✓ OK      10.0.0.3      edge-rtr-01    5h 12m   4 up · 0 down  Cisco IOS XE Software, Version 17.9.4a
  ✗ Failed  10.0.0.9      -                  -               -  no SNMP answer within 2s x 2: check that SNMP is enabled and the community string is right

  3 devices · 1 not answering · 1 interface down
```

It is saved beside the host reports, in every `--formats` format:

- `<prefix>_snmp_<timestamp>.<format>`: one row per device, with its result,
  name, description, location, uptime, interface counts, the names of the
  interfaces that are down, and why it failed.
- `<prefix>_snmp_interfaces_<timestamp>.<format>`: one row per interface,
  with status, speed, and traffic counters. The Markdown report lists the
  interfaces that are down instead.

`--keep-reports` prunes both along with the host reports. SNMP results are not
part of `--json` or `--jsonl` on stdout; use `--formats json` for a file.

A device that does not answer is a result, never a failed scan. The failure
says why: `timeout`, `refused` (nothing listening on the port), `auth` (the
agent rejected the user, a key, or the security level), `error` (the agent
returned an error), `protocol` (an unreadable reply), `unsupported` (encryption
without the `snmp` extra), or `network`.

---

## Changes

Polls are stored with the scan, so `--compare`, `ipmg diff`, notifications,
and IPMG Web compare them like hosts:

| Change | Severity | When |
| --- | --- | --- |
| `device_rebooted` | warning | The uptime is lower than at the last poll: the device, or its agent, restarted |
| `interface_down` | warning | An enabled interface that was up stopped passing traffic (`down`, `lowerLayerDown`, `notPresent`) |
| `snmp_failing` | warning | The device still answers the scan, but no longer SNMP |
| `interface_up` | info | That interface is up again |
| `snmp_recovered` | info | The agent answers again |

Only devices and interfaces both scans polled are compared. An interface that
was switched off (admin down) is never reported. `sysUpTime` wraps to zero
every 497 days on its own, so a drop in that window is not reported as a reboot.

On a switch with many access ports, desktops being switched off at night show
up as interfaces going down. To hear only about the serious changes, raise the
threshold with `--notify-severity critical`, or poll such switches with
`--snmp-no-interfaces` and keep the interface checks for the uplinks' devices.

---

## IPMG Web

- A scan's page lists the devices it polled, with uptime and interface counts,
  and each device's full interface table one click away.
- The Inventory has an **SNMP name** column with each host's latest `sysName`
  (hover for its `sysDescr`), and the search covers it.
- The API serves the same data at `GET /api/v1/scans/{id}/snmp`
  (see [API.md](API.md)).

Scans started from IPMG Web do not poll SNMP; run `ipmg --snmp` from the
command line or a service to record it.

---

## Troubleshooting

**Every device times out.** SNMP is usually off until it is configured, and
v2c agents ignore a wrong community string without a word. Check with
net-snmp's tools from the same machine:
`snmpget -v2c -c "$IPMG_SNMP_COMMUNITY" 10.0.0.2 1.3.6.1.2.1.1.5.0`. Also check
that UDP port 161 is open on the path, and that the agent allows your address
(ACLs often allow only the management network).

**v3: "wrong SNMPv3 authentication key or protocol".** The passphrase or
`IPMG_SNMP_AUTH_PROTOCOL` does not match the user on the device.
**"does not allow this security level"**: the user is configured for a
different level, typically `authPriv` while you gave no privacy key.
**A timeout with a privacy key set**: many agents drop a message they cannot
decrypt instead of reporting it; check `IPMG_SNMP_PRIV_KEY`.
**A timeout only with v3**: the agent may expect a context name
(`IPMG_SNMP_CONTEXT`).

**`interfaces not read: ...` in the Detail column.** The device answered for
its system group but not for the interface tables, most often a view (VACM)
that only allows `system`. The rest of the result is kept.

---

## How it works

IPMG has its own small SNMP implementation in `src/ipmg/core/snmp/`: BER
encoding, the v2c and USM message formats, and the MIB-II walk, about a
thousand lines with no dependency for v2c. It is tested against IPMG's own
test agent, and in CI against two independent agents, net-snmp's `snmpd` and
snmpsim (pysnmp), at every security level. Nothing SNMP-related is imported
unless a scan asks for `--snmp`.
