"""Transparent parameter accounting for a typed-ledger coder design.

The accounting describes one possible low-rank, byte-level front end. It does
not claim that the design trains or matches a large coder. Every term is named
so a future implementation can replace estimates with measured counts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


LIMIT = 40_000_000
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    name: str
    width: int
    layers: int
    rank: int
    slots: int
    modules: int
    module_width: int
    max_ledger_nodes: int


def account(config: Config) -> dict[str, int | float | bool | str]:
    d, l, r = config.width, config.layers, config.rank
    terms = {
        # Byte vocabulary keeps the lexical table small and makes token IDs
        # inspectable; code-specific subword vocabularies are a later variant.
        "byte_embedding": 257 * d,
        # Each block has four low-rank projections. A factor pair has d*r + r*d
        # learned scalars; the activation is fixed GELU-free gated addition.
        "low_rank_attention": l * 4 * (d * r + r * d),
        # Two low-rank state-update maps plus one named scalar gate per layer.
        "low_rank_state_update": l * (2 * (d * r + r * d) + 2 * d),
        # Learned initial slot queries; slot updates use the shared maps above.
        "slot_queries": config.slots * d,
        # Router emits one score per fixed module from each state slot.
        "module_router": config.slots * d * config.module_width + config.module_width * config.modules,
        # Fixed-shape module descriptors are learned but each row maps to one
        # auditable operation family; the executor itself is deterministic.
        "module_descriptors": config.modules * config.module_width,
        # Typed graph legality and output heads.
        "type_and_schema_heads": 8 * d * d + 4 * d * config.modules,
        "normalisation_and_bias": l * 4 * d + config.modules,
    }
    total = sum(terms.values())
    named = sum(terms[key] for key in ("slot_queries", "module_router", "module_descriptors", "type_and_schema_heads"))
    return {
        "name": config.name,
        "learned_parameters": total,
        "under_40m": total < LIMIT,
        "named_mechanism_parameters": named,
        "named_mechanism_fraction": named / total,
        "opaque_front_end_parameters": total - named,
        "opaque_front_end_fraction": (total - named) / total,
        "max_ledger_nodes": config.max_ledger_nodes,
        "module_count": config.modules,
        "formula_terms": terms,
    }


CONFIGS = (
    Config("byte_lowrank_ledger", 512, 8, 64, 16, 128, 64, 32),
    Config("compact_graph_router", 384, 6, 48, 24, 192, 48, 48),
    Config("retrieval_heavy_router", 256, 4, 32, 32, 256, 32, 64),
    Config("wide_module_bank", 512, 6, 48, 16, 256, 64, 32),
)


def main() -> None:
    rows = [account(config) for config in CONFIGS]
    for row in rows:
        print(json.dumps(row, sort_keys=True))
    output = {"limit": LIMIT, "configs": rows,
              "note": "Budget accounting only; no model was trained and no capability score is implied."}
    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
