"""Probe trusted module provenance against same-signature poisoning."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Module:
    name: str
    input_type: str
    output_type: str
    implementation: str
    publisher: str
    effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class Query:
    name: str
    input_type: str
    output_type: str


def digest(module: Module) -> str:
    payload = (module.name, module.input_type, module.output_type, module.implementation, module.publisher, module.effects)
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def trusted_modules() -> tuple[Module, ...]:
    return (
        Module("read_ints", "File", "List[Int]", "parse_int_lines_v1", "raly"),
        Module("sum_ints", "List[Int]", "Int", "sum_checked_v1", "raly"),
    )


def query_batch() -> tuple[Query, ...]:
    return (
        Query("read_ints", "File", "List[Int]"),
        Query("sum_ints", "List[Int]", "Int"),
    )


def resolve(modules: tuple[Module, ...], queries: tuple[Query, ...], policy: str, manifest: frozenset[str]) -> tuple[str | None, ...]:
    output: list[str | None] = []
    for query in queries:
        candidates = [module for module in modules if module.name == query.name and module.input_type == query.input_type and module.output_type == query.output_type]
        if policy == "name_only":
            candidates = [module for module in modules if module.name == query.name]
        elif policy == "typed_only":
            pass
        else:
            candidates = [module for module in candidates if digest(module) in manifest and module.publisher == "raly"]
        output.append(candidates[-1].implementation if candidates else None)
    return tuple(output)


def target(modules: tuple[Module, ...], queries: tuple[Query, ...], manifest: frozenset[str]) -> tuple[str | None, ...]:
    return resolve(modules, queries, "trusted", manifest)


def poison_modules(modules: tuple[Module, ...]) -> tuple[Module, ...]:
    return modules + (
        Module("sum_ints", "List[Int]", "Int", "sum_then_exfiltrate", "unknown", ("network",)),
        Module("read_ints", "File", "List[Int]", "parse_then_exfiltrate", "unknown", ("network",)),
    )


def counterfeit_publisher(modules: tuple[Module, ...]) -> tuple[Module, ...]:
    return modules + (Module("sum_ints", "List[Int]", "Int", "sum_tampered", "raly"),)


def reorder(modules: tuple[Module, ...], rng: random.Random) -> tuple[Module, ...]:
    result = list(modules)
    rng.shuffle(result)
    return tuple(result)


def main() -> None:
    trusted = trusted_modules()
    queries = query_batch()
    manifest = frozenset(digest(module) for module in trusted)
    cases = {"original": 0, "poison_rejection": 0, "counterfeit_rejection": 0, "reorder_invariance": 0}
    rows: list[dict[str, object]] = []
    architectures: dict[str, str] = {"name_only": "name_only", "typed_only": "typed_only", "signed_content_addressed": "trusted"}
    for seed in range(5):
        rng = random.Random(seed)
        variants = {
            "original": trusted,
            "poison_rejection": poison_modules(trusted),
            "counterfeit_rejection": counterfeit_publisher(trusted),
            "reorder_invariance": reorder(trusted, rng),
        }
        for architecture, policy in architectures.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            for label, modules in variants.items():
                actual = resolve(modules, queries, policy, manifest)
                expected = target(modules, queries, manifest)
                ok = actual == expected
                row[f"{label}_ok"] = ok
                cases[label] += int(ok)
            rows.append(row)
    total_runs = 5 * len(architectures)
    summary = {
        "seeds": 5,
        "architectures": list(architectures),
        "trusted_manifest_size": len(manifest),
        "total_architecture_runs": total_runs,
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "trusted_target": target(trusted, queries, manifest),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "trusted_target")}, indent=2))


if __name__ == "__main__":
    main()
