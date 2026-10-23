import textwrap

from agentlens.cli import main

SUITE = textwrap.dedent('''
    from agentlens.testing import Case, contains
    SUITE = "tmp"
    MODEL = "fake"
    CASES = [Case("a", "say hi", contains("hi")), Case("b", "say bye", contains("zzz"))]

    class R:
        answer = "hi there"
        status = "success"

    def build(tracer, mode):
        return lambda task: R()
''')


def test_cli_end_to_end(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    suite = tmp_path / "suite.py"
    suite.write_text(SUITE)

    assert main(["test", str(suite), "--db", db, "--label", "v1"]) == 0
    out = capsys.readouterr().out
    assert "PASS  a" in out and "FAIL  b" in out and "1/2 passed" in out

    assert main(["test", str(suite), "--db", db, "--label", "v2", "--fail-under", "0.9"]) == 1
    capsys.readouterr()

    assert main(["runs", "list", "--db", db]) == 0
    listing = capsys.readouterr().out
    assert "silent_wrong_answer" in listing and "tmp:a" in listing

    run_id = [l.split()[0] for l in listing.splitlines() if "tmp:b" in l][0]
    assert main(["runs", "show", run_id[:6], "--db", db]) == 0
    assert "agent" in capsys.readouterr().out

    assert main(["compare", "tmp", "v1", "v2", "--db", db]) == 0
    assert "regressions" in capsys.readouterr().out


def test_cli_baseline_regression_returns_nonzero(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    good = tmp_path / "suite.py"
    good.write_text(SUITE)
    main(["test", str(good), "--db", db, "--label", "v1"])
    good.write_text(SUITE.replace('answer = "hi there"', 'answer = "nope"'))
    code = main(["test", str(good), "--db", db, "--label", "v2", "--baseline", "v1"])
    assert code == 1 and "REGRESSION  a" in capsys.readouterr().out


def test_cli_missing_run_and_empty_db(tmp_path, capsys):
    db = str(tmp_path / "t.db")
    assert main(["runs", "list", "--db", db]) == 0
    assert "No runs" in capsys.readouterr().out
    assert main(["runs", "show", "nope", "--db", db]) == 1


def test_cli_runs_show_ambiguous_prefix(tmp_path, capsys):
    from agentlens import Tracer, TraceStore
    db = str(tmp_path / "t.db")
    store = TraceStore(db)
    tracer = Tracer(store)
    for _ in range(40):                       # enough runs that a 1-char prefix collides
        with tracer.run("x"):
            pass
    first_char = store.list_runs(limit=1)[0]["id"][0]
    assert main(["runs", "show", first_char, "--db", db]) in (0, 2)
