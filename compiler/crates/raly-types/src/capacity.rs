//! How many items a space can hold, from measurement rather than from theory.
//!
//! # Where the numbers come from
//!
//! `docs/semantics/vsa-and-discrete-ops.md` §3 gives the *scaling*,
//! `M* = Θ(D / ln N)`, and is explicit that the constant varies by ±2× across
//! the literature. A constant that vague is useless to a type system, so
//! `experiments/04_capacity` measured it: a random bipolar codebook of 1000
//! atoms, bundle `N` distinct atoms, and ask whether all `N` come back as the
//! top-`N` nearest neighbours of the bundle.
//!
//! The largest `N` still retrieved at 95% is:
//!
//! | D    | 256 | 512 | 1000 | 2048 |
//! |------|-----|-----|------|------|
//! | M*   | 7   | 14  | 31   | 71   |
//!
//! These four points are [`ANCHORS`], and the checker reproduces them exactly.
//!
//! # The interpolation, and why this one
//!
//! Between anchors, capacity is interpolated **linearly in log–log space**:
//!
//! ```text
//! ln M*(D) = ln M0 + b · (ln D − ln D0),    b = ln(M1/M0) / ln(D1/D0)
//! ```
//!
//! then floored. Outside the measured range the nearest segment's exponent is
//! extrapolated.
//!
//! Three reasons for this rather than a fitted formula:
//!
//! 1. **It is exact at the measurements.** A global power-law fit
//!    (`M* ≈ 0.0145 · D^1.114`, which fits these four points to within 8%)
//!    would make the checker disagree with the experiment at D=512, and the
//!    experiment is the authority.
//! 2. **The measured points really are close to a power law**, so interpolating
//!    in log–log space is interpolating along the shape the data has, not
//!    along a straight line the data does not follow.
//! 3. **It is monotone and total**, which a type system needs: every dimension
//!    gets an answer, and a wider space never holds less.
//!
//! # Effective dimension
//!
//! `experiments/05_real_embeddings` found that real embedding spaces have an
//! effective dimension far below their nominal one — 110.6 of 384 for MiniLM.
//! A bound derived from ambient `D` therefore overstates capacity by 3–5×. A
//! space may declare what was measured:
//!
//! ```raly
//! space Sentences = MAP[384] where effective = 111
//! ```
//!
//! and the checker uses that instead. See [`crate::SpaceInfo::capacity_basis`].
//!
//! # What this is not
//!
//! It is one codebook size (1000 atoms), one family (MAP/bipolar), one
//! threshold (95%), flat bundles only. `M*` also falls as the cleanup pool
//! grows. The number is a *floor on honesty*, not a guarantee.

/// Measured `(dimension, largest bundle still retrieved at 95%)`.
///
/// Sorted by dimension. From `experiments/04_capacity/FINDINGS.md`.
pub const ANCHORS: &[(u64, u32)] = &[(256, 7), (512, 14), (1000, 31), (2048, 71)];

/// The largest number of items a space of this dimension holds.
///
/// Exact at every point of [`ANCHORS`]; log–log interpolated between them and
/// extrapolated beyond them. Always at least 1.
pub fn capacity(dimension: u64) -> u32 {
    if dimension == 0 {
        return 1;
    }
    if let Some(&(_, m)) = ANCHORS.iter().find(|&&(d, _)| d == dimension) {
        return m;
    }

    let last = ANCHORS.len() - 1;
    let segment = if dimension < ANCHORS[0].0 {
        0
    } else if dimension > ANCHORS[last].0 {
        last - 1
    } else {
        ANCHORS
            .windows(2)
            .position(|w| dimension > w[0].0 && dimension < w[1].0)
            .unwrap_or(last - 1)
    };

    let (d0, m0) = ANCHORS[segment];
    let (d1, m1) = ANCHORS[segment + 1];
    let exponent = ((m1 as f64) / (m0 as f64)).ln() / ((d1 as f64) / (d0 as f64)).ln();
    let value = (m0 as f64) * ((dimension as f64) / (d0 as f64)).powf(exponent);
    if !value.is_finite() {
        return u32::MAX;
    }
    (value.floor().max(1.0)).min(u32::MAX as f64) as u32
}

/// The smallest dimension whose [`capacity`] reaches `items`.
///
/// Used by the capacity diagnostic's `help:` line, so that "declare a wider
/// space" comes with the actual number rather than the advice to guess. Found
/// by bisection over [`capacity`] itself, so the two can never disagree.
pub fn dimension_for(items: u32) -> u64 {
    if items <= capacity(1) {
        return 1;
    }
    let mut low: u64 = 1;
    let mut high: u64 = 1 << 20;
    while capacity(high) < items && high < (1 << 40) {
        high = high.saturating_mul(2);
    }
    while low < high {
        let mid = low + (high - low) / 2;
        if capacity(mid) >= items {
            high = mid;
        } else {
            low = mid + 1;
        }
    }
    low
}

/// The next power of two at or above `dimension`.
///
/// VSA dimensions are conventionally powers of two, so the help text offers
/// one alongside the exact minimum.
pub fn round_up_pow2(dimension: u64) -> u64 {
    let mut d: u64 = 1;
    while d < dimension {
        d = d.saturating_mul(2);
    }
    d
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn anchors_are_reproduced_exactly() {
        for &(d, m) in ANCHORS {
            assert_eq!(capacity(d), m, "capacity({d})");
        }
    }

    #[test]
    fn capacity_is_monotone() {
        let mut previous = 0;
        for d in (16u64..=8192).step_by(7) {
            let c = capacity(d);
            assert!(c >= previous, "capacity fell at D={d}: {previous} -> {c}");
            previous = c;
        }
    }

    #[test]
    fn interpolates_between_anchors() {
        // Halfway between 512 and 1000 should sit between their capacities.
        let c = capacity(756);
        assert!(c > 14 && c < 31, "capacity(756) = {c}");
    }

    #[test]
    fn extrapolates_outside_the_measured_range() {
        assert!(capacity(128) < 7);
        assert!(capacity(8192) > 71);
        assert_eq!(capacity(0), 1);
    }

    #[test]
    fn dimension_for_inverts_capacity() {
        for items in [2u32, 7, 14, 31, 40, 71, 200] {
            let d = dimension_for(items);
            assert!(capacity(d) >= items, "capacity({d}) < {items}");
            assert!(d == 1 || capacity(d - 1) < items, "{d} is not minimal");
        }
    }

    #[test]
    fn powers_of_two() {
        assert_eq!(round_up_pow2(1), 1);
        assert_eq!(round_up_pow2(1000), 1024);
        assert_eq!(round_up_pow2(1024), 1024);
    }
}
