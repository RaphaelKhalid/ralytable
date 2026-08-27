# Experiment 17 local handoff

Run date: 2026-08-27. This worktree contains the trust kernel, append-only
ledger, MAP-Elites smoke runner, and a nine-parameter trainable candidate.

## Primary WSL training environment

The approved read-only GPU check succeeded before installation:

```text
NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB total, 1996 MiB used, 5961 MiB free, 1% utilization
```

WSL exposes Python 3.14.4. The isolated EvalPlus environment at
`/home/rapha/.venvs/ralytable-evalplus-0.3.1` reports EvalPlus 0.3.1 and was
not modified. The separate training environment is intended at
`/home/rapha/ralytable-autoresearch-next/.venv`.

Exact attempted install command:

```text
python3 -m venv /home/rapha/ralytable-autoresearch-next/.venv
/home/rapha/ralytable-autoresearch-next/.venv/bin/python -m pip install --upgrade pip
/home/rapha/ralytable-autoresearch-next/.venv/bin/python -m pip install --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple torch==2.13.0+cu130
```

Requested primary package: `torch==2.13.0+cu130` (official PyTorch CUDA 13.0
index), with Python 3.14-compatible wheel metadata. The wheel and CUDA
dependencies downloaded, but pip failed during final installation with
`OSError: [Errno 5] Input/output error`. WSL then failed to launch even a
read-only command with `getpwuid(1000) failed 5` / `CreateInstance/E_FAIL`.
After the controlled restart, filesystem recovery reported orphan inodes had
been cleaned and the partial environment was quarantined as
`.venv.partial-eio-20260827` (retained). A clean retry with the same package,
and scoped `PIP_CACHE_DIR`/`TMPDIR` under the experiment directory, failed a
second time with the same `Errno 5` during final installation. Stop WSL writes
at this point; do not churn the VHD or try another wheel in this task. After a
separate host-level diagnosis, verify:

```text
/home/rapha/ralytable-autoresearch-next/.venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())'
```

Then run a one-step CUDA allocation/training check, record peak allocated VRAM,
and reuse this venv for `python -m tools.autoresearch_next run --environment
wsl`. The dependency-free candidate path is emergency/test-only and must not be
presented as the primary tournament route.

## Safety and recovery

All artifacts and hidden proxy scores are outside Git. The GPU owner lock
serializes candidate training and never kills another process. Candidate
contracts reject protected paths, answer/oracle material, hidden tests, and
more than 9M learned parameters. Interrupted, timeout, OOM, and contract
failures are appended to the ledger and the next candidate can resume.
