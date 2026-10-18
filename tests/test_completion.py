import shlex
import shutil
import subprocess
import sys

import pytest

from ipmg.cli import commands
from ipmg.cli.completion import SHELLS, commands as completion_commands, script
from ipmg.cli.parser import build_parser, build_web_parser


def all_long_flags(parser):
    return {
        option
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--") and action.help != "==SUPPRESS=="
    }


@pytest.mark.parametrize("shell", SHELLS)
def test_every_flag_of_every_command_is_in_every_script(shell):
    text = script(shell)
    for command in completion_commands():
        for flag in command.flags:
            name = flag.long
            # fish names long flags without their dashes.
            assert (name[2:] if shell == "fish" else name) in text, (shell, command.name, name)


def test_scripts_are_generated_from_the_parsers():
    # A flag added to a parser completes without editing the generator.
    scan = next(command for command in completion_commands() if command.name == "")
    assert {flag.long for flag in scan.flags} >= all_long_flags(build_parser()) - {"--help"}
    web = next(command for command in completion_commands() if command.name == "web")
    assert {flag.long for flag in web.flags} >= all_long_flags(build_web_parser()) - {"--help"}


@pytest.mark.parametrize("shell", SHELLS)
def test_ipmg_completion_prints_only_the_script(shell, capsys):
    assert commands.run(["completion", shell]) == 0

    out = capsys.readouterr().out
    assert out == script(shell)
    assert "ipmg" in out and "· completion" not in out


def test_an_unknown_shell_is_refused(capsys):
    with pytest.raises(SystemExit):
        commands.run(["completion", "tcsh"])
    assert "invalid choice" in capsys.readouterr().err


# ------------------------------------------------------------------- bash

BASHES = [
    path
    for path in dict.fromkeys(filter(None, [shutil.which("bash"), "/bin/bash"]))
    if shutil.which(path)
]
needs_bash = pytest.mark.skipif(sys.platform == "win32" or not BASHES, reason="needs a POSIX bash")


@pytest.fixture(scope="module")
def bash_script(tmp_path_factory):
    path = tmp_path_factory.mktemp("completion") / "ipmg.bash"
    path.write_text(script("bash"))
    return path


def complete(bash, script_path, *words):
    """What bash offers for ``ipmg <words>``, the last word being the one typed."""
    quoted = " ".join(shlex.quote(word) for word in ("ipmg", *words))
    program = (
        f"source {shlex.quote(str(script_path))}; "
        f"COMP_WORDS=({quoted}); COMP_CWORD={len(words)}; _ipmg; "
        'printf "%s\\n" "${COMPREPLY[@]}"'
    )
    result = subprocess.run([bash, "-c", program], capture_output=True, text=True, check=True)
    return [line for line in result.stdout.splitlines() if line]


@needs_bash
@pytest.mark.parametrize("bash", BASHES)
@pytest.mark.parametrize(
    "words, expected",
    [
        (("",), {"web", "history", "diff", "compare", "wake", "completion"}),
        (("--fo",), {"--formats"}),
        (("--formats", ""), {"xlsx", "csv", "json", "jsonl", "md"}),
        # --formats takes several values: still offered after the first.
        (("--formats", "csv", ""), {"xlsx", "csv", "json", "jsonl", "md"}),
        (("--probe", ""), {"icmp", "tcp", "icmp,tcp"}),
        (("--discover", ""), {"ipv4", "ipv6", "all"}),
        (("--threads", "5", "--res"), {"--resolve", "--resolve-active-only", "--resume"}),
        (("web", "--max"), {"--max-scans"}),
        (("history", ""), {"prune"}),
        (("history", "prune", "--k"), {"--keep"}),
        (("diff", "--fail"), {"--fail-on-change"}),
        (("completion", ""), set(SHELLS)),
        (("completion", "z"), {"zsh"}),
        (("wake", "--b"), {"--broadcast"}),
    ],
)
def test_bash_offers(bash, bash_script, words, expected):
    assert set(complete(bash, bash_script, *words)) == expected


@needs_bash
@pytest.mark.parametrize("bash", BASHES)
def test_bash_leaves_file_flags_to_file_name_completion(bash, bash_script):
    # Nothing offered, so readline's own file-name completion takes over.
    assert complete(bash, bash_script, "--input", "") == []
    assert complete(bash, bash_script, "--input", "a.txt", "") == []
    assert complete(bash, bash_script, "web", "--db", "") == []


@needs_bash
@pytest.mark.parametrize("bash", BASHES)
def test_web_flags_do_not_leak_into_the_scan_command(bash, bash_script):
    assert "--max-scans" not in complete(bash, bash_script, "--")
    assert "--input" not in complete(bash, bash_script, "web", "--")


# ------------------------------------------------------------ other shells


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
def test_zsh_script_parses_and_registers(tmp_path):
    path = tmp_path / "ipmg.zsh"
    path.write_text(script("zsh"))
    subprocess.run(["zsh", "-n", str(path)], check=True)
    result = subprocess.run(
        [
            "zsh",
            "-f",
            "-c",
            f"autoload -Uz compinit && compinit -u -D; source {shlex.quote(str(path))}; "
            "print -r -- $_comps[ipmg]",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "_ipmg"


@pytest.mark.skipif(shutil.which("fish") is None, reason="fish is not installed")
def test_fish_script_parses_and_completes(tmp_path):
    path = tmp_path / "ipmg.fish"
    path.write_text(script("fish"))
    subprocess.run(["fish", "--no-execute", str(path)], check=True)
    result = subprocess.run(
        ["fish", "-c", f"source {path}; complete -C 'ipmg --form'; complete -C 'ipmg web --max'"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--formats" in result.stdout and "--max-scans" in result.stdout


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 is not installed")
def test_powershell_script_completes(tmp_path):
    path = tmp_path / "ipmg.ps1"
    path.write_text(script("powershell"))

    def expand(line):
        return (
            f"$r = TabExpansion2 -inputScript '{line}' -cursorColumn {len(line)}; "
            "$r.CompletionMatches.CompletionText -join ','; "
        )

    check = f". '{path}'; " + expand("ipmg --form") + expand("ipmg --formats ")
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", check],
        capture_output=True,
        text=True,
        check=True,
    )
    first, second = result.stdout.strip().splitlines()[-2:]
    assert first == "--formats"
    assert set(second.split(",")) == {"xlsx", "csv", "json", "jsonl", "md"}


def test_zsh_specs_escape_brackets_exactly_once():
    # Inside single quotes a backslash is literal: "\\[" made zsh reject the
    # whole _arguments call ("invalid option definition") and complete nothing.
    text = script("zsh")
    assert "\\\\[" not in text
    assert "\\[profile.NAME\\]" in text
