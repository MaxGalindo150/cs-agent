"""Measure the decision model's footprint from the local trace ledgers.

Reads ``<TRACE_DIR>/decisions.jsonl`` and ``<TRACE_DIR>/scores.jsonl`` (plus
the dated trace files for turn-level counts) and prints, per site and per
turn, what a Langfuse dashboard would show once the same records are
exported there (ADR-0004 · Measurement):

  per site   calls · acted rate · fallback rate · agreement with the previous
             method (where measured) · confidence histogram · latency p50/p95
             · tokens
  per turn   turns · tool calls · iterations · budget exhaustions · nudges
             (and how often the model insisted) · judge quality distribution
             · thumbs up/down · diagnoses

    uv run python scripts/jev_report.py                # .traces/
    uv run python scripts/jev_report.py --trace-dir /tmp/traces --json
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _trace_records(trace_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(trace_dir.glob("*.jsonl")):
        if f.name in {"usage.jsonl", "decisions.jsonl", "scores.jsonl"}:
            continue
        out += _read(f)
    return out


def _pct(values: list[int | float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


def _confidence_of(record: dict[str, Any]) -> float | None:
    """The confidence the site acted on: a choice/score confidence when the
    record has one, else the strongest noul's distance from 0.5."""
    answers = record.get("answers") or {}
    confs = [a["confidence"] for a in answers.values() if "confidence" in a]
    if confs:
        return float(max(confs))
    ps = [abs(a["p"] - 0.5) * 2 for a in answers.values() if "p" in a]
    return float(max(ps)) if ps else None


def per_site(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    by_site: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in decisions:
        by_site[str(d.get("site"))].append(d)
    report: dict[str, Any] = {}
    for site, rows in sorted(by_site.items()):
        jev = [r for r in rows if r.get("source") == "jev"]
        lat = [r["latency_ms"] for r in jev if r.get("latency_ms") is not None]
        tokens = [
            (r["usage"] or {}).get("in", 0) + (r["usage"] or {}).get("out", 0)
            for r in jev
            if r.get("usage")
        ]
        confs = [c for c in (_confidence_of(r) for r in jev) if c is not None]
        hist = Counter(
            "<0.5"
            if c < 0.5
            else "<0.8"
            if c < 0.8
            else "<0.95"
            if c < 0.95
            else "≥0.95"
            for c in confs
        )
        measured = [r for r in jev if r.get("agreement") is not None]
        report[site] = {
            "calls": len(rows),
            "acted_rate": round(sum(1 for r in jev if r.get("acted")) / len(jev), 3)
            if jev
            else None,
            "fallback_rate": round(
                sum(1 for r in rows if r.get("source") == "fallback") / len(rows), 3
            ),
            "agreement_with_previous": round(
                sum(1 for r in measured if r["agreement"]) / len(measured), 3
            )
            if measured
            else None,
            "confidence_hist": dict(hist),
            "latency_ms": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95)},
            "tokens_per_call": round(statistics.mean(tokens)) if tokens else None,
        }
    return report


def per_turn(
    trace: list[dict[str, Any]], scores: list[dict[str, Any]]
) -> dict[str, Any]:
    turns = [r for r in trace if r.get("type") == "turn_end"]
    tools = [r for r in trace if r.get("type") == "tool"]
    limits = [r for r in trace if r.get("type") == "limit_reached"]
    nudges = [r for r in trace if r.get("type") == "nudge"]
    llm = [r for r in trace if r.get("type") == "llm"]
    by_name: dict[str, list[Any]] = defaultdict(list)
    for s in scores:
        by_name[str(s.get("name"))].append(s.get("value"))
    quality = [float(v) for v in by_name.get("jev.quality", [])]
    feedback = [int(v) for v in by_name.get("user_feedback", [])]
    return {
        "turns": len(turns),
        "iterations_mean": round(statistics.mean(r["iterations"] for r in turns), 2)
        if turns
        else None,
        "tool_calls_per_turn": round(len(tools) / len(turns), 2) if turns else None,
        "tool_errors": sum(
            1 for r in tools if str(r.get("output", "")).lower().startswith("error")
        ),
        "llm_calls": len(llm),
        "tokens_in": sum((r.get("usage") or {}).get("in", 0) for r in llm),
        "tokens_out": sum((r.get("usage") or {}).get("out", 0) for r in llm),
        "budget_exhausted": dict(Counter(str(r.get("reason")) for r in limits)),
        "nudges": {
            "total": len(nudges),
            "by_site": dict(Counter(str(r.get("site")) for r in nudges)),
        },
        "judge": {
            "scored": len(quality),
            "quality_mean": round(statistics.mean(quality), 2) if quality else None,
            "quality_hist": dict(Counter(str(int(q)) for q in quality)),
            "grounded_rate": round(
                sum(1 for v in by_name.get("jev.grounded", []) if v)
                / len(by_name["jev.grounded"]),
                3,
            )
            if by_name.get("jev.grounded")
            else None,
            "resolved_rate": round(
                sum(1 for v in by_name.get("jev.resolved", []) if v)
                / len(by_name["jev.resolved"]),
                3,
            )
            if by_name.get("jev.resolved")
            else None,
            "llm_escalations": len(by_name.get("llm.quality", [])),
        },
        "feedback": {
            "up": sum(1 for v in feedback if v > 0),
            "down": sum(1 for v in feedback if v < 0),
            "diagnoses": dict(
                Counter(str(v) for v in by_name.get("jev.diagnosis", []))
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--trace-dir", type=Path, default=ROOT / ".traces")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    decisions = _read(args.trace_dir / "decisions.jsonl")
    scores = _read(args.trace_dir / "scores.jsonl")
    trace = _trace_records(args.trace_dir)
    report: dict[str, Any] = {
        "trace_dir": str(args.trace_dir),
        "per_site": per_site(decisions),
        "per_turn": per_turn(trace, scores),
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    print(f"trace dir: {args.trace_dir}")
    print(f"decisions: {len(decisions)}  scores: {len(scores)}\n")
    print("per site")
    for site, r in report["per_site"].items():
        print(
            f"  {site:<19} calls {r['calls']:>4}  acted {r['acted_rate']}  "
            f"fallback {r['fallback_rate']}  agree {r['agreement_with_previous']}  "
            f"p50 {r['latency_ms']['p50']} ms  p95 {r['latency_ms']['p95']} ms  "
            f"tokens {r['tokens_per_call']}  conf {r['confidence_hist']}"
        )
    t = report["per_turn"]
    print("\nper turn")
    for key, value in t.items():
        print(f"  {key:<20} {value}")


if __name__ == "__main__":
    main()
