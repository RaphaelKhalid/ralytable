"""Five-to-fifteen minute plumbing smoke test for experiment 11.

This is intentionally an exploratory pipeline check. It does not produce a
confirmatory model claim. The full preregistered run comes only after this
script verifies the executor, interventions, model loop, checkpointing, and
logging.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import time
from typing import Any

import torch

from dsl import OPS, Task, execute, hidden_tests, make_task, run_program


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "smoke"
OUT.mkdir(exist_ok=True)
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")


def check_interpreter(tasks: list[Task]) -> dict[str, Any]:
    rows = []
    for task in tasks:
        state, result = run_program(task)
        rows.append({"expected": task.expected, "result": result,
                     "errors": state.errors, "pass": hidden_tests(task, result)})
    if not all(x["pass"] and not x["errors"] for x in rows):
        raise RuntimeError("oracle program failed its deterministic hidden test")

    state, _ = run_program(tasks[0])
    relevant = __import__("dsl").corrupt_state(state, "relevant")
    irrelevant = __import__("dsl").corrupt_state(state, "irrelevant")
    erased = __import__("dsl").corrupt_state(state, "erase_types")
    _, relevant_result = execute("return s3", relevant)
    _, irrelevant_result = execute("return s3", irrelevant)
    _, erased_result = execute("return s3", erased)
    if relevant_result == irrelevant_result:
        raise RuntimeError("relevant and irrelevant interventions did not differ")
    if irrelevant_result != erased_result:
        raise RuntimeError("unexpected change in control intervention")
    expected = list(tasks[0].expected)
    return {"oracle_tasks": len(rows), "oracle_pass": len(rows),
            "relevant_changed": relevant_result != expected,
            "irrelevant_preserved": irrelevant_result == expected,
            "type_erased_preserved": erased_result == expected}


def examples(tasks: list[Task], mode: str) -> list[tuple[str, str]]:
    result = []
    for task in tasks:
        state = __import__("dsl").initial_state(task)
        history: list[str] = []
        for target in task.program:
            prompt = (
                "You are a typed program controller. Emit exactly one operation "
                "from the allowed DSL and nothing else.\n"
                f"Allowed operations: {', '.join(OPS)}\n"
                f"Request: {task.request}\n"
                f"Required result type: {task.result_type}\n"
                f"Current typed state: {__import__('dsl').serialize_state(state)}\n"
            )
            if mode == "transcript":
                prompt += "Previous operations:\n" + "\n".join(history) + "\n"
            prompt += "Next operation:"
            result.append((prompt, target))
            state, _ = execute(target, state)
            history.append(target)
    return result


def pad_batch(tokenizer, records: list[dict[str, list[int]]], device: torch.device):
    max_len = max(len(x["input_ids"]) for x in records)
    pad = tokenizer.pad_token_id
    ids, masks, labels = [], [], []
    for x in records:
        n = max_len - len(x["input_ids"])
        ids.append(x["input_ids"] + [pad] * n)
        masks.append(x["attention_mask"] + [0] * n)
        labels.append(x["labels"] + [-100] * n)
    return {"input_ids": torch.tensor(ids, device=device),
            "attention_mask": torch.tensor(masks, device=device),
            "labels": torch.tensor(labels, device=device)}


def load_model(model_id: str):
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.bfloat16, local_files_only=True,
        low_cpu_mem_usage=True,
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model = get_peft_model(model, LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
        task_type=TaskType.CAUSAL_LM,
    ))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.print_trainable_parameters()
    return model, tokenizer, device


def train_smoke(model, tokenizer, device, pairs: list[tuple[str, str]], updates: int,
                batch_size: int = 2, accum: int = 4) -> list[float]:
    records = []
    for prompt, target in pairs:
        p = tokenizer(prompt, add_special_tokens=True)["input_ids"]
        t = tokenizer(" " + target + tokenizer.eos_token, add_special_tokens=False)["input_ids"]
        records.append({"input_ids": p + t, "attention_mask": [1] * (len(p) + len(t)),
                        "labels": [-100] * len(p) + t})
    params = [p for p in model.parameters() if p.requires_grad]
    try:
        opt = torch.optim.AdamW(params, lr=2e-4, fused=True)
    except (TypeError, RuntimeError):
        opt = torch.optim.AdamW(params, lr=2e-4)
    losses = []
    model.train()
    rng = random.Random(11)
    for step in range(updates):
        total = 0.0
        for _ in range(accum):
            batch = [records[rng.randrange(len(records))] for _ in range(batch_size)]
            b = pad_batch(tokenizer, batch, device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16,
                                enabled=device.type == "cuda"):
                loss = model(**b).loss / accum
            loss.backward()
            total += float(loss.detach()) * accum
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        losses.append(total / accum)
        if step % 10 == 0 or step == updates - 1:
            log_metric({"phase": "train", "step": step + 1,
                        "loss": losses[-1], "gpu_gb": gpu_gb()})
    return losses


def first_line(text: str) -> str:
    text = text.strip().splitlines()[0] if text.strip() else ""
    return " ".join(text.split())


def valid_candidates(task: Task, state, *, enforce_result_type: bool = True) -> list[str]:
    """Return syntactically and currently type-valid actions.

    The model still chooses the action. The interpreter supplies the grammar
    boundary so malformed text cannot masquerade as a failed architecture.
    """
    import dsl

    candidates = ["input values -> s0"] if (
        "s0" not in state.slots and state.input_values
    ) else []
    for source, slot in sorted(state.slots.items()):
        if slot.type_name == "List[Int]":
            for target in ("s0", "s1", "s2", "s3"):
                candidates.extend([
                    f"filter_gt {source} {task.threshold} -> {target}",
                    f"sort_asc {source} -> {target}",
                    f"unique {source} -> {target}",
                    f"count {source} -> {target}",
                ])
        if not enforce_result_type or slot.type_name == task.result_type:
            candidates.append(f"return {source}")
    return list(dict.fromkeys(candidates))


@torch.no_grad()
def run_controller(model, tokenizer, device, task: Task, mode: str,
                   max_ops: int = 6, constrained: bool = True,
                   enforce_result_type: bool = True) -> dict[str, Any]:
    import dsl

    state = dsl.initial_state(task)
    history: list[str] = []
    generated: list[str] = []
    errors: list[str] = []
    for _ in range(max_ops):
        prompt = (
            "You are a typed program controller. Emit exactly one operation "
            "from the allowed DSL and nothing else.\n"
            f"Allowed operations: {', '.join(OPS)}\n"
            f"Request: {task.request}\n"
            f"Required result type: {task.result_type}\n"
            f"Current typed state: {dsl.serialize_state(state)}\n"
        )
        if mode == "transcript":
            prompt += "Previous operations:\n" + "\n".join(history) + "\n"
        prompt += "Next operation:"
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        generate_kwargs = {
            "max_new_tokens": 32,
            "do_sample": False,
            "pad_token_id": tokenizer.pad_token_id,
        }
        if constrained:
            candidates = valid_candidates(
                task, state, enforce_result_type=enforce_result_type
            )
            candidate_ids = [tokenizer(" " + c + tokenizer.eos_token,
                                       add_special_tokens=False)["input_ids"]
                             for c in candidates]
            prefix_len = inputs.input_ids.shape[1]

            def allowed_tokens(_batch_id, input_ids):
                # Transformers passes a single sequence here, not a batched tensor.
                generated = input_ids[prefix_len:].tolist()
                matching = [ids for ids in candidate_ids
                            if ids[:len(generated)] == generated]
                if not matching:
                    # This preserves an honest failure if tokenization escapes
                    # the candidate set instead of silently forcing a result.
                    return list(range(tokenizer.vocab_size))
                return sorted({ids[len(generated)] for ids in matching
                               if len(generated) < len(ids)})

            generate_kwargs["prefix_allowed_tokens_fn"] = allowed_tokens

        out = model.generate(**inputs, **generate_kwargs)
        line = first_line(tokenizer.decode(out[0][inputs.input_ids.shape[1]:],
                                            skip_special_tokens=True))
        generated.append(line)
        state, result = dsl.execute(line, state)
        if state.errors:
            errors.extend(state.errors)
            break
        history.append(line)
        if line.startswith("return "):
            return {"result": result, "generated": generated, "errors": errors,
                    "parse_rate": sum(x.split(" ")[0] in OPS for x in generated) /
                    max(len(generated), 1)}
    return {"result": None, "generated": generated, "errors": errors,
            "parse_rate": sum(x.split(" ")[0] in OPS for x in generated) /
            max(len(generated), 1)}


def gpu_gb() -> float:
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.max_memory_allocated() / 1024**3


_METRICS = OUT / "metrics.jsonl"


def log_metric(row: dict[str, Any]) -> None:
    row = {"time": time.time(), **row}
    with _METRICS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    try:
        import wandb
        if wandb.run is not None:
            wandb.log({k: v for k, v in row.items() if isinstance(v, (int, float))},
                      step=row.get("step"))
    except Exception:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL_ID)
    ap.add_argument("--updates", type=int, default=100)
    ap.add_argument("--tasks", type=int, default=32)
    ap.add_argument("--no-model", action="store_true",
                    help="run deterministic executor checks only")
    args = ap.parse_args()
    if _METRICS.exists():
        _METRICS.unlink()
    rng = random.Random(20260827)
    tasks = [make_task(rng) for _ in range(args.tasks)]
    summary = {"interpreter": check_interpreter(tasks[:16])}
    write_jsonl(OUT / "oracle.jsonl", [asdict(t) for t in tasks])
    print("oracle and intervention checks: PASS", flush=True)
    if args.no_model:
        print(json.dumps(summary, indent=2))
        return

    all_parse = []
    for mode in ("transcript", "mediated"):
        try:
            import wandb
            wb = wandb.init(project="ralytable", group="typed-state-smoke",
                            name=f"smoke-qwen-0.5b-{mode}", job_type="smoke",
                            reinit="finish_previous")
            print(f"wandb ({mode}): {wb.url}", flush=True)
        except Exception as exc:
            print(f"wandb unavailable for {mode}, local metrics only: "
                  f"{type(exc).__name__}", flush=True)

        # Fresh base + adapter per arm. Reusing the trained adapter would make
        # the second arm inherit the first arm's training.
        model, tokenizer, device = load_model(args.model)
        pairs = examples(tasks[:26], mode)
        losses = train_smoke(model, tokenizer, device, pairs, args.updates)

        # Round-trip the trainable adapter only. Saving the frozen base would
        # make this check needlessly large and is not what the full run needs.
        adapter = {k: v.detach().cpu() for k, v in model.state_dict().items()
                   if "lora_" in k}
        ckpt = OUT / f"{mode}_adapter.pt"
        torch.save({"mode": mode, "state": adapter}, ckpt)
        restored = torch.load(ckpt, map_location="cpu", weights_only=True)["state"]
        missing, unexpected = model.load_state_dict(restored, strict=False)
        roundtrip = (not unexpected and
                     all(torch.equal(restored[k], model.state_dict()[k].detach().cpu())
                         for k in restored))
        eval_rows = [run_controller(model, tokenizer, device, t, mode)
                     for t in tasks[:16]]
        write_jsonl(OUT / f"{mode}_eval.jsonl", eval_rows)
        all_parse.extend(eval_rows)
        summary[mode] = {
            "initial_loss": losses[0], "final_loss": losses[-1],
            "loss_fell": losses[-1] < losses[0],
            "parse_rate": sum(x["parse_rate"] for x in eval_rows) / len(eval_rows),
            "model_hidden_test_pass": sum(hidden_tests(t, x["result"])
                                           for t, x in zip(tasks[:16], eval_rows)),
            "errors": sum(bool(x["errors"]) for x in eval_rows),
            "checkpoint_roundtrip": roundtrip,
        }
        print(f"{mode}: loss {losses[0]:.3f} -> {losses[-1]:.3f}, "
              f"parse {summary[mode]['parse_rate']:.1%}", flush=True)
        try:
            import wandb
            if wandb.run is not None:
                wandb.log({"smoke_complete": 1,
                           "eval_parse_rate": summary[mode]["parse_rate"],
                           "eval_hidden_pass": summary[mode]["model_hidden_test_pass"],
                           "peak_gpu_gb": gpu_gb(), "step": args.updates})
                wandb.finish()
        except Exception:
            pass
        del model, tokenizer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    summary["model"] = {"peak_gpu_gb": gpu_gb(),
                        "checkpoint_roundtrip": all(summary[m]["checkpoint_roundtrip"]
                                                     for m in ("transcript", "mediated")),
                        "all_model_ops_parse": all(x["parse_rate"] > 0 for x in all_parse)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
