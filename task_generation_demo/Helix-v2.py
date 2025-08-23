import pandas as pd
import math
import numpy as np
import json
import os
import sys
import io
from datetime import datetime

rng = np.random.default_rng()

# ---------------------------- IO & ANALYSIS ---------------------------- #

def get_user_input(prompt, type, min_val=None, max_val=None, choices=None):
    while True:
        try:
            raw = input(prompt)
            if choices:
                val = raw.strip().lower()
                if val in choices:
                    return val
                print(f"Please enter one of: {', '.join(choices)}")
                continue
            if type == str:
                if not raw.strip():
                    print("Value cannot be empty.")
                    continue
                return raw
            val = type(raw)
            if min_val is not None and val < min_val:
                print(f"Enter a value ≥ {min_val}."); continue
            if max_val is not None and val > max_val:
                print(f"Enter a value ≤ {max_val}."); continue
            return val
        except ValueError:
            print("Invalid input. Try again.")

def analyze_design(design_df, category_info):
    """
    category_info:
      - grid mode: {'All': [E_1,...,E_E]}
      - layout mode: {'A': [...], 'B': [...], ...}
    """
    out = io.StringIO(); orig = sys.stdout; sys.stdout = out
    work = design_df.drop(columns=['Consumer ID'])

    print("--- Design Analysis Report ---")

    # Category Balance (for grid, this is a single 'All' bucket)
    print("\n## 1. Category Balance: Appearance of Each Category")
    cat_counts = {c: work[cols].sum().sum() for c, cols in category_info.items()}
    s = pd.Series(cat_counts)
    print("  - Total appearances for each category:"); print(s)
    print(f"  - Average: {s.mean():.2f} | Std: {s.std():.2f}")

    # Element counts
    print("\n## 2. Main Effect Balance: Appearance of Each Element")
    el_counts = work.sum(axis=0)
    print("  - Total appearances for each element:"); print(el_counts)
    print(f"  - Average: {el_counts.mean():.2f} | Std: {el_counts.std():.2f}")

    # Row density
    print("\n## 3. Overall Design Metrics")
    row_sums = work.sum(axis=1)
    print(f"  - Active elements per vignette: min={row_sums.min()} max={row_sums.max()}")

    sys.stdout = orig
    return out.getvalue()

# ---------------------------- HELPERS ---------------------------- #

def compute_k_schedule(total_tasks, E, minK, maxK):
    """Build a K schedule in [minK, maxK] (capped at 4) with sum(K) % E == 0."""
    maxK = min(maxK, 4)
    if minK > maxK:
        raise ValueError("min_active_elements cannot exceed max_active_elements (cap=4).")
    if E < maxK:
        raise ValueError("Number of elements must be ≥ max active elements.")

    Ks = np.full(total_tasks, minK, dtype=int)
    sum_min = int(total_tasks * minK)
    needed = (-sum_min) % E
    headroom = (maxK - minK) * total_tasks
    if needed > headroom:
        raise ValueError(
            f"Infeasible K schedule: need +{needed} activations but capacity is {headroom}. "
            "Widen the min/max band or change counts."
        )
    if needed:
        q, r = divmod(needed, total_tasks)
        if q > (maxK - minK):
            raise ValueError("Per-row headroom too small to distribute needed increments.")
        Ks += q
        if r > 0:
            idx = rng.choice(total_tasks, size=r, replace=False)
            Ks[idx] += 1
    rng.shuffle(Ks)
    return Ks

def compute_k_schedule_grid(num_consumers, tasks_per_consumer, E, minK, maxK):
    """
    Build a per-respondent K schedule (cap 4) that:
      • respects K in [minK, maxK],
      • ensures enough unique K-combos per respondent,
      • and makes sum(K) % E == 0 so exact equal exposure is achievable.
    """
    if maxK > 4:
        raise ValueError("maxK cannot exceed 4.")
    if minK > maxK:
        raise ValueError("minK cannot exceed maxK.")
    if E < maxK:
        raise ValueError("Number of elements must be ≥ max active elements.")

    N = int(num_consumers)
    T = int(tasks_per_consumer)
    Δ = maxK - minK

    # Uniqueness capacity across the K-band
    band_capacity = sum(math.comb(E, k) for k in range(minK, maxK + 1))
    if T > band_capacity:
        raise RuntimeError(
            f"Per-respondent uniqueness impossible: T={T} but capacity with E={E}, "
            f"K∈[{minK},{maxK}] is {band_capacity}."
        )

    # Constant-K case
    if Δ == 0:
        cap_const = math.comb(E, minK)
        if T > cap_const:
            raise RuntimeError(
                f"Per-respondent uniqueness impossible for constant K={minK}: "
                f"T={T} > C({E},{minK})={cap_const}."
            )
        if (minK * N * T) % E != 0:
            raise RuntimeError(
                f"Exact equal exposure impossible with constant K={minK}: "
                f"{minK}*{N}*{T} mod {E} ≠ 0. Allow a K-range or change counts."
            )
        return np.full(N * T, minK, dtype=int)

    # With a band (e.g., 3–4): force enough maxK to avoid low-K duplication
    low_capacity = sum(math.comb(E, k) for k in range(minK, maxK))
    hi_min_per_person = max(0, T - low_capacity)
    hi_cap_per_person = min(T, math.comb(E, maxK))

    base_sum = minK * N * T
    need = (-base_sum) % E
    g = math.gcd(Δ, E)
    if need % g != 0:
        raise RuntimeError(
            f"Cannot meet divisibility: gcd(Δ={Δ}, E={E})={g} does not divide {need}."
        )
    step = E // g

    # Find smallest t with (Δ * t) % E == need
    t0 = None
    for t in range(step):
        if (Δ * t) % E == need:
            t0 = t
            break
    if t0 is None:  # should not happen if the gcd check passed
        t0 = 0

    x_min = N * hi_min_per_person
    x_max = N * hi_cap_per_person
    # Smallest x ≥ x_min with x ≡ t0 (mod step)
    x = t0 if x_min <= t0 else t0 + ((x_min - t0 + step - 1) // step) * step
    if x > x_max:
        raise RuntimeError(
            f"Cannot satisfy both uniqueness and divisibility: need total {x} maxK vignettes, cap is {x_max}."
        )

    # Distribute #maxK per person (round-robin up to cap)
    hi = np.full(N, hi_min_per_person, dtype=int)
    extra = int(x - x_min)
    i = 0
    while extra > 0:
        if hi[i] < hi_cap_per_person:
            hi[i] += 1
            extra -= 1
        i = (i + 1) % N

    # Assemble Ks (shuffle within each respondent)
    Ks = np.empty(N * T, dtype=int)
    pos = 0
    for i in range(N):
        k_list = [maxK] * int(hi[i]) + [minK] * int(T - hi[i])
        rng.shuffle(k_list)
        Ks[pos:pos+T] = k_list
        pos += T

    assert (Ks.sum() % E) == 0
    return Ks


def vignette_signature_pairs(cat_elem_pairs):
    """Canonical signature for per-respondent uniqueness (layout mode)."""
    return tuple(sorted(cat_elem_pairs, key=lambda x: x[0]))

def vignette_signature_elements(elem_list):
    """Canonical signature for per-respondent uniqueness (grid mode)."""
    return tuple(sorted(elem_list))

# ---------------------------- AUTO PICKERS ---------------------------- #

def auto_choose_grid_k_and_t(num_consumers, num_elements, baseline=24, minT=12, maxT=32):
    """
    Pick a FIXED K (avoid 3–4 bias) and T (vignettes/respondent) automatically so that:
      • per-respondent uniqueness holds (T ≤ C(E,K)),
      • exact equal exposure is possible ((N*T*K) % E == 0),
      • T is close to 'baseline' (default 24), bounded to [minT, maxT].
    Preference order for K: 2, then 3, then 4, then 1.
    """
    N = int(num_consumers); E = int(num_elements)
    k_candidates = [k for k in (2, 3, 4, 1) if 1 <= k <= min(4, E)]
    # Search K in preference order
    for K in k_candidates:
        cap = math.comb(E, K)  # uniqueness capacity per respondent
        if cap < 1:
            continue
        # divisibility modulus for equal exposure
        m = E // math.gcd(E, N * K)  # T must be a multiple of m
        # Build T candidates near baseline within [minT, maxT]
        radius = max(maxT - baseline, baseline - minT)
        ordered = []
        for d in range(0, radius + 1):
            for sign in (+1, -1):
                t = baseline + sign * d
                if t < minT or t > maxT: 
                    continue
                if t not in ordered:
                    ordered.append(t)
        if baseline not in ordered and (minT <= baseline <= maxT):
            ordered.insert(0, baseline)
        # Filter to multiples of m within capacity
        valid = [t for t in ordered if (t % m == 0) and (t <= cap)]
        if not valid:
            # fallback: any multiple of m in range & capacity, closest to baseline
            multiples = [t for t in range(((minT + m - 1) // m) * m, min(maxT, cap) + 1, m)]
            if multiples:
                valid = [min(multiples, key=lambda x: (abs(x - baseline), -x))]
        if valid:
            T = valid[0]
            return K, T, cap, m
    # Last-resort fallback: pick K with max capacity, pick the largest feasible T multiple of m
    K = max(k_candidates, key=lambda k: math.comb(E, k))
    cap = math.comb(E, K)
    m = E // math.gcd(E, N * K)
    if cap < 1:
        raise RuntimeError("Cannot auto-pick K/T: no capacity for uniqueness.")
    # choose best T ≤ cap that is a multiple of m and within [1, maxT]
    T = max(m, min(cap, maxT) // m * m)
    return K, T, cap, m

def choose_fixed_k_for_given_T(E, T):
    """
    Given target T, choose the smallest K (≤4) such that C(E,K) ≥ T.
    Preference order: 2 -> 3 -> 4 -> 1.
    """
    for K in (2, 3, 4, 1):
        if K <= E and math.comb(E, K) >= T:
            return K
    # If none, pick K that maximizes capacity
    ks = [k for k in (2, 3, 4, 1) if k <= E]
    return max(ks, key=lambda k: math.comb(E, k))

def auto_pick_t_for_layer(category_info, baseline=24, minT=12, maxT=32):
    """
    For layer mode, per-respondent uniqueness capacity is ∏ sizes.
    Pick T closest to baseline but ≤ capacity, bounded to [minT, maxT].
    """
    sizes = [len(v) for v in category_info.values()]
    cap = 1
    for s in sizes:
        cap *= s
    if cap >= baseline:
        return baseline, cap
    # else choose the largest within [minT,maxT] that ≤ cap
    choices = [t for t in range(minT, min(maxT, cap) + 1)]
    if choices:
        # pick the one closest to baseline; prefer larger if tie
        t = min(choices, key=lambda x: (abs(x - baseline), -x))
        return t, cap
    # if cap < minT, we must accept T = cap
    return cap, cap

# ---------------------------- REPAIR (GRID MODE) ---------------------------- #

def repair_grid_counts(design_df, elem_names, target_r):
    """
    Swap 1s from overfull elements to underfull elements, within rows,
    preserving K per row and per-respondent uniqueness.
    """
    totals = design_df[elem_names].sum().astype(int).to_dict()
    row_to_cid = design_df["Consumer ID"].astype(str).to_numpy()
    X = design_df[elem_names].to_numpy()

    # Build per-row element sets and signatures
    row_elems = []
    row_sig = []
    seen_by_cid = {}
    for i in range(X.shape[0]):
        present = [elem_names[j] for j in np.flatnonzero(X[i] == 1)]
        row_elems.append(set(present))
        sig = vignette_signature_elements(present)
        row_sig.append(sig)
        s = seen_by_cid.setdefault(row_to_cid[i], set())
        s.add(sig)

    rows_by_elem = {e: set(np.flatnonzero(design_df[e].to_numpy() == 1)) for e in elem_names}

    def deficits():
        donors = [(e, totals[e] - target_r) for e in elem_names if totals[e] > target_r]
        recvs  = [(e, target_r - totals[e]) for e in elem_names if totals[e] < target_r]
        donors.sort(key=lambda x: x[1], reverse=True)   # biggest surplus first
        recvs.sort(key=lambda x: x[1], reverse=True)    # biggest need first
        return donors, recvs

    moved_any = True
    max_passes = 6
    passes = 0

    while moved_any and passes < max_passes:
        moved_any = False
        passes += 1

        donors, recvs = deficits()
        if not donors or not recvs:
            break

        recv_list = [e for e, _ in recvs]

        for don, surplus in donors:
            if totals[don] <= target_r:
                continue
            candidate_rows = list(rows_by_elem[don])
            rng.shuffle(candidate_rows)

            for r in candidate_rows:
                if totals[don] <= target_r:
                    break
                recvs = [(e, target_r - totals[e]) for e in recv_list if totals[e] < target_r]
                if not recvs:
                    break
                recvs.sort(key=lambda x: x[1], reverse=True)

                for rec, need in recvs:
                    if need <= 0 or rec in row_elems[r]:
                        continue
                    cid = row_to_cid[r]
                    new_row_elems = set(row_elems[r])
                    new_row_elems.remove(don)
                    new_row_elems.add(rec)
                    new_sig = vignette_signature_elements(sorted(new_row_elems))
                    if new_sig in seen_by_cid[cid]:
                        continue

                    design_df.at[r, don] = 0
                    design_df.at[r, rec] = 1

                    rows_by_elem[don].remove(r)
                    rows_by_elem[rec].add(r)

                    totals[don] -= 1
                    totals[rec] += 1

                    old_sig = row_sig[r]
                    seen_by_cid[cid].remove(old_sig)
                    seen_by_cid[cid].add(new_sig)
                    row_sig[r] = new_sig
                    row_elems[r] = new_row_elems

                    moved_any = True
                    break

    bad = {e: totals[e] for e in elem_names if totals[e] != target_r}
    if bad:
        raise AssertionError(f"Grid repair couldn't reach exact totals for: {bad}")
    return design_df

# ---------------------------- REPAIR (LAYER MODE) ---------------------------- #

def repair_layer_counts(design_df, category_info, tol_pct):
    """
    Post-process Layer design to bring all element totals within ±tol_pct
    of their per-category target, using within-category swaps that preserve
    per-respondent uniqueness.
    """
    total_tasks = len(design_df)
    cats = list(category_info.keys())

    # Build chosen element per row per category
    chosen = {}
    for c in cats:
        chosen[c] = design_df[category_info[c]].idxmax(axis=1).copy()

    # Build per-row signatures and per-consumer seen sets
    row_to_cid = design_df["Consumer ID"].astype(str).to_numpy()
    row_sig = [None] * total_tasks
    seen_by_cid = {}
    for i in range(total_tasks):
        pairs = [(c, chosen[c].iat[i]) for c in cats]
        sig = tuple(sorted(pairs))
        row_sig[i] = sig
        cid = row_to_cid[i]
        s = seen_by_cid.setdefault(cid, set())
        s.add(sig)

    # Build totals and bounds
    all_elems = [e for es in category_info.values() for e in es]
    totals = design_df[all_elems].sum().astype(int).to_dict()

    lower = {}
    upper = {}
    target = {}
    for c in cats:
        n = len(category_info[c])
        t = total_tasks / n
        tol_cnt = max(1, int(round(tol_pct * t)))
        for e in category_info[c]:
            target[e] = t
            lower[e] = int(np.ceil(t - tol_cnt))
            upper[e] = int(np.floor(t + tol_cnt))

    rows_by_elem = {e: set(np.flatnonzero(design_df[e].to_numpy() == 1)) for e in all_elems}

    moved_any = True
    max_passes = 4
    passes = 0

    while moved_any and passes < max_passes:
        moved_any = False
        passes += 1

        for c in cats:
            elems = category_info[c]
            lo = {e: lower[e] for e in elems}
            hi = {e: upper[e] for e in elems}

            receivers = [e for e in elems if totals[e] < lo[e]]
            if not receivers:
                continue

            donors_hi = [e for e in elems if totals[e] > hi[e]]
            donors_lo = [e for e in elems if (e not in donors_hi) and (totals[e] > lo[e])]
            donors = donors_hi + donors_lo
            if not donors:
                continue

            receivers.sort(key=lambda e: (lo[e] - totals[e]), reverse=True)
            donors.sort(key=lambda e: (totals[e] - lo[e]), reverse=True)

            for rec in receivers:
                need = lo[rec] - totals[rec]
                if need <= 0:
                    continue

                d_idx = 0
                while need > 0 and d_idx < len(donors):
                    don = donors[d_idx]
                    give_cap = totals[don] - max(lo[don], (hi[don] if don in donors_hi else lo[don]))
                    if give_cap <= 0:
                        d_idx += 1
                        continue

                    candidates = list(rows_by_elem[don])
                    rng.shuffle(candidates)

                    gave_here = 0
                    for r in candidates:
                        if give_cap <= 0 or need <= 0:
                            break
                        cid = design_df.at[r, "Consumer ID"]
                        pairs = [(cc, (rec if cc == c else chosen[cc].iat[r])) for cc in cats]
                        new_sig = tuple(sorted(pairs))
                        if new_sig in seen_by_cid[cid]:
                            continue

                        design_df.at[r, don] = 0
                        design_df.at[r, rec] = 1

                        rows_by_elem[don].remove(r)
                        rows_by_elem[rec].add(r)
                        totals[don] -= 1
                        totals[rec] += 1

                        old_sig = row_sig[r]
                        seen_by_cid[cid].remove(old_sig)
                        seen_by_cid[cid].add(new_sig)
                        row_sig[r] = new_sig
                        chosen[c].iat[r] = rec

                        give_cap -= 1
                        need -= 1
                        gave_here += 1
                        moved_any = True

                    if gave_here == 0:
                        d_idx += 1

    violations = []
    for c in cats:
        for e in category_info[c]:
            if totals[e] < lower[e] or totals[e] > upper[e]:
                violations.append((e, totals[e], target[e], lower[e], upper[e]))
    if violations:
        msg = "\n".join([f"{e}: got={got}, target≈{t:.2f}, bounds=[{lo},{hi}]"
                         for e, got, t, lo, hi in violations[:12]])
        raise AssertionError(
            "Repair could not enforce ±tolerance for some elements.\n"
            "Consider increasing tolerance slightly or elements per category.\n"
            f"Examples:\n{msg}"
        )
    return design_df

# ---------------------------- GENERATORS ---------------------------- #

def generate_grid_mode(num_consumers, tasks_per_consumer, num_elements, minK, maxK):
    """
    GRID MODE (no categories):
      - Single pool of elements {E_1,...,E_E}.
      - Each vignette has K active elements, K in [minK,maxK], cap 4.
      - Exact equal exposure across ALL elements (with repair pass).
      - Per-respondent uniqueness.
    """
    E = int(num_elements)
    if E < 1:
        raise ValueError("Number of elements must be ≥ 1.")

    total_tasks = num_consumers * tasks_per_consumer
    elem_names = [f"E_{i+1}" for i in range(E)]

    # Build K schedule so sum(K) % E == 0
    Ks = compute_k_schedule_grid(num_consumers, tasks_per_consumer, E, minK, maxK)
    sumK = int(Ks.sum())
    assert sumK % E == 0
    r = sumK // E  # per-element exact target

    # Counters
    r_elem = {e: r for e in elem_names}
    used_elem = {e: 0 for e in elem_names}
    col_index = {e: i for i, e in enumerate(elem_names)}
    design_data = np.zeros((total_tasks, E), dtype=int)

    def ranked_elements():
        return sorted(
            [(r_elem[e] - used_elem[e], rng.random(), e) for e in elem_names],
            key=lambda x: (x[0], x[1]),
            reverse=True
        )

    row = 0
    MAX_RETRIES = 200
    for cid in range(1, num_consumers + 1):
        seen = set()
        for _ in range(tasks_per_consumer):
            k_i = int(Ks[row])
            for _attempt in range(MAX_RETRIES):
                ranked = ranked_elements()
                pool_size = min(E, max(6, 2 * k_i + 4))
                pool = [e for _, _, e in ranked[:pool_size]]
                chosen = rng.choice(pool, size=k_i, replace=False)
                sig = vignette_signature_elements(chosen)
                if sig in seen:
                    continue
                for e in chosen:
                    used_elem[e] += 1
                    design_data[row, col_index[e]] = 1
                seen.add(sig)
                row += 1
                break
            else:
                raise RuntimeError(
                    "Grid mode: could not build a unique vignette within retry budget. "
                    "Try widening min/max K, increasing #elements, or reducing vignettes per respondent."
                )

    df = pd.DataFrame(design_data, columns=elem_names)
    consumer_ids = [f"C{i+1}" for i in range(num_consumers) for _ in range(tasks_per_consumer)]
    df.insert(0, "Consumer ID", consumer_ids)

    # --- Repair to exact per-element totals (fix +1/-1 drift) ---
    totals = df[elem_names].sum().astype(int).to_dict()
    if any(totals[e] != r for e in elem_names):
        df = repair_grid_counts(df, elem_names, r)

    # Final assertion
    totals = df[elem_names].sum().astype(int).to_dict()
    for e in elem_names:
        if totals[e] != r:
            raise AssertionError(f"Element {e} total {totals[e]} != target {r}")

    # For analysis, fake a single 'All' category
    category_info = {"All": elem_names}
    return df, Ks, r, category_info

def generate_layer_mode(num_consumers, tasks_per_consumer, category_info, tol_pct=0.02):
    """
    LAYER MODE (soft quotas):
      - Exactly one element from EVERY category per vignette (roles).
      - Per-respondent uniqueness (HARD).
      - Within-category element totals within ±tol_pct of equal-share target (SOFT; default 2%),
        with a repair pass.
      - Requires #categories ≤ 4 (≤4 elements per vignette).
    """
    MAX_RETRIES = 600
    CANDIDATE_WIDTH = 4

    num_categories = len(category_info)
    if num_categories > 4:
        raise ValueError("Layer mode requires number of categories (roles) ≤ 4 due to the ≤4-elements rule.")

    total_tasks = num_consumers * tasks_per_consumer

    # Targets: equal share per element within each category; tolerance -> integer bounds
    all_factors = []
    r_elem = {}
    up_bound = {}
    for cat, elems in category_info.items():
        n = len(elems)
        target = total_tasks / n
        tol_count = max(1, int(round(tol_pct * target)))
        for e in elems:
            r_elem[e] = target
            up_bound[e] = int(np.floor(target + tol_count))
            all_factors.append(e)

    factor_index = {f: i for i, f in enumerate(all_factors)}
    design_data = np.zeros((total_tasks, len(all_factors)), dtype=int)
    used_elem = {e: 0 for e in all_factors}

    cats = list(category_info.keys())

    def top_candidates(cat, width, allow_overflow):
        ranked = sorted(
            [((r_elem[e] - used_elem[e]), rng.random(), e) for e in category_info[cat]],
            key=lambda x: (x[0], x[1]),
            reverse=True
        )
        if allow_overflow:
            base = [e for _, _, e in ranked]
        else:
            not_capped = [e for _, _, e in ranked if used_elem[e] < up_bound[e]]
            base = not_capped if not_capped else [e for _, _, e in ranked]
        return base[:min(width, len(base))]

    row = 0
    for cid in range(1, num_consumers + 1):
        seen = set()
        for _ in range(tasks_per_consumer):
            success = False
            for allow_overflow in (False, True):
                for _attempt in range(MAX_RETRIES):
                    pairs = []
                    for cat in cats:
                        cands = top_candidates(cat, CANDIDATE_WIDTH, allow_overflow)
                        e = rng.choice(cands)
                        pairs.append((cat, e))
                    sig = vignette_signature_pairs(pairs)
                    if sig in seen:
                        continue
                    for _, e in pairs:
                        used_elem[e] += 1
                        design_data[row, factor_index[e]] = 1
                    seen.add(sig)
                    row += 1
                    success = True
                    break
                if success:
                    break
            if not success:
                remaining = {e: int(np.ceil(r_elem[e]) - used_elem[e]) for e in all_factors}
                raise RuntimeError(
                    "Layer mode: could not build a unique vignette within retry budget.\n"
                    "Tips: increase elements per category, reduce vignettes per respondent, increase tolerance, "
                    "or raise MAX_RETRIES/CANDIDATE_WIDTH.\n"
                    f"Remaining (approx) to targets: {remaining}"
                )

    # Repair to bring totals into ±tolerance while preserving uniqueness
    design_df = pd.DataFrame(design_data, columns=all_factors)
    consumer_ids = [f"C{i+1}" for i in range(num_consumers) for _ in range(tasks_per_consumer)]
    design_df.insert(0, "Consumer ID", consumer_ids)

    design_df = repair_layer_counts(design_df, category_info, tol_pct)

    # Final validation
    totals = design_df.drop(columns=['Consumer ID']).sum(axis=0)
    violations = []
    for cat, elems in category_info.items():
        n = len(elems)
        target = total_tasks / n
        tol_cnt = max(1, int(round(tol_pct * target)))
        lo = int(np.ceil(target - tol_cnt))
        hi = int(np.floor(target + tol_cnt))
        for e in elems:
            got = int(totals[e])
            if got < lo or got > hi:
                violations.append((e, got, target, lo, hi))
    if violations:
        msg = "\n".join([f"{e}: got={got}, target≈{t:.2f}, bounds=[{lo},{hi}]"
                         for e, got, t, lo, hi in violations[:12]])
        raise AssertionError(f"Quota tolerance exceeded for some elements after repair:\n{msg}")

    Ks = np.full(total_tasks, len(category_info), dtype=int)  # all categories active
    return design_df, Ks, None

# ---------------------------- MAIN ---------------------------- #

def generate_design():
    print("--- Helix Experimentation Engine ---")
    mode = get_user_input("Choose mode [grid/layer]: ", str, choices={"grid","layer"})

    project_name = get_user_input("Enter a project name: ", str)
    num_consumers = get_user_input("Number of respondents (e.g., 200): ", int, 1)

    if mode == "grid":
        # GRID: no categories; just a single pool of elements
        num_elements = get_user_input("Number of elements (pool size, e.g., 6+): ", int, 1)

        auto_both = get_user_input("Auto-calc vignettes/respondent AND pick a FIXED K to avoid 3–4 bias? [y/n]: ",
                                   str, choices={"y","n"})
        if auto_both == "y":
            K, T, cap, m = auto_choose_grid_k_and_t(num_consumers, num_elements, baseline=24, minT=12, maxT=32)
            print(f"\n[AUTO] Picked K={K} and T={T} (vigs/respondent). "
                  f"Capacity C({num_elements},{K})={cap}; divisibility modulus m={m}.")
            minK = maxK = K
            tasks_per_consumer = T
        else:
            tasks_per_consumer = get_user_input("Number of vignettes per respondent (e.g., 24): ", int, 1)
            auto_k = get_user_input("Auto-pick a FIXED K to avoid 3–4 bias? [y/n]: ", str, choices={"y","n"})
            if auto_k == "y":
                K = choose_fixed_k_for_given_T(num_elements, tasks_per_consumer)
                print(f"[AUTO K] Picked K={K} as the smallest K with capacity "
                      f"C({num_elements},{K})={math.comb(num_elements,K)} ≥ T={tasks_per_consumer}.")
                minK = maxK = K
            else:
                minK = get_user_input("Min active elements per vignette (1-4): ", int, 1, 4)
                maxK = get_user_input(f"Max active elements per vignette ({minK}-4): ", int, minK, 4)

        print("\n[GRID MODE] Building design with equal exposure across all elements…")
        design_df, Ks, r, catinfo_for_report = generate_grid_mode(
            num_consumers, tasks_per_consumer, num_elements, minK, maxK
        )
        category_info_for_analysis = catinfo_for_report

    else:
        # LAYER: ask for categories and elements per category
        num_categories = get_user_input("Number of categories (A, B, C...): ", int, 1, 26)
        category_names = [chr(ord('A') + i) for i in range(num_categories)]
        category_info = {}
        for c in category_names:
            n = get_user_input(f"Number of elements in Category {c} (1-20): ", int, 1, 20)
            category_info[c] = [f"{c}_{i+1}" for i in range(n)]

        auto_T_layer = get_user_input("Auto-calc vignettes/respondent for layer mode? [y/n]: ", str, choices={"y","n"})
        if auto_T_layer == "y":
            tasks_per_consumer, cap = auto_pick_t_for_layer(category_info, baseline=24, minT=12, maxT=32)
            print(f"\n[AUTO] Picked T={tasks_per_consumer} for layer mode "
                  f"(per-respondent uniqueness capacity={cap}).")
        else:
            tasks_per_consumer = get_user_input("Number of vignettes per respondent (e.g., 24): ", int, 1)

        print("\n[LAYER MODE] Building design with equal exposure within each category (±2%)…")
        design_df, Ks, r = generate_layer_mode(
            num_consumers, tasks_per_consumer, category_info, tol_pct=0.02
        )
        category_info_for_analysis = category_info

    # Save outputs
    sanitized = project_name.replace(" ", "_").strip()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = f"{sanitized}_{ts}"
    os.makedirs(folder, exist_ok=True)

    design_path = os.path.join(folder, f"{sanitized}_design.csv")
    design_df.to_csv(design_path, index=False)

    params = {
        "mode": mode,
        "project_name": project_name,
        "tasks_per_consumer": int(Ks.size // num_consumers),  # robust to both modes
        "num_consumers": num_consumers,
        "K_summary": {
            "min": int(Ks.min()),
            "max": int(Ks.max()),
            "sum": int(Ks.sum())
        },
        "tolerance_pct_layer": (0.02 if mode=="layer" else None)
    }
    if mode == "grid":
        params.update({
            "num_elements": int(design_df.shape[1] - 1),
            "per_element_target_across_elements": int(Ks.sum() // (design_df.shape[1] - 1))
        })
    else:
        params.update({
            "category_info": {k: list(v) for k, v in category_info_for_analysis.items()}
        })

    with open(os.path.join(folder, f"{sanitized}_parameters.json"), "w", encoding="utf-8") as f:
        json.dump(params, f, indent=4)

    report = analyze_design(design_df, category_info_for_analysis)
    with open(os.path.join(folder, f"{sanitized}_analysis_report.txt"), "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ Files saved in '{folder}'")
    print(f"   • Design CSV: {design_path}")
    if mode == "grid":
        print(f"   • Per-element target (across all elements): {params['per_element_target_across_elements']}")
    else:
        print("   • Within-category balance uses ±2% tolerance (with repair).")
    print("   • Analysis report and parameters JSON included.")

if __name__ == "__main__":
    generate_design()
