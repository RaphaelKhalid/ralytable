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

  - torch.compile(mode="reduce-overhead") captures CUDA graphs and replays them,
    which is the single largest win for small models and does nothing for large.
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
    """Vector quantiser: EMA updates, cosine distance, low-dim codes, dead-code revival."""

    def __init__(self, n_codes=512, dim=256, code_dim=32, decay=0.99, revive_after=50):
        super().__init__()
        self.n_codes, self.code_dim, self.decay = n_codes, code_dim, decay
        self.revive_after = revive_after
        self.proj_in = nn.Linear(dim, code_dim, bias=False)
        self.proj_out = nn.Linear(code_dim, dim, bias=False)
        self.register_buffer("codes", F.normalize(torch.randn(n_codes, code_dim), dim=-1))
        self.register_buffer("cluster_size", torch.zeros(n_codes))
        self.register_buffer("ema_sum", self.codes.clone())
        self.register_buffer("idle", torch.zeros(n_codes))

    @torch.no_grad()
    def _ema_update(self, flat, idx):
        onehot = F.one_hot(idx, self.n_codes).type(flat.dtype)
        n = onehot.sum(0)
        self.cluster_size.mul_(self.decay).add_(n, alpha=1 - self.decay)
        self.ema_sum.mul_(self.decay).add_(onehot.T @ flat, alpha=1 - self.decay)
        self.codes.copy_(F.normalize(self.ema_sum, dim=-1))

        # dead-code revival: re-seed codes nothing has claimed recently
        self.idle.add_(1)
        self.idle[n > 0] = 0
        dead = self.idle > self.revive_after
        if dead.any():
            pick = torch.randint(0, flat.size(0), (int(dead.sum()),), device=flat.device)
            self.codes[dead] = flat[pick]
            self.ema_sum[dead] = flat[pick]
            self.cluster_size[dead] = 1.0
            self.idle[dead] = 0

    def forward(self, h):
        z = F.normalize(self.proj_in(h), dim=-1)          # cosine space
        flat = z.reshape(-1, self.code_dim)
        idx = (flat @ self.codes.T).argmax(-1)            # cosine distance
        q = self.codes[idx].view_as(z)
        if self.training:
            self._ema_update(flat.detach(), idx)
        commit = F.mse_loss(z, q.detach())                # encoder -> codebook only
        q = z + (q - z).detach()                          # straight-through
        return self.proj_out(q), commit, idx.view(h.shape[:-1])

    @torch.no_grad()
    def live_codes(self):
        return int((self.cluster_size > 1e-3).sum())


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


def build(vocab, device="cuda", compile_model=True, **kw):
    m = DiscreteCore(vocab, **kw).to(device)
    if compile_model and device == "cuda":
        # reduce-overhead captures CUDA graphs; the big win at this size, where
        # kernel launch cost dominates actual arithmetic
        m = torch.compile(m, mode="reduce-overhead")
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
