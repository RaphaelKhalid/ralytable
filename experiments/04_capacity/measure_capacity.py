"""Measure VSA bundling capacity empirically instead of citing it.

The semantics doc quotes M* = Theta(D / ln N) and, for D=1000, "about 10 items".
The constant matters more than the form here, because the capacity TYPE in Raly
has to carry a concrete number. So measure it.

Protocol: build a random bipolar codebook, bundle N distinct atoms, then check
whether all N are recoverable as the top-N nearest neighbours of the bundle.
"""
import numpy as np

rng = np.random.default_rng(0)


def retrieval(D, N, vocab=1000, trials=60):
    ok = tot = 0
    for _ in range(trials):
        cb = rng.choice([-1.0, 1.0], size=(vocab, D))
        idx = rng.choice(vocab, N, replace=False)
        bundled = np.sign(cb[idx].sum(0) + 1e-9 * rng.normal(size=D))
        top = np.argsort(-(cb @ bundled))[:N]
        ok += len(set(top) & set(idx))
        tot += N
    return ok / tot


def capacity(D, vocab, thresh=0.95, hi=200):
    """Largest N with retrieval >= thresh. Returns (N, censored)."""
    best = 0
    for n in range(2, hi):
        if retrieval(D, n, vocab, trials=40) >= thresh:
            best = n
        else:
            return best, False
    return best, True


if __name__ == "__main__":
    print("retrieval accuracy, MAP/bipolar, vocab=1000\n")
    Ns = [3, 5, 8, 10, 15, 20, 30, 50]
    print(f"{'D':>6} " + " ".join(f"N={n:<5}" for n in Ns))
    for D in [256, 512, 1000, 2048, 4096]:
        print(f"{D:>6} " + " ".join(f"{retrieval(D, n):<7.2f}" for n in Ns))

    print("\ncapacity M* at 95% retrieval, and codebook-size dependence:")
    print(f"{'D':>6} {'vocab=1k':>12} {'vocab=10k':>12}   D/ln(D)")
    for D in [256, 512, 1000, 2048]:
        a, ca = capacity(D, 1000)
        b, cb_ = capacity(D, 10000)
        f = lambda v, c: f"{v}{'+' if c else ''}"
        print(f"{D:>6} {f(a,ca):>12} {f(b,cb_):>12}   {D/np.log(D):8.1f}")
