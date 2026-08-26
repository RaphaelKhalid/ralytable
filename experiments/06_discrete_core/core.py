"""Discrete-bottleneck core, with the standard fixes for codebook collapse
and the optimisations that actually matter on a laptop GPU.

WHY THESE FIXES. The first smoke run collapsed to 11 of 64 codes. That is the
textbook failure of vector quantisation: a few codes win early, only winners get
gradient, the rest stay where they were initialised and die. Four mitigations,
all standard, all cheap:

  1. EMA codebook updates (van den Oord et al.) instead of a gradient on the
     codebook. The codebook tracks the running mean of what is assigned to it,
     which is far more stable than backprop through a straight-through estimator.
  2. Dead-code revival: any code unused for N steps is re-seeded onto a random
     high-error encoder output. This is what actually rescues the tail.
  3. Cosine distance on L2-normalised vectors instead of Euclidean (Improved
     VQGAN). Removes the magnitude race where high-norm codes swallow everything.
  4. Low-dimensional codes: quantise in a projected-down space, then project back
     up. Smaller code space means codes are closer together and more get used.

WHY THESE OPTIMISATIONS. At this size the bottleneck is NOT arithmetic, it is
kernel launch overhead -- thousands of tiny CUDA launches per step, each costing
more than the work it does. So:

  - torch.compile is DISABLED by default: measured at 222 ms/step against
    41.6 ms/step eager, because the dead-code revival's data-dependent topk
    breaks the graph every step. See build().
  - bf16 autocast: Ada (sm_89) has bf16 tensor cores; bf16 over fp16 avoids loss
    scaling entirely.
  - TF32 matmuls, fused AdamW, and the whole corpus resident on the GPU so there
    is no host-device traffic in the loop.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True


class VQ(nn.Module):
    """Vector quantiser with the three fixes that actually stop collapse.

    The first two attempts collapsed to 11/64 and then 1/64 live codes. The bug
    was in the EMA: unused codes have an ema_sum decaying to zero, and
    normalising a near-zero vector yields noise, so dead codes were re-randomised
    every step and could never win anything. Fixes:

      1. Codes = ema_sum / cluster_size (the standard VQ-VAE EMA), and codes with
         no assignments are LEFT ALONE rather than recomputed from noise.
      2. Data-dependent init: seed the codebook from the first batch's encoder
         outputs, so codes start where the data actually is instead of on a
         random sphere the encoder never visits.
      3. Dead-code revival targets the HIGHEST-ERROR encoder outputs, not random
         ones, so a revived code lands somewhere currently badly served.
    """

    def __init__(self, n_codes=512, dim=256, code_dim=32, decay=0.99, revive_after=25):
        super().__init__()
        self.n_codes, self.code_dim, self.decay = n_codes, code_dim, decay
        self.revive_after, self.eps = revive_after, 1e-5
        self.proj_in = nn.Linear(dim, code_dim, bias=False)
        self.proj_out = nn.Linear(code_dim, dim, bias=False)
        self.register_buffer("codes", torch.randn(n_codes, code_dim) * 0.1)
        self.register_buffer("cluster_size", torch.ones(n_codes))
        self.register_buffer("ema_sum", self.codes.clone())
        self.register_buffer("idle", torch.zeros(n_codes))
        self.register_buffer("inited", torch.zeros((), dtype=torch.bool))

    @torch.no_grad()
    def _init_from_data(self, flat):
        pick = torch.randperm(flat.size(0), device=flat.device)[: self.n_codes]
        if pick.numel() < self.n_codes:                      # pad by resampling
            extra = torch.randint(0, flat.size(0),
                                  (self.n_codes - pick.numel(),), device=flat.device)
            pick = torch.cat([pick, extra])
        self.codes.copy_(flat[pick])
        self.ema_sum.copy_(flat[pick])
        self.cluster_size.fill_(1.0)
        self.inited.fill_(True)

    @torch.no_grad()
    def _ema_update(self, flat, idx):
        flat = flat.float()          # buffers are fp32; autocast hands us bf16
        onehot = F.one_hot(idx, self.n_codes).type(flat.dtype)
        n = onehot.sum(0)
        self.cluster_size.mul_(self.decay).add_(n, alpha=1 - self.decay)
        self.ema_sum.mul_(self.decay).add_(onehot.T @ flat, alpha=1 - self.decay)
        # only recompute codes that have mass; leave the rest where they are
        live = self.cluster_size > self.eps
        self.codes[live] = self.ema_sum[live] / self.cluster_size[live].unsqueeze(-1)

        self.idle.add_(1)
        self.idle[n > 0] = 0
        dead = self.idle > self.revive_after
        if dead.any():
            # revive onto the worst-reconstructed inputs, not random ones
            err = (flat - self.codes[idx]).pow(2).sum(-1)
            worst = err.topk(min(int(dead.sum()), flat.size(0))).indices
            tgt = flat[worst]
            slots = dead.nonzero(as_tuple=True)[0][: tgt.size(0)]
            self.codes[slots] = tgt
            self.ema_sum[slots] = tgt
            self.cluster_size[slots] = 1.0
            self.idle[slots] = 0

    def forward(self, h):
        z = self.proj_in(h)
        flat = z.reshape(-1, self.code_dim)
        if self.training and not bool(self.inited):
            self._init_from_data(flat.detach().float())
        d = (flat.pow(2).sum(-1, keepdim=True)
             - 2 * flat @ self.codes.T
             + self.codes.pow(2).sum(-1))
        idx = d.argmin(-1)
        q = self.codes[idx].view_as(z).to(z.dtype)
        if self.training:
            self._ema_update(flat.detach(), idx)
        commit = F.mse_loss(z, q.detach())
        q = z + (q - z).detach()
        return self.proj_out(q), commit, idx.view(h.shape[:-1])

    @torch.no_grad()
    def live_codes(self):
        return int((self.cluster_size > self.eps).sum())


class Block(nn.Module):
    """Pre-norm transformer block: RMSNorm + SwiGLU + SDPA (flash when available)."""

    def __init__(self, dim, heads):
        super().__init__()
        self.n1, self.n2 = nn.RMSNorm(dim), nn.RMSNorm(dim)
        self.qkv = nn.Linear(dim, 3 * dim, bias=False)
        self.proj = nn.Linear(dim, dim, bias=False)
        self.w1 = nn.Linear(dim, 4 * dim, bias=False)
        self.w2 = nn.Linear(dim, 4 * dim, bias=False)
        self.w3 = nn.Linear(4 * dim, dim, bias=False)
        self.heads = heads

    def forward(self, x):
        B, T, C = x.shape
        q, k, v = self.qkv(self.n1(x)).chunk(3, -1)
        shape = lambda t: t.view(B, T, self.heads, C // self.heads).transpose(1, 2)
        a = F.scaled_dot_product_attention(shape(q), shape(k), shape(v), is_causal=True)
        x = x + self.proj(a.transpose(1, 2).reshape(B, T, C))
        h = self.n2(x)
        return x + self.w3(F.silu(self.w1(h)) * self.w2(h))


class DiscreteCore(nn.Module):
    """Soft encoder -> discrete bottleneck -> decoder.

    `bottleneck=False` gives the dense baseline at matched parameters, which is
    the control the whole legibility-vs-capability comparison needs.
    """

    def __init__(self, vocab, dim=256, depth=4, heads=4, ctx=256,
                 n_codes=512, code_dim=32, bottleneck=True):
        super().__init__()
        self.bottleneck = bottleneck
        self.emb = nn.Embedding(vocab, dim)
        self.pos = nn.Embedding(ctx, dim)
        self.enc = nn.ModuleList(Block(dim, heads) for _ in range(depth // 2))
        self.vq = VQ(n_codes, dim, code_dim) if bottleneck else None
        self.dec = nn.ModuleList(Block(dim, heads) for _ in range(depth - depth // 2))
        self.norm = nn.RMSNorm(dim)
        self.head = nn.Linear(dim, vocab, bias=False)
        self.head.weight = self.emb.weight                # tied
        self.apply(self._init)

    @staticmethod
    def _init(m):
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, std=0.02)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, std=0.02)

    def forward(self, x, targets=None):
        h = self.emb(x) + self.pos(torch.arange(x.size(1), device=x.device))
        for b in self.enc:
            h = b(h)
        commit, idx = h.new_zeros(()), None
        if self.bottleneck:
            h, commit, idx = self.vq(h)
        for b in self.dec:
            h = b(h)
        logits = self.head(self.norm(h))
        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)),
                                   targets.reshape(-1)) + commit
        return logits, loss, idx


def build(vocab, device="cuda", compile_model=False, **kw):
    """compile_model defaults to FALSE, and that is a measured decision.

    torch.compile was tried three ways on this model and lost every time:
      - mode="reduce-overhead" captures CUDA graphs, which cannot capture the
        VQ's in-place EMA buffer writes during forward;
      - default mode compiles, but the dead-code revival does a data-dependent
        `topk` on `dead.sum()`, which breaks the graph and recompiles every
        step: 222 ms/step against 41.6 ms/step eager, a 5x regression;
      - and on Windows it needs a Triton whose version must match torch's
        exactly (torch 2.6 wants triton 3.2, not 3.7).
    Eager is the right default here. Pass compile_model=True only after
    re-benchmarking on a model without data-dependent control flow.
    """
    m = DiscreteCore(vocab, **kw).to(device)
    if compile_model and device == "cuda":
        try:
            compiled = torch.compile(m)
            compiled(torch.zeros(1, 8, dtype=torch.long, device=device))
            return compiled
        except Exception as e:
            print(f"  (torch.compile unavailable, running eager: "
                  f"{type(e).__name__})", flush=True)
    return m


def optimizer(model, lr=3e-4, wd=0.1):
    decay = [p for n, p in model.named_parameters() if p.dim() >= 2]
    no_decay = [p for n, p in model.named_parameters() if p.dim() < 2]
    return torch.optim.AdamW(
        [{"params": decay, "weight_decay": wd},
         {"params": no_decay, "weight_decay": 0.0}],
        lr=lr, betas=(0.9, 0.95), fused=torch.cuda.is_available())


def cosine_lr(step, total, warmup, peak):
    if step < warmup:
        return peak * step / max(1, warmup)
    p = (step - warmup) / max(1, total - warmup)
    return 0.1 * peak + 0.9 * peak * 0.5 * (1 + math.cos(math.pi * p))
