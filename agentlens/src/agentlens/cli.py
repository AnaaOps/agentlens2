"""Command line interface: agentlens runs list | runs show | test | compare | dashboard."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

from .storage import TraceStore
from .testing import compare, current_version, run_suite
from .tracer import Tracer


def _fmt_ms(ms: Optional[float]) -> str:
    if ms is None:
        return "-"
    return f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms:.0f}ms"


def _short(text: object, n: int = 70) -> str:
    s = str(text).replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _preview(span) -> str:
    out = json.loads(span["output_json"]) if span["output_json"] else None
    if span["kind"] == "llm" and isinstance(out, dict):
        calls = out.get("tool_calls") or []
        body = ("calls " + ", ".join(f"{c['name']}({c['arguments']})" for c in calls)
                if calls else f"says {out.get('content')!r}")
        return body + ("  [cached]" if out.get("cached") else "")
    if span["kind"] == "tool":
        inp = json.loads(span["input_json"]) if span["input_json"] else {}
        return f"{inp.get('kwargs', {})} -> {out}"
    return ""


def cmd_runs_list(args) -> int:
    runs = TraceStore(args.db).list_runs(limit=args.limit, status=args.status)
    if not runs:
        print("No runs recorded yet.")
        return 0
    print(f"{'ID':<13}{'STATUS':<11}{'TOKENS':>7}{'TIME':>8}  {'LABEL':<20}NAME")
    for r in runs:
        print(f"{r['id']:<13}{r['status']:<11}{r['total_tokens']:>7}"
              f"{_fmt_ms(r['total_latency_ms']):>8}  {(r['failure_label'] or '-'):<20}{_short(r['name'], 40)}")
    return 0


def cmd_runs_show(args) -> int:
    store = TraceStore(args.db)
    try:
        run = store.get_run(args.run_id)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if run is None:
        print(f"Run '{args.run_id}' not found.", file=sys.stderr)
        return 1
    print(f"Run {run['id']}  {run['name']}  status={run['status']}  model={run['model']}  "
          f"tokens={run['total_tokens']}  time={_fmt_ms(run['total_latency_ms'])}")
    if run["failure_label"]:
        print(f"failure label: {run['failure_label']}")
    spans = store.get_spans(run["id"])
    depth: dict[str, int] = {}
    for s in spans:
        depth[s["id"]] = depth.get(s["parent_id"], -1) + 1
        pad = "  " * depth[s["id"]]
        tok = (f"  tokens {s['tokens_in']}->{s['tokens_out']}"
               if s["kind"] == "llm" and s["tokens_in"] is not None else "")
        print(f"{pad}{s['kind']:<5} {s['name']}  {_fmt_ms(s['latency_ms'])}{tok}")
        if (p := _preview(s)):
            print(f"{pad}      {_short(p, 100)}")
        if s["error"]:
            print(f"{pad}      ERROR {_short(s['error'], 100)}")
    return 0


def _load_suite(path: str):
    p = Path(path).resolve()
    sys.path.insert(0, str(p.parent))
    spec = importlib.util.spec_from_file_location(p.stem, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in ("SUITE", "CASES", "build"):
        if not hasattr(module, attr):
            raise SystemExit(f"Suite file must define {attr}")
    return module


def cmd_test(args) -> int:
    module = _load_suite(args.suite_file)
    store = TraceStore(args.db)
    tracer = Tracer(store)
    version = args.label or current_version()
    agent = module.build(tracer, args.mode)
    report = run_suite(module.SUITE, module.CASES, agent, tracer, version,
                       model=getattr(module, "MODEL", None))

    for r in report.results:
        tag = "PASS" if r.passed else "FAIL"
        extra = "" if r.passed else f"  [{r.label}] {_short(r.detail, 60)}"
        print(f"{tag}  {r.case_id:<22} run={r.run_id}{extra}")
    print(f"\n{module.SUITE} @ {version}: {sum(r.passed for r in report.results)}/"
          f"{len(report.results)} passed ({report.pass_rate:.0%})")

    code = 0
    if args.baseline:
        cmp = compare(store, module.SUITE, args.baseline, version)
        print(f"vs {args.baseline}: {len(cmp.regressions)} regressions, {len(cmp.fixes)} fixes")
        for cid in cmp.regressions:
            print(f"  REGRESSION  {cid}")
        for cid in cmp.fixes:
            print(f"  fixed       {cid}")
        if cmp.regressions:
            code = 1
    if args.fail_under is not None and report.pass_rate < args.fail_under:
        print(f"Pass rate {report.pass_rate:.0%} is below --fail-under {args.fail_under:.0%}")
        code = 1
    return code


def cmd_compare(args) -> int:
    cmp = compare(TraceStore(args.db), args.suite, args.base, args.new)
    print(f"{args.suite}: {args.base} -> {args.new}")
    print(f"  regressions : {cmp.regressions or '-'}")
    print(f"  fixes       : {cmp.fixes or '-'}")
    print(f"  still failing: {cmp.still_failing or '-'}")
    print(f"  new cases   : {cmp.new_cases or '-'}")
    return 1 if cmp.regressions else 0


def cmd_dashboard(args) -> int:
    app = Path(__file__).parent / "dashboard.py"
    env = {**os.environ, "AGENTLENS_DB": args.db}
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)], env=env)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=os.getenv("AGENTLENS_DB", "agentlens.db"),
                        help="trace database file (default: agentlens.db)")

    parser = argparse.ArgumentParser(prog="agentlens", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    runs = sub.add_parser("runs", help="inspect recorded runs").add_subparsers(
        dest="runs_command", required=True)
    p = runs.add_parser("list", parents=[common], help="list recent runs")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--status", choices=["running", "success", "error", "max_steps"])
    p.set_defaults(func=cmd_runs_list)
    p = runs.add_parser("show", parents=[common], help="show one run as a span tree")
    p.add_argument("run_id", help="full id or unique prefix")
    p.set_defaults(func=cmd_runs_show)

    p = sub.add_parser("test", parents=[common], help="run a regression suite")
    p.add_argument("suite_file")
    p.add_argument("--label", help="version label (default: git short hash)")
    p.add_argument("--mode", choices=["live", "auto", "replay"], default="auto")
    p.add_argument("--baseline", help="version label to compare against")
    p.add_argument("--fail-under", type=float, help="exit 1 if pass rate is below this (0-1)")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("compare", parents=[common], help="compare two versions of a suite")
    p.add_argument("suite")
    p.add_argument("base")
    p.add_argument("new")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("dashboard", parents=[common], help="open the Streamlit dashboard")
    p.set_defaults(func=cmd_dashboard)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
