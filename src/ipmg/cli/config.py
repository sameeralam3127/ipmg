"""Default scan options read from an ``ipmg.toml`` file.

Repeating ``--threads 200 --timeout 1 --resolve --formats md csv`` on every run
is what this exists to stop. Any long flag of the scan command can be given a
default in a file instead:

.. code-block:: toml

    threads = 200
    timeout = 1
    resolve = true
    formats = ["md", "csv"]

    [profile.datacenter]
    threads = 400
    scan-ports = true

Files are read from the user's config directory first and the project's
``./ipmg.toml`` on top, so a project can override a global default. The command
line overrides both: a flag that appears on it ignores the file entirely for
that flag, which matters for ``--input``, where the two would otherwise merge.

Defaults reach argparse through :meth:`~argparse.ArgumentParser.set_defaults`,
so a value is checked against the very flag it sets — its ``type``, its
``choices``, and whether it takes a value at all — and an unknown key names
itself and the file it came from.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ipmg.exceptions import ConfigError

if sys.version_info >= (3, 11):  # pragma: no cover - one branch per interpreter
    import tomllib
else:  # pragma: no cover - one branch per interpreter
    import tomli as tomllib

#: The file a project keeps its own defaults in.
PROJECT_CONFIG = "ipmg.toml"
#: Where a user's defaults live, under XDG_CONFIG_HOME or ~/.config.
USER_CONFIG = Path("ipmg") / "config.toml"

#: The table named profiles live in: ``[profile.datacenter]``.
PROFILE_TABLE = "profile"

#: Flags that cannot be defaulted from a file, and why. ``--web`` is picked out
#: of the command line before the parser runs, so a default could never take
#: effect; the rest select the configuration itself.
_NOT_CONFIGURABLE = {
    "config": "it selects the file",
    "no_config": "it selects the file",
    "profile": "it selects the profile",
    "web": "'ipmg web' is a command, not a scan option",
    "help": "it is not a scan option",
    "version": "it is not a scan option",
}

#: Where scan results can be sent. A project's ./ipmg.toml comes with whatever
#: directory you scan from, a cloned repository included, so it may not choose
#: these: it could send your results to an address its author picked. Your own
#: config file and an explicit --config file can.
_NOT_FROM_PROJECT = frozenset(
    {
        "notify_webhook",
        "notify_slack",
        "notify_teams",
        "notify_email",
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_user",
        "smtp_from",
    }
)

#: Sentinel for "this key is valid but should leave the flag's own default
#: alone" — a boolean key set to false, meaning the flag was simply not passed.
_KEEP = object()


def add_config_arguments(parser: argparse.ArgumentParser) -> None:
    """Add ``--config``, ``--no-config``, and ``--profile`` to a parser."""
    group = parser.add_argument_group("configuration file")
    source = group.add_mutually_exclusive_group()
    source.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help=f"Read default options from this file instead of searching for {PROJECT_CONFIG}.",
    )
    source.add_argument(
        "--no-config",
        action="store_true",
        help="Ignore every configuration file and use the built-in defaults.",
    )
    group.add_argument(
        "--profile",
        default=None,
        metavar="NAME",
        help=f"Apply the [{PROFILE_TABLE}.NAME] section of the configuration file.",
    )


def config_help() -> str:
    """The one line ``--help`` carries about where defaults come from."""
    return (
        f"Default options are read from ./{PROJECT_CONFIG}, then "
        f"{_user_config_path()}; flags on the command line override them. "
        "Use --config PATH for another file, --no-config to ignore them, "
        f"and --profile NAME for a [{PROFILE_TABLE}.NAME] section."
    )


def _user_config_path() -> Path:
    """The user-wide config file, honouring ``XDG_CONFIG_HOME`` when it is set."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / USER_CONFIG


# ----------------------------------------------------------------- reading


def _read(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Configuration file '{path}' could not be read: {exc}") from exc


def _sources(explicit: Optional[str]) -> List[Tuple[Path, Dict[str, Any]]]:
    """Every configuration file to apply, least specific first.

    An explicit ``--config`` must exist — asking for a file and silently
    getting the built-in defaults is worse than being told it is missing. The
    searched files are optional by nature.
    """
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"Configuration file '{explicit}' was not found.")
        return [(path, _read(path))]

    found = []
    for path in (_user_config_path(), Path(PROJECT_CONFIG)):
        if path.is_file():
            found.append((path, _read(path)))
    return found


def _profiles(table: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """The named profiles one file defines, checked for shape.

    Validated even when no ``--profile`` was asked for: ``profile = 3`` is a
    mistake worth naming now rather than the next time someone asks for one.
    """
    profiles = table.get(PROFILE_TABLE)
    if profiles is None:
        return {}
    if not isinstance(profiles, dict):
        raise ConfigError(
            f"'{PROFILE_TABLE}' in {path} must be a table of profiles, "
            f"as in [{PROFILE_TABLE}.datacenter]."
        )
    for name, section in profiles.items():
        if not isinstance(section, dict):
            raise ConfigError(f"[{PROFILE_TABLE}.{name}] in {path} must be a table of options.")
    return profiles


def _select(
    table: Dict[str, Any],
    path: Path,
    profile: Optional[str],
    profiles: Dict[str, Any],
) -> List[Tuple[str, Any, Path]]:
    """One file's keys: its top level, then the chosen profile on top."""
    layers = [{key: value for key, value in table.items() if key != PROFILE_TABLE}]
    if profile is not None and profile in profiles:
        layers.append(profiles[profile])
    return [(key, value, path) for layer in layers for key, value in layer.items()]


# -------------------------------------------------------------- validating


def _flag_actions(parser: argparse.ArgumentParser) -> Dict[str, argparse.Action]:
    """Every long flag of ``parser``, by the key a config file would use.

    Both spellings of a name are accepted: ``scan-ports`` as the flag is
    written, and ``scan_ports`` as a Python programmer would write it.
    """
    # _actions is argparse's only route to the flags it holds; there is no
    # public accessor for them.
    actions: Dict[str, argparse.Action] = {}
    for action in parser._actions:
        if action.dest in _NOT_CONFIGURABLE:
            continue
        for option in action.option_strings:
            if not option.startswith("--"):
                continue
            name = option[2:]
            actions[name] = action
            actions[name.replace("-", "_")] = action
    return actions


def _kind(value: Any) -> str:
    return {bool: "true/false", int: "a number", float: "a number", str: "text"}.get(
        type(value), type(value).__name__
    )


def _one_value(action: argparse.Action, key: str, value: Any, path: Path) -> Any:
    """Check and convert one scalar against the flag it will become."""
    where = f"'{key}' in {path}"

    # A flag with its own converter (--min-active, --ports) validates there, so
    # a TOML number goes through it as the text it would be on the command line;
    # otherwise min-active = 150 would skip the 0-100 check.
    custom_type = action.type is not None and action.type not in (int, float, str)
    if custom_type and isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(value)

    if action.type is not None and isinstance(value, str):
        try:
            value = action.type(value)
        except (argparse.ArgumentTypeError, TypeError, ValueError) as exc:
            raise ConfigError(f"{where}: {exc}") from exc

    # TOML's true is a bool, and Python's bool is an int, so a numeric flag has
    # to reject it explicitly rather than quietly scanning with 1 thread.
    if action.type in (int, float) and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise ConfigError(f"{where} must be a number, not {_kind(value)}.")
    if action.type is int and not isinstance(value, int):
        raise ConfigError(f"{where} must be a whole number, not {value!r}.")

    if action.choices is not None and value not in action.choices:
        allowed = ", ".join(str(choice) for choice in action.choices)
        raise ConfigError(f"{where}: {value!r} is not one of {allowed}.")

    return value


def _coerce(action: argparse.Action, key: str, value: Any, path: Path) -> Any:
    """One config value as the flag's ``dest`` should hold it."""
    where = f"'{key}' in {path}"

    if action.nargs == 0:
        # A switch: true means "as if the flag were passed", false means it was
        # not — which is the flag's own default, not its opposite.
        if not isinstance(value, bool):
            raise ConfigError(f"{where} must be true or false, not {_kind(value)}.")
        return action.const if value else _KEEP

    if action.nargs in ("+", "*"):
        values = value if isinstance(value, list) else [value]
        if not values:
            raise ConfigError(f"{where} must list at least one value.")
        return [_one_value(action, key, item, path) for item in values]

    if isinstance(value, list):
        raise ConfigError(f"{where} takes a single value, not a list.")

    return _one_value(action, key, value, path)


def _unknown_key(key: str, path: Path, known: Dict[str, argparse.Action]) -> ConfigError:
    reason = _NOT_CONFIGURABLE.get(key.replace("-", "_"))
    if reason is not None:
        return ConfigError(f"'{key}' in {path} cannot be set in a configuration file: {reason}.")
    suggestion = _closest(key, known)
    hint = f" Did you mean '{suggestion}'?" if suggestion else ""
    return ConfigError(f"Unknown option '{key}' in {path}.{hint}")


def _closest(key: str, known: Dict[str, argparse.Action]) -> Optional[str]:
    from difflib import get_close_matches

    # Only the hyphenated spellings, so a suggestion reads like the flag.
    names = [name for name in known if "_" not in name]
    matches = get_close_matches(key.replace("_", "-"), names, n=1)
    return matches[0] if matches else None


# ---------------------------------------------------------------- applying


def resolve(
    parser: argparse.ArgumentParser,
    explicit: Optional[str],
    profile: Optional[str],
    given: Set[str],
) -> Dict[str, Any]:
    """The defaults to apply, keyed by argparse ``dest``.

    ``given`` are the dests the command line already set; they are dropped, so
    a flag that was passed ignores the file completely. Without that, an
    ``extend`` flag such as ``--input`` would add to the file's value instead
    of replacing it.
    """
    sources = _sources(explicit)
    profiles = [_profiles(table, path) for path, table in sources]

    if profile is not None and sources and not any(profile in found for found in profiles):
        names = ", ".join(str(path) for path, _table in sources)
        raise ConfigError(f"No [{PROFILE_TABLE}.{profile}] section in {names}.")

    known = _flag_actions(parser)
    defaults: Dict[str, Any] = {}
    for (path, table), found in zip(sources, profiles):
        from_project = explicit is None and path == Path(PROJECT_CONFIG)
        for key, value, origin in _select(table, path, profile, found):
            action = known.get(key)
            if action is None:
                raise _unknown_key(key, origin, known)
            if from_project and action.dest in _NOT_FROM_PROJECT:
                raise ConfigError(
                    f"'{key}' in {origin} cannot be set in a project file, which could "
                    f"send your scan results elsewhere. Put it in {_user_config_path()} "
                    "or a file you pass with --config."
                )
            if action.dest in given:
                continue
            resolved = _coerce(action, key, value, origin)
            if resolved is _KEEP:
                defaults.pop(action.dest, None)
            else:
                defaults[action.dest] = resolved
    _check_exclusive(parser, defaults, given)
    return defaults


def _check_exclusive(
    parser: argparse.ArgumentParser, defaults: Dict[str, Any], given: Set[str]
) -> None:
    """Enforce the parser's mutually exclusive groups on the file's values.

    argparse checks them only among flags on the command line, never defaults,
    so without this a file could turn on --json and --jsonl together. A flag
    on the command line wins over the file's choice from its group, as a flag
    wins over the file everywhere else.
    """
    # _mutually_exclusive_groups is, like _actions, argparse's only route to them.
    for group in parser._mutually_exclusive_groups:
        members = group._group_actions
        if any(action.dest in given for action in members):
            for action in members:
                defaults.pop(action.dest, None)
            continue
        chosen = [action for action in members if action.dest in defaults]
        if len(chosen) > 1:
            names = " and ".join(action.option_strings[-1][2:] for action in chosen)
            raise ConfigError(f"The configuration sets {names}, which cannot be combined.")


def _given_dests(build, argv: List[str]) -> Set[str]:
    """Which options the command line set, whatever spelling it used.

    A throwaway parser whose every default is ``SUPPRESS`` leaves out the
    options that were not given, so argparse's own matching — abbreviations,
    ``--flag=value``, everything — decides, rather than a second guess at what
    the tokens mean.
    """
    probe = build()
    # set_defaults() values live here rather than on an action, and parse_args
    # applies them to whatever the command line left unset — so they have to go
    # too, or every dest the parser set a default for would look like it was
    # given.
    probe._defaults.clear()
    for action in probe._actions:
        action.default = argparse.SUPPRESS
    namespace, _unknown = probe.parse_known_args(argv)
    return set(vars(namespace))


def apply(parser: argparse.ArgumentParser, build, argv: List[str]) -> None:
    """Set ``parser``'s defaults from the configuration files ``argv`` selects.

    ``build`` remakes the parser for the throwaway pass that works out which
    flags the command line gave, so this one is left untouched until its
    defaults are ready.
    """
    selector = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    selector.add_argument("--config", default=None)
    selector.add_argument("--no-config", action="store_true")
    selector.add_argument("--profile", default=None)
    selected, _unknown = selector.parse_known_args(argv)

    if selected.no_config:
        if selected.profile is not None:
            raise ConfigError(
                "--profile needs a configuration file, so it cannot join --no-config."
            )
        return

    defaults = resolve(parser, selected.config, selected.profile, _given_dests(build, argv))
    if defaults:
        parser.set_defaults(**defaults)
