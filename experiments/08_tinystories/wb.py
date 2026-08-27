"""Optional Weights & Biases mirror. Off by default; never load-bearing.

The local dashboard (dashboard.py) is the default and requires no account. This
is an ADDITIVE layer behind `--wandb`, for when the numbers should also live
somewhere shareable.

AUTH. We never prompt, never take a key on the command line, and never print
one. `wandb.login(anonymous="never", timeout=...)` picks up ~/.netrc (written
by `wandb login`) or WANDB_API_KEY from the environment. If neither exists,
this class prints a single line and every subsequent method is a no-op.

FAILURE POLICY. Every call is inside try/except. A dropped network connection
mid-run degrades to local-only, silently after the first warning. Nothing in
here is allowed to raise into the training loop -- a 4-hour run must not die
because a logging service had a bad minute.
"""
import os


class WandB:
    def __init__(self, enabled=False):
        self.on = False
        self.run = None
        self._warned = False
        if not enabled:
            return
        try:
            import wandb
            self.wandb = wandb
        except Exception as e:
            print(f"  (wandb not importable: {type(e).__name__}; local dashboard only)")
            return
        try:
            has_env = bool(os.environ.get("WANDB_API_KEY"))
            ok = self.wandb.login(anonymous="never", timeout=20)
            if not (ok or has_env):
                raise RuntimeError("no credentials")
            self.on = True
            print("  wandb: authenticated, mirroring to project 'ralytable'")
        except Exception as e:
            print(f"  (wandb unavailable -- run `wandb login` or set WANDB_API_KEY "
                  f"[{type(e).__name__}]; continuing local-only)")

    def _safe(self, fn):
        if not self.on:
            return None
        try:
            return fn()
        except Exception as e:
            if not self._warned:
                self._warned = True
                print(f"\n  (wandb call failed: {type(e).__name__}; "
                      f"continuing local-only)", flush=True)
            return None

    def start(self, name, group, config):
        """One wandb run per (config, seed); `group` is the config so seeds aggregate."""
        self._safe(lambda: setattr(self, "run", self.wandb.init(
            project="ralytable", name=name, group=group, config=config,
            reinit=True, job_type="tinystories")))

    def url(self):
        try:
            return self.run.url if self.run is not None else None
        except Exception:
            return None

    def log(self, d, step=None):
        self._safe(lambda: self.wandb.log(d, step=step))

    def finish(self):
        """Per-run finish, so three seeds are three runs and not one merged mess."""
        self._safe(lambda: self.wandb.finish())
        self.run = None
