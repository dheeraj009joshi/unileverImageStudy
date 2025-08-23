# grid_logic.py
import math
import numpy as np
import pandas as pd
from common import rng, vignette_signature_elements

# ---------------------------- POLICY (SOFT EXPOSURE) ---------------------------- #

def target_k_from_e(E: int) -> int:
    """
    Preferred K based on E, clamped to [2,4]:
      4–8   -> K = 2
      9–16  -> K = 3
      17+   -> K = 4
    """
    if E <= 8:
        return 2
    elif E <= 16:
        return 3
    else:
        return 4


def choose_k_t_capped_policy(num_consumers: int, num_elements: int, maxT: int = 24, exposure_tol_cv: float = 0.01):
    """
    SOFT exposure policy (no exact modulus):
      • Hard cap: T ≤ maxT.
      • Per-respondent uniqueness: T ≤ C(E,K).
      • Exposure balance: aim for std-dev ≤ exposure_tol_cv * mean (~1%).
      • Constant K by breakpoints.

    Returns: (minK, maxK, T, cap, notes)
    """
    N = int(num_consumers)
    E = int(num_elements)
    if E < 4:
        raise ValueError("E must be at least 4 (K in [2,4]).")

    # Preferred constant K by breakpoint
    if 4 <= E <= 8:
        K = 2
    elif 9 <= E <= 16:
        K = 3
    else:  # E >= 17
        K = 4
    K = min(max(2, K), min(4, E))

    cap = math.comb(E, K)          # per-respondent uniqueness capacity
    T = min(maxT, cap)             # push to the hard cap; no modulus

    notes = []
    if cap < maxT:
        notes.append(f"Capacity C({E},{K})={cap} < {maxT}; T clipped to {T}.")
    else:
        notes.append(f"T set to {T} (no modulus; soft exposure target {100*exposure_tol_cv:.2f}% CV).")

    return K, K, T, cap, notes

# ---------------------------- K SCHEDULE ---------------------------- #

def compute_k_schedule_grid(num_consumers, tasks_per_consumer, E, minK, maxK):
    """
    Per-respondent K schedule (cap 4), **SOFT exposure** version:
      • K in [minK, maxK],
      • uniqueness feasible,
      • NO exact-exposure divisibility constraint.
    For this policy we use constant K (minK == maxK).
    """
    if maxK > 4: raise ValueError("maxK cannot exceed 4.")
    if minK > maxK: raise ValueError("minK cannot exceed maxK.")
    if E < maxK: raise ValueError("Number of elements must be ≥ max active elements.")

    N = int(num_consumers); T = int(tasks_per_consumer)
    if minK == maxK:
        cap_const = math.comb(E, minK)
        if T > cap_const:
            raise RuntimeError(f"Uniqueness impossible for K={minK}: T={T} > C({E},{minK})={cap_const}.")
        return np.full(N * T, minK, dtype=int)

    # If someone passes a range, keep it simple without divisibility rules:
    # Distribute maxK sparsely but we are not using this in the current policy.
    raise NotImplementedError("This policy expects constant K (minK == maxK).")

# ---------------------------- SOFT REPAIR ---------------------------- #

def _compute_exposure_stats(df, elem_names):
    counts = df[elem_names].sum().astype(float).to_numpy()
    mean = float(np.mean(counts)) if counts.size else 0.0
    std = float(np.std(counts, ddof=0)) if counts.size else 0.0
    cv = (std / mean) if mean > 0 else 0.0
    return counts, mean, std, cv

def soft_repair_grid_counts(design_df, elem_names, exposure_tol_cv=0.01, max_passes=8):
    """
    Reduce exposure std-dev toward ≤ exposure_tol_cv * mean using single-bit swaps
    that preserve per-respondent uniqueness.
    """
    totals = design_df[elem_names].sum().astype(int).to_dict()
    row_to_cid = design_df["Consumer ID"].astype(str).to_numpy()
    X = design_df[elem_names].to_numpy()

    # Build row structures
    row_elems = []
    row_sig = []
    seen_by_cid = {}
    for i in range(X.shape[0]):
        present = [elem_names[j] for j in np.flatnonzero(X[i] == 1)]
        row_elems.append(set(present))
        sig = vignette_signature_elements(present)
        row_sig.append(sig)
        s = seen_by_cid.setdefault(row_to_cid[i], set()); s.add(sig)

    rows_by_elem = {e: set(np.flatnonzero(design_df[e].to_numpy() == 1)) for e in elem_names}

    # Stats
    _, mean, std, cv = _compute_exposure_stats(design_df, elem_names)
    if cv <= exposure_tol_cv:
        return design_df  # already good enough

    moved_any = True
    passes = 0
    while moved_any and passes < max_passes:
        moved_any = False; passes += 1

        # Recompute donors/receivers by deviation from mean
        diffs = {e: (totals[e] - mean) for e in elem_names}
        donors = [(e, diffs[e]) for e in elem_names if diffs[e] > 0]   # above mean
        recvs  = [(e, -diffs[e]) for e in elem_names if diffs[e] < 0]  # below mean
        donors.sort(key=lambda x: x[1], reverse=True)
        recvs.sort(key=lambda x: x[1], reverse=True)
        if not donors or not recvs:
            break

        recv_list = [e for e, _ in recvs]

        for don, _over in donors:
            # stop early if std-dev already within tol
            _, mean, std, cv = _compute_exposure_stats(design_df, elem_names)
            if cv <= exposure_tol_cv:
                return design_df

            candidate_rows = list(rows_by_elem[don]); rng.shuffle(candidate_rows)
            for r in candidate_rows:
                recvs_candidates = [(e, 1) for e in recv_list if totals[e] < mean and e not in row_elems[r]]
                if not recvs_candidates:
                    continue

                for rec, _need in recvs_candidates:
                    # Try swapping don -> rec in row r
                    cid = row_to_cid[r]
                    new_row_elems = set(row_elems[r]); new_row_elems.remove(don); new_row_elems.add(rec)
                    new_sig = vignette_signature_elements(sorted(new_row_elems))
                    if new_sig in seen_by_cid[cid]:
                        continue  # would duplicate within this consumer

                    # Do the swap
                    design_df.at[r, don] = 0; design_df.at[r, rec] = 1
                    rows_by_elem[don].remove(r); rows_by_elem[rec].add(r)
                    totals[don] -= 1; totals[rec] += 1

                    old_sig = row_sig[r]
                    seen_by_cid[cid].remove(old_sig); seen_by_cid[cid].add(new_sig)
                    row_sig[r] = new_sig; row_elems[r] = new_row_elems
                    moved_any = True
                    break
                if moved_any:
                    break

        # Check after pass
        _, mean, std, cv = _compute_exposure_stats(design_df, elem_names)
        if cv <= exposure_tol_cv:
            return design_df

    return design_df  # best effort

# ---------------------------- GENERATOR ---------------------------- #

def generate_grid_mode(num_consumers, tasks_per_consumer, num_elements, minK, maxK, exposure_tol_cv=0.01):
    """
    Returns:
      design_df, Ks, r_stats, category_info_for_analysis

    SOFT exposure:
      • We aim for mean exposure r_mean = (sumK / E) (float, not forced-integer).
      • Ranking uses deficits vs r_mean to keep counts tight.
      • A soft repair pass reduces std-dev toward the tolerance.
    """
    E = int(num_elements)
    if E < 1: raise ValueError("Number of elements must be ≥ 1.")

    total_tasks = num_consumers * tasks_per_consumer
    elem_names = [f"E_{i+1}" for i in range(E)]

    Ks = compute_k_schedule_grid(num_consumers, tasks_per_consumer, E, minK, maxK)
    sumK = int(Ks.sum())
    r_mean = sumK / E  # float target

    used_elem = {e: 0 for e in elem_names}
    col_index = {e: i for i, e in enumerate(elem_names)}
    design_data = np.zeros((total_tasks, E), dtype=int)

    def ranked_elements():
        # rank by (deficit vs r_mean), then small random jitter
        return sorted(
            [((r_mean - used_elem[e]), rng.random(), e) for e in elem_names],
            key=lambda x: (x[0], x[1]), reverse=True
        )

    row = 0; MAX_RETRIES = 200
    for cid in range(1, num_consumers + 1):
        seen = set()
        for _ in range(tasks_per_consumer):
            k_i = int(Ks[row])
            for _attempt in range(MAX_RETRIES):
                ranked = ranked_elements()
                pool_size = min(E, max(6, 2 * k_i + 4))
                pool = [e for _, _, e in ranked[:pool_size]]
                chosen = rng.choice(pool, size=k_i, replace=False)
                sig = vignette_signature_elements(sorted(chosen))
                if sig in seen:
                    continue
                for e in chosen:
                    used_elem[e] += 1
                    design_data[row, col_index[e]] = 1
                seen.add(sig); row += 1; break
            else:
                raise RuntimeError(
                    "Grid mode: couldn't build a unique vignette. "
                    "Increase #elements or reduce vignettes/respondent."
                )

    df = pd.DataFrame(design_data, columns=elem_names)
    consumer_ids = [f"C{i+1}" for i in range(num_consumers) for _ in range(tasks_per_consumer)]
    df.insert(0, "Consumer ID", consumer_ids)

    # Soft repair toward ≤1% CV (best effort)
    df = soft_repair_grid_counts(df, elem_names, exposure_tol_cv=exposure_tol_cv)

    # Final stats (returned for visibility)
    counts, mean, std, cv = _compute_exposure_stats(df, elem_names)
    r_stats = {"mean": mean, "std": std, "cv_pct": 100.0 * cv}

    category_info = {"All": elem_names}
    return df, Ks, r_stats, category_info
