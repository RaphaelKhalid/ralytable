"""Probe transitive module effects against a caller capability budget."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Module:
    name: str
    declared_effects: frozenset[str]
    calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class Program:
    modules: tuple[Module, ...]
    entry: str
    capabilities: frozenset[str]


def base_program() -> Program:
    return Program(
        modules=(
            Module("read_file", frozenset({"read"})),
            Module("normalize", frozenset()),
            Module("safe_wrapper", frozenset({"read"}), ("read_file", "normalize")),
        ),
        entry="safe_wrapper",
        capabilities=frozenset({"read"}),
    )


def by_name(program: Program) -> dict[str, Module]:
    return {module.name: module for module in program.modules}


def declared_only(program: Program) -> bool:
    modules = by_name(program)
    return modules[program.entry].declared_effects <= program.capabilities


def shallow_effects(program: Program) -> bool:
    modules = by_name(program)
    entry = modules[program.entry]
    direct = set(entry.declared_effects)
    direct.update(effect for child in entry.calls for effect in modules[child].declared_effects)
    return direct <= program.capabilities


def transitive_ledger(program: Program) -> bool:
    modules = by_name(program)
    active: set[str] = set()
    memo: dict[str, frozenset[str]] = {}

    def effects(name: str) -> frozenset[str]:
        if name in memo:
            return memo[name]
        if name in active:
            return frozenset({"cycle"})
        active.add(name)
        module = modules[name]
        result = set(module.declared_effects)
        for child in module.calls:
            result.update(effects(child))
        active.remove(name)
        memo[name] = frozenset(result)
        return memo[name]

    return effects(program.entry) <= program.capabilities


ARCHITECTURES: dict[str, Callable[[Program], bool]] = {
    "declared_only": declared_only,
    "shallow_effects": shallow_effects,
    "transitive_capability_ledger": transitive_ledger,
}


def hidden_network_wrapper(program: Program) -> Program:
    modules = program.modules + (Module("network_send", frozenset({"network"})),)
    modules = tuple(replace(module, calls=("network_send",)) if module.name == "safe_wrapper" else module for module in modules)
    return replace(program, modules=modules)


def nested_hidden_network(program: Program) -> Program:
    modules = program.modules + (
        Module("network_send", frozenset({"network"})),
        Module("nested_wrapper", frozenset(), ("network_send",)),
    )
    modules = tuple(replace(module, calls=("nested_wrapper",)) if module.name == "safe_wrapper" else module for module in modules)
    return replace(program, modules=modules)


def cycle(program: Program) -> Program:
    modules = tuple(replace(module, calls=("safe_wrapper",)) if module.name == "normalize" else module for module in program.modules)
    return replace(program, modules=modules)


def reorder_modules(program: Program, rng: random.Random) -> Program:
    modules = list(program.modules)
    rng.shuffle(modules)
    return replace(program, modules=tuple(modules))


def main() -> None:
    cases = {"original": 0, "hidden_network_rejection": 0, "nested_hidden_rejection": 0, "cycle_rejection": 0, "reorder_invariance": 0}
    rows: list[dict[str, object]] = []
    for seed in range(5):
        rng = random.Random(seed)
        program = base_program()
        variants = {
            "hidden_network_rejection": hidden_network_wrapper(program),
            "nested_hidden_rejection": nested_hidden_network(program),
            "cycle_rejection": cycle(program),
            "reorder_invariance": reorder_modules(program, rng),
        }
        for architecture, run in ARCHITECTURES.items():
            row: dict[str, object] = {"seed": seed, "architecture": architecture}
            row["original_exact"] = run(program) == transitive_ledger(program)
            cases["original"] += int(row["original_exact"])
            for label, variant in variants.items():
                ok = run(variant) == transitive_ledger(variant)
                row[f"{label}_ok"] = ok
                cases[label] += int(ok)
            rows.append(row)
    total_runs = 5 * len(ARCHITECTURES)
    summary = {
        "seeds": 5,
        "architectures": list(ARCHITECTURES),
        "total_architecture_runs": total_runs,
        "pass_counts": cases,
        "pass_rates": {key: round(value / total_runs, 4) for key, value in cases.items()},
        "base_effects": sorted({"read"}),
        "rows": rows,
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("pass_counts", "pass_rates", "base_effects")}, indent=2))


if __name__ == "__main__":
    main()
