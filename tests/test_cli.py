from ride_app.__main__ import main
from ride_app.interfaces.cli import run_cli


def run_session(app, monkeypatch, commands):
    lines = iter(commands)
    monkeypatch.setattr("builtins.input", lambda _: next(lines))
    return run_cli(app)


def test_cli_lifecycle_and_session_persistence(app, monkeypatch, capsys):
    code = run_session(
        app,
        monkeypatch,
        [
            "user register --name Alice",
            "driver register --name Bob --registration-number KA01 --type sedan --lat 0 --lng 0",
            "coupon add --code SAVE10 --percentage 10",
            "ride book --user id-001 --type hatchback --lat 0 --lng 0 --coupon SAVE10",
            "coupon delete --code SAVE10",
            "ride end --ride id-003 --distance-km 10 --lat 0 --lng 0",
            "user rides --user id-001",
            "driver rides --driver id-002",
            "ride show --ride id-003",
            "exit",
        ],
    )
    output = capsys.readouterr()
    assert code == 0 and output.err == ""
    assert '"is_upgrade": true' in output.out
    assert '"total": "62.10"' in output.out
    assert len(app.rides.get_user_history("id-001")) == 1


def test_cli_recovers_from_core_errors_and_bad_syntax(app, monkeypatch, capsys):
    code = run_session(
        app,
        monkeypatch,
        [
            'user register --name " "',
            (
                "driver register --name Bob --registration-number KA01 "
                "--type hatchback --lat 99 --lng 0"
            ),
            "coupon add --code SAVE --percentage NaN",
            "ride book --user MISSING --type hatchback --lat 0 --lng 0",
            "not-a-command",
            'user register --name "unterminated',
            "help",
            "user register --name Alice",
            "exit",
        ],
    )
    output = capsys.readouterr()
    assert code == 1
    for expected in ("INVALID_NAME", "INVALID_LOCATION", "USER_NOT_FOUND", "INVALID_COMMAND"):
        assert expected in output.err
    assert "Alice" in output.out
    assert "usage:" in output.out


def test_cli_help_is_not_an_error(app, monkeypatch, capsys):
    assert run_session(app, monkeypatch, ["user --help", "exit"]) == 0
    assert capsys.readouterr().err == ""


def test_cli_eof_exits_cleanly(app, monkeypatch):
    def eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert run_cli(app) == 0


def test_demo_runs_and_has_expected_edge_cases(capsys):
    assert main(["demo"]) == 0
    output = capsys.readouterr().out
    assert '"total": "50.00"' in output
    assert '"total": "62.10"' in output
    assert "NO_DRIVER_AVAILABLE" in output
    assert "INVALID_COUPON" in output
    assert output.endswith("Demo completed successfully.\n")
