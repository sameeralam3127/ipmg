"""Defaults read from ipmg.toml, and the errors a bad one produces."""

import pytest

from ipmg.cli import commands
from ipmg.cli.parser import build_parser
from ipmg.exceptions import ConfigError


@pytest.fixture(autouse=True)
def in_project(tmp_path, monkeypatch):
    """Run each test in an empty directory, so ./ipmg.toml is only what it writes."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def parse(argv):
    """Parse a command line the way the scan command does, config included."""
    from ipmg.cli import config

    parser = build_parser()
    config.apply(parser, build_parser, argv)
    return parser.parse_args(argv)


# ------------------------------------------------------------------ reading


def test_project_config_supplies_defaults(in_project):
    write(in_project / "ipmg.toml", "threads = 200\ntimeout = 1\nresolve = true\n")

    args = parse([])

    assert (args.threads, args.timeout, args.resolve) == (200, 1, True)


def test_a_list_valued_flag_takes_a_list(in_project):
    write(in_project / "ipmg.toml", 'formats = ["md", "csv"]\n')

    assert parse([]).formats == ["md", "csv"]


def test_a_flag_name_may_be_spelled_with_either_separator(in_project):
    write(in_project / "ipmg.toml", "scan-ports = true\nport_timeout = 0.25\n")

    args = parse([])

    assert args.scan_ports is True
    assert args.port_timeout == 0.25


def test_a_value_is_converted_by_the_flags_own_type(in_project):
    """--ports parses "22,80" into a tuple, and so does the file."""
    write(in_project / "ipmg.toml", 'ports = "22,80"\n')

    assert parse([]).ports == (22, 80)


def test_a_switch_set_to_false_leaves_the_built_in_default(in_project):
    write(in_project / "ipmg.toml", "resolve = false\nno-history = false\n")

    args = parse([])

    assert args.resolve is False
    assert args.history is True


def test_a_store_false_flag_is_named_as_the_flag_is_written(in_project):
    """no-history = true means "as if --no-history were passed"."""
    write(in_project / "ipmg.toml", "no-history = true\n")

    assert parse([]).history is False


def test_the_user_config_is_read_when_there_is_no_project_file(in_project, monkeypatch):
    xdg = in_project / "xdg"
    (xdg / "ipmg").mkdir(parents=True)
    write(xdg / "ipmg" / "config.toml", "threads = 111\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    assert parse([]).threads == 111


def test_the_project_file_overrides_the_user_file(in_project, monkeypatch):
    xdg = in_project / "xdg"
    (xdg / "ipmg").mkdir(parents=True)
    write(xdg / "ipmg" / "config.toml", "threads = 111\ntimeout = 9\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    write(in_project / "ipmg.toml", "threads = 222\n")

    args = parse([])

    assert args.threads == 222  # the project's
    assert args.timeout == 9  # only the user's, so it still applies


def test_no_config_file_at_all_leaves_the_built_in_defaults():
    assert parse([]).threads == 50


# ---------------------------------------------------------------- selecting


def test_config_points_at_another_file(in_project):
    write(in_project / "ipmg.toml", "threads = 200\n")
    other = write(in_project / "other.toml", "threads = 300\n")

    assert parse(["--config", str(other)]).threads == 300


def test_no_config_ignores_every_file(in_project):
    write(in_project / "ipmg.toml", "threads = 200\n")

    assert parse(["--no-config"]).threads == 50


def test_a_profile_layers_on_top_of_the_top_level(in_project):
    write(
        in_project / "ipmg.toml",
        "threads = 200\ntimeout = 1\n\n[profile.datacenter]\nthreads = 400\n",
    )

    args = parse(["--profile", "datacenter"])

    assert args.threads == 400  # the profile's
    assert args.timeout == 1  # inherited from the top level


def test_a_profile_is_ignored_unless_it_is_asked_for(in_project):
    write(in_project / "ipmg.toml", "threads = 200\n\n[profile.datacenter]\nthreads = 400\n")

    assert parse([]).threads == 200


# ----------------------------------------------------- the command line wins


def test_a_flag_overrides_the_file(in_project):
    write(in_project / "ipmg.toml", "threads = 200\n")

    assert parse(["--threads", "7"]).threads == 7


def test_a_flag_overrides_a_profile(in_project):
    write(in_project / "ipmg.toml", "[profile.datacenter]\nthreads = 400\n")

    assert parse(["--profile", "datacenter", "--threads", "7"]).threads == 7


def test_an_abbreviated_flag_still_overrides_the_file(in_project):
    """The override is decided by argparse's own matching, not by the spelling."""
    write(in_project / "ipmg.toml", "threads = 200\n")

    assert parse(["--thread", "7"]).threads == 7


def test_an_input_on_the_command_line_replaces_the_file_rather_than_adding_to_it(in_project):
    """--input accumulates across repeats, which must not reach across the file."""
    write(in_project / "ipmg.toml", 'input = ["10.0.0.1"]\n')

    assert parse(["--input", "10.0.0.9"]).input == ["10.0.0.9"]


def test_an_input_from_the_file_is_used_when_the_flag_is_absent(in_project):
    write(in_project / "ipmg.toml", 'input = ["10.0.0.1", "10.0.0.2"]\n')

    assert parse([]).input == ["10.0.0.1", "10.0.0.2"]


def test_a_switch_on_the_command_line_beats_the_file(in_project):
    write(in_project / "ipmg.toml", "resolve = false\n")

    assert parse(["--resolve"]).resolve is True


# ------------------------------------------------------------------- errors


def test_an_unknown_key_names_itself_and_the_file(in_project):
    write(in_project / "ipmg.toml", "thredas = 200\n")

    with pytest.raises(ConfigError) as error:
        parse([])

    message = str(error.value)
    assert "thredas" in message
    assert "ipmg.toml" in message
    assert "Did you mean 'threads'?" in message


def test_a_flag_that_cannot_be_configured_says_why(in_project):
    write(in_project / "ipmg.toml", "web = true\n")

    with pytest.raises(ConfigError, match="cannot be set in a configuration file"):
        parse([])


def test_a_number_that_is_not_a_number(in_project):
    write(in_project / "ipmg.toml", "threads = true\n")

    with pytest.raises(ConfigError, match="'threads' in ipmg.toml must be a number"):
        parse([])


def test_a_whole_number_flag_rejects_a_fraction(in_project):
    write(in_project / "ipmg.toml", "threads = 1.5\n")

    with pytest.raises(ConfigError, match="must be a whole number"):
        parse([])


def test_a_switch_that_is_not_a_switch(in_project):
    write(in_project / "ipmg.toml", 'resolve = "yes"\n')

    with pytest.raises(ConfigError, match="must be true or false"):
        parse([])


def test_a_value_outside_the_flags_choices(in_project):
    write(in_project / "ipmg.toml", 'formats = ["pdf"]\n')

    with pytest.raises(ConfigError, match="'pdf' is not one of"):
        parse([])


def test_a_value_the_flags_type_rejects(in_project):
    write(in_project / "ipmg.toml", 'ports = "not-a-port"\n')

    with pytest.raises(ConfigError, match="'ports' in ipmg.toml"):
        parse([])


def test_a_list_for_a_single_valued_flag(in_project):
    write(in_project / "ipmg.toml", "threads = [1, 2]\n")

    with pytest.raises(ConfigError, match="takes a single value, not a list"):
        parse([])


def test_an_empty_list_for_a_list_flag(in_project):
    write(in_project / "ipmg.toml", "formats = []\n")

    with pytest.raises(ConfigError, match="must list at least one value"):
        parse([])


def test_malformed_toml_names_the_file(in_project):
    write(in_project / "ipmg.toml", "threads =\n")

    with pytest.raises(ConfigError, match="ipmg.toml is not valid TOML"):
        parse([])


def test_a_missing_explicit_config_file_is_an_error(in_project):
    with pytest.raises(ConfigError, match="was not found"):
        parse(["--config", "nope.toml"])


def test_a_missing_profile_names_the_files_searched(in_project):
    write(in_project / "ipmg.toml", "threads = 200\n")

    with pytest.raises(ConfigError, match=r"No \[profile.nope\] section in ipmg.toml"):
        parse(["--profile", "nope"])


def test_a_profile_cannot_be_asked_for_with_no_config(in_project):
    with pytest.raises(ConfigError, match="--profile needs a configuration file"):
        parse(["--no-config", "--profile", "datacenter"])


def test_a_profile_table_that_is_not_a_table(in_project):
    write(in_project / "ipmg.toml", "profile = 3\n")

    with pytest.raises(ConfigError, match="must be a table of profiles"):
        parse(["--profile", "datacenter"])


# ----------------------------------------------------------- end to end


def test_a_scan_uses_the_config_file(in_project, monkeypatch, capsys):
    monkeypatch.setattr("ipmg.core.engine.ping_ip", lambda *_args: ("Active", 1.0))
    write(
        in_project / "ipmg.toml",
        'input = ["10.0.0.1"]\nthreads = 3\ntimeout = 1\nno-history = true\nformats = ["csv"]\n',
    )

    assert commands.run(["--output", "out"]) == commands.EXIT_OK

    out = capsys.readouterr().out
    assert "3 threads" in out
    assert "1s timeout" in out
    assert len(list(in_project.glob("out_*.csv"))) == 1


def test_a_config_error_exits_with_status_one(in_project, capsys):
    write(in_project / "ipmg.toml", "thredas = 200\n")

    assert commands.run([]) == commands.EXIT_ERROR
    assert "thredas" in capsys.readouterr().out


def test_help_says_where_configuration_is_read_from(capsys):
    with pytest.raises(SystemExit):
        commands.run(["--help"])

    out = " ".join(capsys.readouterr().out.split())
    assert "ipmg.toml" in out
    assert "--no-config" in out
    assert "--profile" in out
