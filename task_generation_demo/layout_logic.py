import numpy as np
import pandas as pd
from common import rng, vignette_signature_pairs

# ---------------------------- AUTO PICKER ---------------------------- #

def auto_pick_t_for_layer(category_info, baseline=24):
    """
    Per-respondent uniqueness capacity is the product of category sizes.
    Return T = min(baseline, capacity).
    """
    sizes = [len(v) for v in category_info.values()]
    cap = 1
    for s in sizes:
        cap *= s
    return min(baseline, cap), cap

# ---------------------------- REPAIR ---------------------------- #

def repair_layer_counts(design_df, category_info, tol_pct=0.02):
    """
    Balance element exposure within each category to be within ±tol_pct
    of the per-category mean, while preserving per-respondent uniqueness
    of vignette tuples (one element per category per vignette).
    """
    total_tasks = len(design_df)
    cats = list(category_info.keys())

    # Current chosen element (column name) per category per row
    chosen = {}
    for c in cats:
        chosen[c] = design_df[category_info[c]].idxmax(axis=1).copy()

    # Track seen tuples per consumer for uniqueness constraint
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

    # Totals & targets
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
    passes = 0
    while moved_any and passes < 4:
        moved_any = False
        passes += 1

        for c in cats:
            elems = category_info[c]
            lo = {e: lower[e] for e in elems}
            # Prioritize donors that are above the upper bound, then above lower
            donors_hi = [e for e in elems if totals[e] > upper[e]]
            donors_lo = [e for e in elems if (e not in donors_hi) and (totals[e] > lo[e])]
            donors = donors_hi + donors_lo

            receivers = [e for e in elems if totals[e] < lo[e]]
            if not receivers or not donors:
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
                    give_cap = totals[don] - (upper[don] if don in donors_hi else lo[don])
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

                        # Build a prospective tuple replacing only this category's element
                        pairs = [(cc, (rec if cc == c else chosen[cc].iat[r])) for cc in cats]
                        new_sig = tuple(sorted(pairs))
                        if new_sig in seen_by_cid[cid]:
                            continue  # would duplicate within this consumer

                        # Perform swap
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

    # Verify bounds (best-effort, but raise if still out-of-bounds)
    violations = []
    for c in cats:
        n = len(category_info[c])
        t = total_tasks / n
        tol_cnt = max(1, int(round(tol_pct * t)))
        lo = int(np.ceil(t - tol_cnt))
        hi = int(np.floor(t + tol_cnt))
        for e in category_info[c]:
            got = int(design_df[e].sum())
            if got < lo or got > hi:
                violations.append((e, got, t, lo, hi))
    if violations:
        msg = "\n".join(
            [f"{e}: got={got}, target≈{t:.2f}, bounds=[{lo},{hi}]" for e, got, t, lo, hi in violations[:12]]
        )
        raise AssertionError(
            "Repair could not enforce ±tolerance for some elements.\n"
            "Increase tolerance / elements per category / or reduce T.\n"
            f"Examples:\n{msg}"
        )
    return design_df

# ---------------------------- GENERATOR ---------------------------- #

def generate_layer_mode(num_consumers, tasks_per_consumer, category_info, tol_pct=0.02):
    """
    Exactly one element from EVERY category per vignette (any number of categories).
    Per-respondent uniqueness (hard).
    Within-category element totals balanced within ±tol_pct (soft) with a repair pass.
    """
    MAX_RETRIES = 600
    CANDIDATE_WIDTH = 4  # shortlist per category when picking

    cats = list(category_info.keys())
    if len(cats) < 1:
        raise ValueError("Layer mode requires at least one category.")

    total_tasks = num_consumers * tasks_per_consumer

    # Per-element targets and upper bounds (soft)
    all_factors = []
    r_elem = {}
    up_bound = {}
    for cat, elems in category_info.items():
        n = len(elems)
        if n < 1:
            raise ValueError(f"Category '{cat}' must contain at least one element.")
        target = total_tasks / n
        tol_count = max(1, int(round(tol_pct * target)))
        for e in elems:
            r_elem[e] = target
            up_bound[e] = int(np.floor(target + tol_count))
            all_factors.append(e)

    factor_index = {f: i for i, f in enumerate(all_factors)}
    design_data = np.zeros((total_tasks, len(all_factors)), dtype=int)
    used_elem = {e: 0 for e in all_factors}

    def top_candidates(cat, width, allow_overflow):
        ranked = sorted(
            [((r_elem[e] - used_elem[e]), rng.random(), e) for e in category_info[cat]],
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )
        if allow_overflow:
            base = [e for _, _, e in ranked]
        else:
            not_capped = [e for _, _, e in ranked if used_elem[e] < up_bound[e]]
            base = not_capped if not_capped else [e for _, _, e in ranked]
        return base[: min(width, len(base))]

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
                    # commit
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
                    "Increase elements/category, reduce T, increase tolerance or retries.\n"
                    f"Remaining (approx) to targets: {remaining}"
                )

    design_df = pd.DataFrame(design_data, columns=all_factors)
    consumer_ids = [f"C{i+1}" for i in range(num_consumers) for _ in range(tasks_per_consumer)]
    design_df.insert(0, "Consumer ID", consumer_ids)

    # Balance within tolerance (fixed 2%)
    design_df = repair_layer_counts(design_df, category_info, tol_pct=0.02)

    # K is exactly the number of categories active per vignette
    Ks = np.full(total_tasks, len(cats), dtype=int)
    return design_df, Ks, None
