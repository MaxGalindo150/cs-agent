"""Replay the labelled set (``evals/jev/cases.jsonl``) against the real
decision model, site by site, and report accuracy, confidence and latency.

This is the Level-2 eval for the harness's judgment calls (CLAUDE.md §8):
the unit tests prove the harness applies a verdict correctly; this proves
the verdicts are right often enough on aliado-domain inputs to be worth
acting on. Run it before changing a site's question, the threshold, or the
model version — and in CI (``jev-eval`` job) when a key is available.

    uv run python scripts/jev_replay.py                 # all sites
    uv run python scripts/jev_replay.py --site skill_match --verbose
    uv run python scripts/jev_replay.py --min-accuracy 0.85 --out report.json

Exit code 1 when any site scores below ``--min-accuracy`` (default 0.8).
Needs ``TYPESAFE_API_KEY`` (from ``.env`` or the environment); the skill and
tool catalogues come from the repo itself, so what Jev sees here is what the
harness shows it in production.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from agent.decide.jev import JevClient, JevConfig
from agent.decide.sites import DecisionConfig, Decisions
from agent.identity import Principal
from agent.memory import Memory
from agent.memory.db import Database, DatabaseConfig
from agent.tools import build_registry
from agent.tools.context import ToolContext

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "jev" / "cases.jsonl"

# A merchant employee, so the registry shows the aliado catalogue.
_ALIADO = Principal(user_id="eval", merchant_id="eval", role="ADMIN")


@dataclass
class Outcome:
    case_id: str
    site: str
    correct: bool
    confidence: float | None
    latency_ms: int
    got: Any
    want: Any


def _load_cases(site: str | None) -> list[dict[str, Any]]:
    cases = [
        json.loads(line) for line in CASES.read_text().splitlines() if line.strip()
    ]
    return [c for c in cases if site is None or c["site"] == site]


def _catalogs() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(merchant tools, merchant skills) exactly as the harness offers them."""
    dummy = httpx.AsyncClient(base_url="http://eval.invalid")
    db = Database(
        DatabaseConfig(
            url=os.environ.get(
                "AGENT_DATABASE_URL", "postgresql+asyncpg://x:x@localhost:1/x"
            )
        )
    )
    registry = build_registry(dummy, db, dummy)
    tools = [
        (str(s["name"]), str(s.get("description", "")))
        for s in registry.schemas(ToolContext(principal=_ALIADO))
    ]
    memory = Memory.__new__(Memory)  # catalogue only: no DB, no client
    memory.skills = {}
    skills = Memory.skill_catalog(memory, "merchant")
    return tools, skills


async def _run_case(
    d: Decisions,
    case: dict[str, Any],
    tools: list[tuple[str, str]],
    skills: list[tuple[str, str]],
    events: list[dict[str, Any]],
) -> Outcome:
    site, want = case["site"], case["expect"]
    events.clear()
    notify = lambda kind, ev: events.append(ev) if kind == "decision" else None  # noqa: E731
    t0 = time.perf_counter()
    got: Any
    correct: bool
    confidence: float | None = None

    if site == "retrieval":
        rv = await d.retrieval(case["message"], notify)
        assert rv is not None
        got = {"retrieve": rv.retrieve, "p": round(rv.p_needs_history, 2)}
        correct = rv.retrieve == want["retrieve"]
        confidence = abs(rv.p_needs_history - 0.5) * 2
    elif site == "skill_match":
        sv = await d.skill_match(case["message"], skills, [], notify)
        picked = sv.skills[0] if sv.skills else None
        got = {"skill": picked, "confidence": round(sv.confidence, 2)}
        correct = picked == want["skill"]
        confidence = sv.confidence
    elif site == "tool_review":
        tv = await d.tool_review(
            case["conversation"],
            case["call"]["tool"],
            case["call"]["args"],
            tools,
            notify,
        )
        assert tv is not None
        got = {
            "fits": tv.p_fits >= 0.5,
            "p_fits": round(tv.p_fits, 2),
            "best_tool": tv.best_tool,
            "confidence": round(tv.best_confidence, 2),
            "nudged": tv.suggestion is not None,
        }
        correct = (tv.p_fits >= 0.5) == want["fits"] and (
            tv.best_tool == want["best_tool"]
        )
        confidence = tv.best_confidence
    elif site == "ask_or_act":
        av = await d.ask_or_act(
            case["conversation"],
            case["prompt"],
            [{"label": o} for o in case["options"]],
            tools,
            notify,
        )
        assert av is not None
        got = {"action": av.action, "confidence": round(av.confidence, 2)}
        correct = av.action == want["action"]
        confidence = av.confidence
    elif site == "judge":
        jv = await d.judge_turn(
            case["user_message"],
            case["reply"],
            case["tools_used"],
            case["skills"],
            case["audience"],
            notify,
        )
        assert jv is not None
        level = round(
            jv.quality
        )  # the expected level, read as the nearest rubric level
        got = {
            "quality": round(jv.quality, 2),
            "level": level,
            "confidence": round(jv.quality_confidence, 2),
            "grounded": jv.p_grounded >= 0.5,
            "llm_judge": jv.needs_llm_judge,
        }
        correct = True
        if "quality_min" in want:
            correct &= level >= want["quality_min"]
        if "quality_max" in want:
            correct &= level <= want["quality_max"]
        if "grounded" in want:
            correct &= (jv.p_grounded >= 0.5) == want["grounded"]
        confidence = jv.quality_confidence
    elif site == "fact_select":
        fv = await d.fact_select(case["facts"], case["existing"], notify)
        kept = [case["facts"].index(f) for f in fv.kept]
        got = {"keep": kept}
        correct = kept == want["keep"]
    elif site == "consolidation_gate":
        cv = await d.consolidation_gate(case["log"], notify)
        got = {"proceed": cv.proceed, "p": round(cv.p_worth_it, 2)}
        correct = cv.proceed == want["proceed"]
        confidence = abs(cv.p_worth_it - 0.5) * 2
    else:
        raise ValueError(f"unknown site {site}")

    latency = events[-1].get("latency_ms") if events else None
    return Outcome(
        case_id=case["id"],
        site=site,
        correct=correct,
        confidence=confidence,
        latency_ms=int(
            latency if latency is not None else (time.perf_counter() - t0) * 1000
        ),
        got=got,
        want=want,
    )


def _summarise(outcomes: list[Outcome]) -> dict[str, Any]:
    by_site: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        by_site[o.site].append(o)
    report: dict[str, Any] = {}
    for site, rows in sorted(by_site.items()):
        right = [o for o in rows if o.correct]
        wrong = [o for o in rows if not o.correct]
        lat = sorted(o.latency_ms for o in rows)
        conf_right = [o.confidence for o in right if o.confidence is not None]
        conf_wrong = [o.confidence for o in wrong if o.confidence is not None]
        report[site] = {
            "cases": len(rows),
            "accuracy": round(len(right) / len(rows), 3),
            "latency_ms": {
                "p50": lat[len(lat) // 2],
                "p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
            },
            "confidence": {
                "right_median": round(statistics.median(conf_right), 2)
                if conf_right
                else None,
                "wrong_median": round(statistics.median(conf_wrong), 2)
                if conf_wrong
                else None,
                "wrong_max": round(max(conf_wrong), 2) if conf_wrong else None,
            },
            "failures": [
                {"id": o.case_id, "got": o.got, "want": o.want} for o in wrong
            ],
        }
    return report


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", default=None)
    parser.add_argument("--min-accuracy", type=float, default=0.8)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key:
        print("TYPESAFE_API_KEY is not set — nothing to replay.", file=sys.stderr)
        return 2

    client = JevClient(
        JevConfig(api_key=key, model=os.environ.get("JEV_MODEL", "jev-latest"))
    )
    decisions = Decisions(client, DecisionConfig(confidence_threshold=args.threshold))
    tools, skills = _catalogs()
    cases = _load_cases(args.site)
    semaphore = asyncio.Semaphore(args.concurrency)

    async def bounded(case: dict[str, Any]) -> Outcome:
        async with semaphore:
            return await _run_case(decisions, case, tools, skills, [])

    try:
        outcomes = await asyncio.gather(*(bounded(c) for c in cases))
    finally:
        await client.aclose()

    report = _summarise(list(outcomes))
    report_out = {
        "model": os.environ.get("JEV_MODEL", "jev-latest"),
        "threshold": args.threshold,
        "cases": len(cases),
        "sites": report,
    }
    if args.out:
        args.out.write_text(json.dumps(report_out, indent=2, ensure_ascii=False))

    failed = False
    for site, r in report.items():
        flag = "OK " if r["accuracy"] >= args.min_accuracy else "LOW"
        failed |= r["accuracy"] < args.min_accuracy
        print(
            f"{flag} {site:<19} {r['accuracy']:>5.0%} ({r['cases']} cases)  "
            f"p50 {r['latency_ms']['p50']} ms  p95 {r['latency_ms']['p95']} ms  "
            f"conf right/wrong {r['confidence']['right_median']}"
            f"/{r['confidence']['wrong_median']}"
        )
        if args.verbose or r["failures"]:
            for f in r["failures"]:
                print(f"      ✗ {f['id']}: got {f['got']} want {f['want']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
