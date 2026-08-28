"""Generate private Raly Coder v1 tasks and a public hash-only manifest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Any


GENERATOR_VERSION = "raly-coder-v1-generator-2026-08-27"
FAMILIES = (
    "boundary_off_by_one", "tree_graph_traversal", "parser_tokenizer_edge",
    "state_cache_invalidation", "serialization_round_trip", "error_validation",
    "sorting_stable_order", "numeric_empty_input",
)
SPLITS = {
    "train": (48, 10_000), "dev": (8, 20_000),
    "private_test": (16, 30_000), "private_replication": (16, 40_000),
}
TASKS_PER_REPOSITORY = 24


@dataclass(frozen=True)
class Task:
    task_id: str
    split: str
    repository_id: str
    repository_seed: int
    task_index: int
    family: str
    request: str
    files: dict[str, str]
    visible_tests: dict[str, str]
    hidden_tests: str
    oracle_patch: dict[str, str]

    def private_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _task_common(*, split: str, repository_seed: int, task_index: int,
                 family: str, request: str, source: str, visible: str,
                 hidden: str, old_text: str, new_text: str) -> Task:
    repository_id = f"repo-{split}-{repository_seed}"
    return Task(
        task_id=f"{split}-{repository_seed}-{task_index:02d}",
        split=split, repository_id=repository_id,
        repository_seed=repository_seed, task_index=task_index, family=family,
        request=request, files={"app.py": source},
        visible_tests={"tests/test_visible.py": visible}, hidden_tests=hidden,
        oracle_patch={
            "path": "app.py", "old_text": old_text, "new_text": new_text,
            "expected_sha256": _sha256(source.encode()),
        },
    )


def _build_boundary(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def window_sums(values, width):
    if width <= 0:
        raise ValueError("width must be positive")
    return [sum(values[i:i + width]) for i in range(len(values) - width)]
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = source.replace("range(len(values) - width)",
                           "range(len(values) - width + 1)")
    visible = '''import unittest
from app import window_sums


class VisibleTests(unittest.TestCase):
    def test_single_window(self):
        self.assertEqual(window_sums([2, 5], 2), [7])
'''
    hidden = '''import unittest
from app import window_sums


class HiddenBoundary(unittest.TestCase):
    def test_last_valid_start_is_included(self):
        self.assertEqual(window_sums([1, 2, 3, 4], 2), [3, 5, 7])
'''
    return _task_common(request="Fix window_sums so every valid window is returned.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_tree(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def tree_height(node):
    children = node.get("children", [])
    if not children:
        return 1
    return 1 + max(tree_height(child) for child in children[:-1])
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = source.replace("children[:-1]", "children")
    visible = '''import unittest
from app import tree_height


class VisibleTests(unittest.TestCase):
    def test_leaf(self):
        self.assertEqual(tree_height({"value": "root"}), 1)
'''
    hidden = '''import unittest
from app import tree_height


class HiddenTree(unittest.TestCase):
    def test_last_child_is_not_ignored(self):
        node = {"children": [{"children": [{"value": 1}]}, {"value": 2}]}
        self.assertEqual(tree_height(node), 3)
'''
    return _task_common(request="Fix tree_height so every child contributes to the height.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_parser(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def tokenize(line):
    return [part.strip() for part in line.split(",") if part.strip()]
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = '''import csv
from io import StringIO


def tokenize(line):
    return [part.strip() for part in next(csv.reader(StringIO(line)))]
'''
    visible = '''import unittest
from app import tokenize


class VisibleTests(unittest.TestCase):
    def test_simple_fields(self):
        self.assertEqual(tokenize("red, blue"), ["red", "blue"])
'''
    hidden = '''import unittest
from app import tokenize


class HiddenParser(unittest.TestCase):
    def test_quoted_separator_is_data(self):
        self.assertEqual(tokenize('red,"blue,green",yellow'),
                         ["red", "blue,green", "yellow"])
'''
    return _task_common(request="Fix tokenize so quoted separators remain inside one field.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_cache(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''class ValueCache:
    def __init__(self):
        self.values = {}

    def update(self, key, value):
        self.values.setdefault(key, value)

    def get(self, key):
        return self.values[key]
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = source.replace("self.values.setdefault(key, value)",
                           "self.values[key] = value")
    visible = '''import unittest
from app import ValueCache


class VisibleTests(unittest.TestCase):
    def test_insert(self):
        cache = ValueCache()
        cache.update("a", 1)
        self.assertEqual(cache.get("a"), 1)
'''
    hidden = '''import unittest
from app import ValueCache


class HiddenCache(unittest.TestCase):
    def test_update_replaces_old_value(self):
        cache = ValueCache()
        cache.update("a", 1)
        cache.update("a", 2)
        self.assertEqual(cache.get("a"), 2)
'''
    return _task_common(request="Fix ValueCache.update so replacing a key invalidates its old value.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_serialization(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def encode(data):
    return "|".join(f"{key}={value}" for key, value in data.items())


def decode(text):
    return {part.split("=", 1)[0]: part.split("=", 1)[1]
            for part in text.split("|") if part}
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = '''import json


def encode(data):
    return json.dumps(data, sort_keys=True)


def decode(text):
    return json.loads(text)
'''
    visible = '''import unittest
from app import decode, encode


class VisibleTests(unittest.TestCase):
    def test_simple_round_trip(self):
        value = {"name": "raly", "version": "1"}
        self.assertEqual(decode(encode(value)), value)
'''
    hidden = '''import unittest
from app import decode, encode


class HiddenSerialization(unittest.TestCase):
    def test_nested_and_delimiter_values_round_trip(self):
        value = {"name": "red|blue", "items": [1, 2, {"ok": True}]}
        self.assertEqual(decode(encode(value)), value)
'''
    return _task_common(request="Make encode/decode preserve nested values and delimiters during round-trip.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_validation(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def require_int(value):
    if not value:
        raise ValueError("an integer is required")
    return int(value)
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = source.replace("if not value:", "if value is None:")
    visible = '''import unittest
from app import require_int


class VisibleTests(unittest.TestCase):
    def test_positive_integer(self):
        self.assertEqual(require_int(3), 3)
'''
    hidden = '''import unittest
from app import require_int


class HiddenValidation(unittest.TestCase):
    def test_zero_is_a_valid_integer(self):
        self.assertEqual(require_int(0), 0)
'''
    return _task_common(request="Fix require_int so zero is accepted as a valid integer.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_sorting(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def order_records(records):
    return sorted(records, key=lambda record: record["group"], reverse=True)
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = source.replace(', reverse=True', '')
    visible = '''import unittest
from app import order_records


class VisibleTests(unittest.TestCase):
    def test_same_group_is_unchanged(self):
        records = [{"group": 1, "name": "a"}, {"group": 1, "name": "b"}]
        self.assertEqual(order_records(records), records)
'''
    hidden = '''import unittest
from app import order_records


class HiddenSorting(unittest.TestCase):
    def test_groups_are_ascending_and_stable(self):
        records = [{"group": 2, "name": "b"}, {"group": 1, "name": "a"},
                   {"group": 2, "name": "c"}]
        self.assertEqual(order_records(records),
                         [{"group": 1, "name": "a"},
                          {"group": 2, "name": "b"},
                          {"group": 2, "name": "c"}])
'''
    return _task_common(request="Fix order_records to sort groups ascending while preserving ties.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


def _build_numeric(*, rng: random.Random, **kwargs: Any) -> Task:
    source = '''def mean(values):
    return sum(values) / len(values)
'''
    source = f"CASE_ID = {rng.randrange(1_000_000)}\n\n" + source
    fixed = source.replace(
        "    return sum(values) / len(values)",
        "    if not values:\n        return None\n    return sum(values) / len(values)",
    )
    visible = '''import unittest
from app import mean


class VisibleTests(unittest.TestCase):
    def test_nonempty_mean(self):
        self.assertEqual(mean([2, 4]), 3)
'''
    hidden = '''import unittest
from app import mean


class HiddenNumeric(unittest.TestCase):
    def test_empty_input_is_defined(self):
        self.assertIsNone(mean([]))
'''
    return _task_common(request="Fix mean so empty input has a defined result instead of raising.",
                        source=source, visible=visible, hidden=hidden,
                        old_text=source, new_text=fixed, **kwargs)


BUILDERS = dict(zip(FAMILIES, (
    _build_boundary, _build_tree, _build_parser, _build_cache,
    _build_serialization, _build_validation, _build_sorting, _build_numeric,
)))


def make_task(split: str, repository_seed: int, task_index: int) -> Task:
    if split not in SPLITS:
        raise ValueError(f"unknown split: {split}")
    family = FAMILIES[(repository_seed + task_index) % len(FAMILIES)]
    return BUILDERS[family](
        rng=random.Random(repository_seed * 10_000 + task_index),
        split=split, repository_seed=repository_seed,
        task_index=task_index, family=family,
    )


def _repo_hash(task: Task) -> str:
    return _sha256(_canonical(task.files | task.visible_tests))


def _hidden_hash(task: Task) -> str:
    return _sha256(task.hidden_tests.encode())


def _patch_hash(task: Task) -> str:
    return _sha256(_canonical(task.oracle_patch))


def _manifest_entry(task: Task, private_path: str) -> dict[str, Any]:
    return {
        "task_id": task.task_id, "split": task.split,
        "repository_id": task.repository_id,
        "repository_seed": task.repository_seed,
        "task_index": task.task_index, "family": task.family,
        "repository_sha256": _repo_hash(task),
        "hidden_bundle_sha256": _hidden_hash(task),
        "oracle_patch_sha256": _patch_hash(task),
        "private_path": private_path,
    }


def write_task(task: Task, output: Path) -> dict[str, Any]:
    task_dir = output / task.split / task.task_id
    if task_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing task: {task_dir}")
    repo = task_dir / "repo"
    for relative, content in task.files.items() | task.visible_tests.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    private = task_dir / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "hidden_tests.py").write_text(task.hidden_tests, encoding="utf-8", newline="\n")
    (private / "oracle_patch.json").write_text(
        json.dumps(task.oracle_patch, indent=2) + "\n", encoding="utf-8"
    )
    (private / "request.txt").write_text(task.request + "\n", encoding="utf-8")
    (private / "task.json").write_text(
        json.dumps(task.private_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return _manifest_entry(task, task_dir.relative_to(output).as_posix())


def generate_bundle(output: Path, *, splits: list[str] | None = None,
                    repositories: int | None = None,
                    tasks_per_repository: int = TASKS_PER_REPOSITORY) -> dict[str, Any]:
    selected = splits or list(SPLITS)
    for split in selected:
        if split not in SPLITS:
            raise ValueError(f"unknown split: {split}")
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for split in selected:
        configured_repositories, first_seed = SPLITS[split]
        count = configured_repositories if repositories is None else repositories
        for offset in range(count):
            seed = first_seed + offset
            for task_index in range(tasks_per_repository):
                entries.append(write_task(
                    make_task(split, seed, task_index), output
                ))
    manifest = {
        "schema": "raly-coder-manifest-v1",
        "generator_version": GENERATOR_VERSION,
        "tasks_per_repository": tasks_per_repository,
        "splits": {
            split: {
                "repositories": sum(x["split"] == split for x in entries) // tasks_per_repository,
                "tasks": sum(x["split"] == split for x in entries),
                "first_seed": SPLITS[split][1],
            } for split in selected
        },
        "tasks": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--splits", default="")
    parser.add_argument("--repositories", type=int)
    parser.add_argument("--tasks-per-repository", type=int, default=TASKS_PER_REPOSITORY)
    args = parser.parse_args()
    splits = [x for x in args.splits.split(",") if x] or None
    manifest = generate_bundle(
        args.output, splits=splits, repositories=args.repositories,
        tasks_per_repository=args.tasks_per_repository,
    )
    print(json.dumps({
        "generator_version": GENERATOR_VERSION,
        "tasks": len(manifest["tasks"]),
        "splits": manifest["splits"],
        "manifest": str(args.output / "manifest.json"),
    }, indent=2))


if __name__ == "__main__":
    main()
