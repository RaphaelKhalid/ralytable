"""Count auditable parameter allocations for a sub-40M architecture."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Budget:
    name: str
    hidden: int
    feedforward: int
    parser_layers: int
    router_hidden: int
    router_layers: int
    module_count: int
    module_width: int
    verifier_heads: int


def linear(in_features: int, out_features: int, bias: bool = True) -> int:
    return in_features * out_features + (out_features if bias else 0)


def count(budget: Budget) -> dict[str, int]:
    d = budget.hidden
    parser_block = 4 * d * d + 2 * d * budget.feedforward + 4 * d + budget.feedforward + d
    parser = 256 * d + budget.parser_layers * parser_block
    router = 256 * budget.router_hidden + budget.router_layers * (
        4 * budget.router_hidden * budget.router_hidden
        + 2 * budget.router_hidden * (4 * budget.router_hidden)
        + 5 * budget.router_hidden
    )
    # Each module has an auditable typed signature projection and a compact
    # implementation descriptor; no free-form neural residual is included.
    module_bank = budget.module_count * (linear(d, budget.module_width) + linear(budget.module_width, d) + 4 * budget.module_width)
    retrieval = linear(d, d) + linear(d, d) + 2 * d
    heads = (
        linear(d, 128)  # operation/type logits
        + linear(d, 64)  # scope/binder logits
        + linear(d, 64)  # effect/capability logits
        + budget.verifier_heads * linear(d, 128)
    )
    explicit_copy = 256 * 64 + 64 * d
    total = parser + router + module_bank + retrieval + heads + explicit_copy
    return {
        "byte_parser": parser,
        "typed_graph_router": router,
        "typed_module_bank": module_bank,
        "retrieval_interfaces": retrieval,
        "typed_effect_verifier_heads": heads,
        "explicit_copy_channel": explicit_copy,
        "total_learned": total,
        "opaque_residual_bypass": 0,
        "headroom_to_40m": 40_000_000 - total,
    }


def main() -> None:
    configs = (
        Budget("lean_parser", 384, 1536, 8, 256, 3, 64, 128, 4),
        Budget("balanced_ledger", 448, 1792, 8, 288, 4, 96, 160, 6),
        Budget("verifier_heavy", 384, 1536, 6, 320, 5, 80, 160, 12),
    )
    rows = []
    for config in configs:
        components = count(config)
        rows.append({"name": config.name, "config": config.__dict__, "components": components, "under_40m": components["total_learned"] < 40_000_000})
    summary = {
        "hard_constraints": {
            "parameter_cap": 40_000_000,
            "opaque_residual_bypass": 0,
            "learned_state_roles": ["byte_parser", "typed_graph_router", "typed_module_bank", "retrieval_interfaces", "typed_effect_verifier_heads", "explicit_copy_channel"],
        },
        "rows": rows,
        "all_under_cap": all(row["under_40m"] for row in rows),
    }
    Path(__file__).with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_under_cap": summary["all_under_cap"], "budgets": [{"name": row["name"], "total_learned": row["components"]["total_learned"], "headroom_to_40m": row["components"]["headroom_to_40m"], "opaque_residual_bypass": row["components"]["opaque_residual_bypass"]} for row in rows]}, indent=2))


if __name__ == "__main__":
    main()
