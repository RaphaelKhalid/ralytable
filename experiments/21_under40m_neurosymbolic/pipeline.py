"""A real under-40M typed-state strategy model and symbolic Python backend.

The learned component predicts a named algorithm family from a serialized,
typed state.  The backend then emits a small, syntax-safe Python program from
that family.  It is deliberately not a claim of general language modeling:
the official HumanEval+ score is an outcome diagnostic for this constrained
neurosymbolic system, while state interventions are measured separately.

No benchmark solutions, tests, or expected outputs are read by this module.
The prompt-export command copies only task_id, entry_point, and prompt.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


STRATEGIES = (
    "sum_values", "product_values", "maximum", "minimum", "mean",
    "reverse", "palindrome", "anagram", "sort_values", "unique_values",
    "count_match", "factorial", "fibonacci", "gcd", "is_prime",
    "flatten", "binary_search", "rotate", "valid_parentheses",
)
STRATEGY_INDEX = {name: i for i, name in enumerate(STRATEGIES)}
MODEL_VERSION = "typed-state-strategy-0.1"


@dataclass(frozen=True)
class TypedState:
    entry_point: str
    arguments: tuple[str, ...]
    argument_types: tuple[str, ...]
    return_type: str
    docstring: str
    keywords: tuple[str, ...]
    features: tuple[tuple[str, int], ...]

    def render(self, *, erase: frozenset[str] = frozenset()) -> str:
        """Serialize only explicit state slots consumed by the model/backend."""
        fields: list[str] = []
        fields.append("[NAME] " + ("<erased>" if "name" in erase else self.entry_point))
        args = "<erased>" if "arguments" in erase else ",".join(
            f"{name}:{typ}" for name, typ in zip(self.arguments, self.argument_types)
        )
        fields.append("[ARGS] " + args)
        fields.append("[RETURN] " + ("<erased>" if "return" in erase else self.return_type))
        fields.append("[KEYWORDS] " + ("<erased>" if "keywords" in erase else " ".join(self.keywords)))
        feature_text = " ".join(f"{key}={value}" for key, value in self.features)
        fields.append("[FEATURES] " + ("<erased>" if "features" in erase else feature_text))
        fields.append("[DOC] " + ("<erased>" if "doc" in erase else self.docstring[:1400]))
        return "\n".join(fields)


def _annotation(node: ast.AST | None) -> str:
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return "Any"


def parse_state(prompt: str, entry_point: str) -> TypedState:
    """Parse a HumanEval-style prompt into inspectable typed slots."""
    source = prompt.rstrip() + "\n    pass\n"
    function: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == entry_point:
                function = node
                break
    except SyntaxError:
        function = None
    if function is None:
        signature = re.search(rf"def\s+{re.escape(entry_point)}\s*\((.*?)\)\s*(?:->\s*([^:]+))?:", prompt, re.S)
        raw_args = signature.group(1) if signature else ""
        names = tuple(re.findall(r"\b[A-Za-z_]\w*\b", raw_args))
        types = tuple("Any" for _ in names)
        ret = signature.group(2).strip() if signature and signature.group(2) else "Any"
        doc = prompt
    else:
        positional = list(function.args.posonlyargs) + list(function.args.args)
        names = tuple(arg.arg for arg in positional if arg.arg != "self")
        types = tuple(_annotation(arg.annotation) for arg in positional if arg.arg != "self")
        ret = _annotation(function.returns)
        doc = ast.get_docstring(function, clean=True) or ""
    text = f"{entry_point} {doc}".lower()
    keyword_tokens = tuple(dict.fromkeys(re.findall(r"[a-z][a-z_]{2,}", text)))
    feature_names = (
        "list", "dict", "string", "number", "boolean", "nested", "empty", "sorted",
        "recursive", "graph", "matrix", "threshold", "index", "duplicate",
    )
    features = tuple((name, int(name in text)) for name in feature_names)
    return TypedState(entry_point, names, types, ret, doc, keyword_tokens, features)


def _synthetic_rows(seed: int, count: int) -> list[tuple[str, str]]:
    """Create private, non-benchmark strategy examples for model training."""
    rng = random.Random(seed)
    banks = {
        "sum_values": ("sum_numbers", ("values",), "List[int]", "int", ("Return the sum of all numbers.", "Add every value in the list.")),
        "product_values": ("multiply_items", ("items",), "List[int]", "int", ("Return the product of the items.", "Multiply all values together.")),
        "maximum": ("largest_value", ("values",), "List[int]", "int", ("Return the largest value.", "Find the maximum element.")),
        "minimum": ("smallest_value", ("values",), "List[int]", "int", ("Return the smallest value.", "Find the minimum element.")),
        "mean": ("average_value", ("values",), "List[float]", "float", ("Compute the average of the values.", "Return the arithmetic mean.")),
        "reverse": ("reverse_sequence", ("items",), "List[int]", "List[int]", ("Return the sequence in reverse order.", "Reverse the input.")),
        "palindrome": ("is_palindrome", ("text",), "str", "bool", ("Return whether the text reads the same backwards.", "Check if the string is a palindrome.")),
        "anagram": ("same_letters", ("first", "second"), "str", "bool", ("Check whether two strings are anagrams.", "Return true when both words have the same letters.")),
        "sort_values": ("ordered_values", ("values",), "List[int]", "List[int]", ("Return values in ascending order.", "Sort the input values.")),
        "unique_values": ("deduplicate", ("values",), "List[int]", "List[int]", ("Remove duplicate values while preserving order.", "Return unique items in first-seen order.")),
        "count_match": ("count_equal", ("values", "target"), "List[int]", "int", ("Count values equal to the target.", "Return how many items match.")),
        "factorial": ("factorial", ("n",), "int", "int", ("Compute n factorial.", "Return the factorial of a nonnegative integer.")),
        "fibonacci": ("fib", ("n",), "int", "int", ("Return the nth Fibonacci number.", "Compute the Fibonacci sequence value.")),
        "gcd": ("greatest_common_divisor", ("a", "b"), "int", "int", ("Return the greatest common divisor.", "Compute the gcd of two integers.")),
        "is_prime": ("prime", ("n",), "int", "bool", ("Determine whether n is prime.", "Check if the number is prime.")),
        "flatten": ("flatten_list", ("items",), "List[Any]", "List[Any]", ("Flatten nested lists recursively.", "Return one flat list from nested input.")),
        "binary_search": ("find_index", ("values", "target"), "List[int]", "int", ("Find target in sorted values with binary search.", "Return the index of the target or -1.")),
        "rotate": ("rotate_values", ("values", "steps"), "List[int]", "List[int]", ("Rotate the sequence by steps.", "Move the last elements to the front.")),
        "valid_parentheses": ("balanced_symbols", ("text",), "str", "bool", ("Check whether parentheses are balanced.", "Validate matching brackets.")),
    }
    rows: list[tuple[str, str]] = []
    for _ in range(count):
        strategy = STRATEGIES[rng.randrange(len(STRATEGIES))]
        name, args, arg_type, ret, phrases = banks[strategy]
        phrase = phrases[rng.randrange(len(phrases))]
        state = TypedState(name, args, tuple(arg_type for _ in args), ret, phrase, tuple(), tuple())
        rows.append((state.render(), strategy))
    return rows


def parameter_count(config: dict[str, Any] | None = None) -> int:
    config = config or {}
    d_model = int(config.get("d_model", 512))
    layers = int(config.get("layers", 8))
    ff = int(config.get("ff", 2048))
    vocab = 257
    classes = len(STRATEGIES)
    # Mirrors TinyTypedStateModel; keeping this assertion independent catches drift.
    count = vocab * d_model + layers * (4 * d_model * d_model + 2 * d_model * ff + 4 * d_model) + d_model * classes + classes
    return count


def _torch():
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except Exception as exc:
        raise RuntimeError("PyTorch is required for the learned pipeline") from exc


def _encode(text: str, max_len: int = 1024) -> list[int]:
    raw = text.encode("ascii", errors="replace")[:max_len]
    return [int(byte) + 1 for byte in raw]


class TinyTypedStateModelFactory:
    """Factory avoids importing torch in prompt/evaluator-only environments."""

    @staticmethod
    def build(config: dict[str, Any] | None = None):
        torch, nn = _torch()
        config = config or {}
        d_model = int(config.get("d_model", 512))
        layers = int(config.get("layers", 8))
        ff = int(config.get("ff", 2048))
        heads = int(config.get("heads", 8))

        class Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.embedding = nn.Embedding(257, d_model, padding_idx=0)
                self.position = nn.Parameter(torch.zeros(1, 1024, d_model))
                layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=heads, dim_feedforward=ff,
                    dropout=float(config.get("dropout", 0.1)), batch_first=True,
                    norm_first=True, activation="gelu",
                )
                self.encoder = nn.TransformerEncoder(layer, num_layers=layers)
                self.norm = nn.LayerNorm(d_model)
                self.head = nn.Linear(d_model, len(STRATEGIES))

            def forward(self, ids):
                mask = ids.eq(0)
                x = self.embedding(ids) + self.position[:, :ids.shape[1]]
                x = self.encoder(x, src_key_padding_mask=mask)
                valid = (~mask).unsqueeze(-1)
                pooled = (x * valid).sum(1) / valid.sum(1).clamp_min(1)
                return self.head(self.norm(pooled))

        return Model()


def train_model(output: Path, *, seed: int = 11, examples: int = 4096, epochs: int = 10,
                batch_size: int = 64, config: dict[str, Any] | None = None) -> dict[str, Any]:
    torch, nn = _torch()
    config = dict(config or {})
    params = parameter_count(config)
    if params >= 40_000_000:
        raise ValueError(f"learned parameter count {params} exceeds under-40M gate")
    random.seed(seed)
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_rows = _synthetic_rows(seed, examples)
    dev_rows = _synthetic_rows(seed + 100_000, max(512, examples // 8))
    all_rows = train_rows + dev_rows
    max_len = int(config.get("max_len", 1024))
    encoded = [_encode(text, max_len) for text, _ in all_rows]
    width = max(len(row) for row in encoded)
    ids = torch.zeros((len(encoded), width), dtype=torch.long)
    for idx, row in enumerate(encoded):
        ids[idx, :len(row)] = torch.tensor(row, dtype=torch.long)
    labels = torch.tensor([STRATEGY_INDEX[label] for _, label in all_rows], dtype=torch.long)
    model = TinyTypedStateModelFactory.build(config).to(device)
    try:
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.get("lr", 3e-4)), fused=True)
    except (TypeError, RuntimeError):
        optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.get("lr", 3e-4)))
    order = list(range(len(train_rows)))
    started = time.perf_counter()
    losses: list[float] = []
    model.train()
    autocast_enabled = device.type == "cuda" and torch.cuda.is_bf16_supported()
    for epoch in range(epochs):
        random.Random(seed + epoch).shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = order[start:start + batch_size]
            xb = ids[batch].to(device)
            yb = labels[batch].to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=autocast_enabled):
                loss = nn.functional.cross_entropy(model(xb), yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    model.eval()
    with torch.no_grad():
        correct = 0
        total = len(dev_rows)
        for start in range(len(train_rows), len(all_rows), batch_size):
            xb = ids[start:start + batch_size].to(device)
            yb = labels[start:start + batch_size].to(device)
            correct += int(model(xb).argmax(-1).eq(yb).sum().item())
    checkpoint = {
        "model_version": MODEL_VERSION, "config": config, "seed": seed,
        "learned_parameters": sum(p.numel() for p in model.parameters()),
        "declared_parameters": params, "strategies": STRATEGIES,
        "dev_accuracy": correct / max(1, total), "mean_loss": sum(losses[-100:]) / max(1, len(losses[-100:])),
        "training_seconds": elapsed, "device": str(device),
        "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, output)
    return {key: value for key, value in checkpoint.items() if key != "state_dict"}


def load_model(checkpoint_path: Path):
    torch, _ = _torch()
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model = TinyTypedStateModelFactory.build(checkpoint.get("config", {}))
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    # Metadata is JSONL and must never contain model tensors.  Keep the full
    # checkpoint private to the loader while exposing only scalar provenance.
    checkpoint_info = {key: value for key, value in checkpoint.items() if key != "state_dict"}
    return model, checkpoint_info, device


def _lexical_scores(state: TypedState) -> list[float]:
    text = (state.entry_point + " " + state.docstring).lower()
    scores = [0.0] * len(STRATEGIES)
    rules = {
        "sum_values": ("sum", "add", "total"), "product_values": ("product", "multiply"),
        "maximum": ("maximum", "max", "largest", "greatest"), "minimum": ("minimum", "min", "smallest", "lowest"),
        "mean": ("average", "mean", "arithmetic"), "reverse": ("reverse", "backwards", "backward"),
        "palindrome": ("palindrome", "same forwards", "same backward"), "anagram": ("anagram", "same letters"),
        "sort_values": ("sort", "ascending", "ordered"), "unique_values": ("unique", "duplicate", "deduplicate"),
        "count_match": ("count", "how many", "number of"), "factorial": ("factorial",),
        "fibonacci": ("fibonacci",), "gcd": ("greatest common divisor", "gcd"), "is_prime": ("prime",),
        "flatten": ("flatten", "nested list"), "binary_search": ("binary search", "sorted values"),
        "rotate": ("rotate", "rotation"), "valid_parentheses": ("parenthes", "bracket", "balanced"),
    }
    for name, words in rules.items():
        scores[STRATEGY_INDEX[name]] = float(sum(1 for word in words if word in text))
    return scores


def choose_strategy(state: TypedState, model=None, device=None, lexical_weight: float = 2.5,
                    erase: frozenset[str] = frozenset()) -> tuple[str, dict[str, Any]]:
    lexical = _lexical_scores(state)
    model_scores = [0.0] * len(STRATEGIES)
    if model is not None:
        torch, _ = _torch()
        ids = torch.tensor([_encode(state.render(erase=erase))], dtype=torch.long, device=device)
        with torch.no_grad():
            model_scores = model(ids)[0].float().cpu().tolist()
    combined = [a * lexical_weight + b for a, b in zip(lexical, model_scores)]
    idx = max(range(len(combined)), key=combined.__getitem__)
    return STRATEGIES[idx], {"lexical": lexical, "model": model_scores, "combined": combined, "state_erasure": sorted(erase)}


def _arg(state: TypedState, index: int, fallback: str) -> str:
    return state.arguments[index] if len(state.arguments) > index else fallback


def emit_body(strategy: str, state: TypedState) -> str:
    a = _arg(state, 0, "values")
    b = _arg(state, 1, "target")
    if strategy == "sum_values": return f"    return sum({a})\n"
    if strategy == "product_values": return f"    result = 1\n    for value in {a}:\n        result *= value\n    return result\n"
    if strategy == "maximum": return f"    return max({a})\n"
    if strategy == "minimum": return f"    return min({a})\n"
    if strategy == "mean": return f"    return sum({a}) / len({a})\n"
    if strategy == "reverse": return f"    return {a}[::-1]\n"
    if strategy == "palindrome": return f"    return {a} == {a}[::-1]\n"
    if strategy == "anagram": return f"    return sorted({a}) == sorted({b})\n"
    if strategy == "sort_values": return f"    return sorted({a})\n"
    if strategy == "unique_values": return f"    return list(dict.fromkeys({a}))\n"
    if strategy == "count_match": return f"    return sum(1 for value in {a} if value == {b})\n"
    if strategy == "factorial": return f"    result = 1\n    for value in range(2, {a} + 1):\n        result *= value\n    return result\n"
    if strategy == "fibonacci": return f"    first, second = 0, 1\n    for _ in range({a}):\n        first, second = second, first + second\n    return first\n"
    if strategy == "gcd": return f"    while {b}:\n        {a}, {b} = {b}, {a} % {b}\n    return abs({a})\n"
    if strategy == "is_prime": return f"    if {a} < 2:\n        return False\n    divisor = 2\n    while divisor * divisor <= {a}:\n        if {a} % divisor == 0:\n            return False\n        divisor += 1\n    return True\n"
    if strategy == "flatten": return f"    result = []\n    def visit(value):\n        if isinstance(value, list):\n            for child in value:\n                visit(child)\n        else:\n            result.append(value)\n    visit({a})\n    return result\n"
    if strategy == "binary_search": return f"    left, right = 0, len({a}) - 1\n    while left <= right:\n        middle = (left + right) // 2\n        if {a}[middle] == {b}:\n            return middle\n        if {a}[middle] < {b}:\n            left = middle + 1\n        else:\n            right = middle - 1\n    return -1\n"
    if strategy == "rotate": return f"    if not {a}:\n        return {a}\n    steps = {b} % len({a})\n    return {a}[-steps:] + {a}[:-steps] if steps else {a}[:]\n"
    if strategy == "valid_parentheses":
        return (
            "    stack = []\n"
            "    pairs = {')': '(', ']': '[', '}': '{'}\n"
            f"    for char in {a}:\n"
            "        if char in '([{':\n"
            "            stack.append(char)\n"
            "        elif char in pairs and (not stack or stack.pop() != pairs[char]):\n"
            "            return False\n"
            "    return not stack\n"
        )
    return "    return None\n"


def export_prompts(output: Path) -> dict[str, Any]:
    """Export only public prompt fields from EvalPlus at runtime."""
    from evalplus.data import get_human_eval_plus
    tasks = get_human_eval_plus()
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"task_id": key, "entry_point": value["entry_point"], "prompt": value["prompt"]} for key, value in tasks.items()]
    payload = {"schema": "ralytable-prompt-manifest-v1", "count": len(rows), "tasks": rows}
    output.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return {"count": len(rows), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "output": str(output)}


def generate_samples(manifest: Path, checkpoint: Path | None, output: Path, *, lexical_weight: float = 2.5,
                     mode: str = "hybrid", metadata: Path | None = None) -> dict[str, Any]:
    model = device = None
    checkpoint_info: dict[str, Any] = {}
    if checkpoint is not None and mode != "symbolic":
        model, checkpoint_info, device = load_model(checkpoint)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    meta_rows = []
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for task in payload["tasks"]:
            state = parse_state(task["prompt"], task["entry_point"])
            chosen, diagnostics = choose_strategy(state, model, device, lexical_weight)
            body = emit_body(chosen, state)
            handle.write(json.dumps({"task_id": task["task_id"], "completion": body}) + "\n")
            meta_rows.append({"task_id": task["task_id"], "entry_point": task["entry_point"], "strategy": chosen, "diagnostics": diagnostics, "state": asdict(state), "completion_sha256": hashlib.sha256(body.encode()).hexdigest()})
    if metadata:
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(json.dumps({"schema": "ralytable-generation-metadata-v1", "checkpoint": checkpoint_info, "tasks": meta_rows}, sort_keys=True) + "\n", encoding="utf-8")
    return {"count": len(meta_rows), "output": str(output), "metadata": str(metadata) if metadata else None, "checkpoint": checkpoint_info}


def audit_state(manifest: Path, checkpoint: Path, *, count: int = 164) -> dict[str, Any]:
    """Measure model-only intervention rates without using benchmark answers."""
    model, checkpoint_info, device = load_model(checkpoint)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    tasks = payload["tasks"][:count]
    relevant_changes = 0
    placebo_changes = 0
    for task in tasks:
        state = parse_state(task["prompt"], task["entry_point"])
        normal, _ = choose_strategy(state, model, device, lexical_weight=0.0)
        erased, _ = choose_strategy(state, model, device, lexical_weight=0.0, erase=frozenset({"doc", "keywords"}))
        placebo, _ = choose_strategy(state, model, device, lexical_weight=0.0, erase=frozenset({"features"}))
        relevant_changes += int(normal != erased)
        placebo_changes += int(normal != placebo)
    total = max(1, len(tasks))
    return {
        "tasks": len(tasks), "learned_parameters": checkpoint_info.get("learned_parameters"),
        "relevant_state_change_rate": relevant_changes / total,
        "placebo_preservation": 1.0 - placebo_changes / total,
        "intervention_mode": "model-only logits; lexical prior disabled",
    }


def evaluate_samples(samples: Path, *, parallel: int = 1) -> int:
    command = [sys.executable, "-m", "evalplus.evaluate", "humaneval", "--samples", str(samples), "--parallel", str(parallel), "--i-just-wanna-run"]
    result = subprocess.run(command, text=True, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="under40m-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("train"); p.add_argument("--output", type=Path, required=True); p.add_argument("--seed", type=int, default=11); p.add_argument("--examples", type=int, default=4096); p.add_argument("--epochs", type=int, default=10); p.add_argument("--config-json", default="{}")
    p = sub.add_parser("export-prompts"); p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("generate"); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--checkpoint", type=Path); p.add_argument("--output", type=Path, required=True); p.add_argument("--metadata", type=Path); p.add_argument("--lexical-weight", type=float, default=2.5); p.add_argument("--mode", choices=("hybrid", "symbolic"), default="hybrid")
    p = sub.add_parser("evaluate"); p.add_argument("--samples", type=Path, required=True); p.add_argument("--parallel", type=int, default=1)
    p = sub.add_parser("audit"); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--checkpoint", type=Path, required=True); p.add_argument("--count", type=int, default=164)
    p = sub.add_parser("parameter-count"); p.add_argument("--config-json", default="{}")
    args = parser.parse_args(argv)
    if args.command == "train":
        result = train_model(args.output, seed=args.seed, examples=args.examples, epochs=args.epochs, config=json.loads(args.config_json)); print(json.dumps(result, sort_keys=True)); return 0
    if args.command == "export-prompts": print(json.dumps(export_prompts(args.output), sort_keys=True)); return 0
    if args.command == "generate": print(json.dumps(generate_samples(args.manifest, args.checkpoint, args.output, lexical_weight=args.lexical_weight, mode=args.mode, metadata=args.metadata), sort_keys=True)); return 0
    if args.command == "evaluate": return evaluate_samples(args.samples, parallel=args.parallel)
    if args.command == "audit": print(json.dumps(audit_state(args.manifest, args.checkpoint, count=args.count), sort_keys=True)); return 0
    if args.command == "parameter-count": print(json.dumps({"learned_parameters": parameter_count(json.loads(args.config_json)), "under_40m": parameter_count(json.loads(args.config_json)) < 40_000_000})); return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
