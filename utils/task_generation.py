"""
Task Generation Logic for IPED Studies
Based on the algorithms from task_generation_demo directory
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import random

# Global RNG for consistent seeding
_rng = np.random.default_rng()

def set_seed(seed: Optional[int] = None):
    """Set the global random seed for task generation."""
    global _rng
    if seed is not None:
        _rng = np.random.default_rng(seed)
        random.seed(seed)
    else:
        _rng = np.random.default_rng()
        random.seed()

# ---------------------------- GRID STUDY LOGIC ---------------------------- #

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

def vignette_signature_elements(elem_list):
    """Canonical signature for per-respondent uniqueness (grid mode)."""
    return tuple(sorted(elem_list))

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

            candidate_rows = list(rows_by_elem[don]); _rng.shuffle(candidate_rows)
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
    elem_names = [f"E{i+1}" for i in range(E)]  # Changed from E_{i+1} to E{i+1} to match element_id

    Ks = compute_k_schedule_grid(num_consumers, tasks_per_consumer, E, minK, maxK)
    sumK = int(Ks.sum())
    r_mean = sumK / E  # float target

    used_elem = {e: 0 for e in elem_names}
    col_index = {e: i for i, e in enumerate(elem_names)}
    design_data = np.zeros((total_tasks, E), dtype=int)

    def ranked_elements():
        # rank by (deficit vs r_mean), then small random jitter
        return sorted(
            [((r_mean - used_elem[e]), _rng.random(), e) for e in elem_names],
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
                chosen = _rng.choice(pool, size=k_i, replace=False)
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

# ---------------------------- LAYER STUDY LOGIC ---------------------------- #

def vignette_signature_pairs(cat_elem_pairs):
    """Canonical signature for per-respondent uniqueness (layout mode)."""
    return tuple(sorted(cat_elem_pairs, key=lambda x: x[0]))

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
                    _rng.shuffle(candidates)
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
            [((r_elem[e] - used_elem[e]), _rng.random(), e) for e in category_info[cat]],
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
                        e = _rng.choice(cands)
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
    design_df = repair_layer_counts(design_df, category_info, tol_pct=tol_pct)

    # K is exactly the number of categories active per vignette
    Ks = np.full(total_tasks, len(cats), dtype=int)
    return design_df, Ks, None

# ---------------------------- MAIN GENERATOR FUNCTIONS ---------------------------- #

def generate_grid_tasks(num_elements: int, tasks_per_consumer: int, number_of_respondents: int, 
                       exposure_tolerance_cv: float = 1.0, seed: Optional[int] = None, 
                       elements: Optional[List] = None) -> Dict[str, Any]:
    """
    Generate tasks for grid studies using the new algorithm.
    
    Args:
        num_elements: Number of elements (E)
        tasks_per_consumer: Tasks per consumer (T)
        number_of_respondents: Number of respondents (N)
        exposure_tolerance_cv: Exposure tolerance as coefficient of variation percentage
        seed: Random seed for reproducibility
        elements: Optional list of StudyElement objects for content
    
    Returns:
        Dictionary containing task matrix and metadata
    """
    # Set seed if provided
    if seed is not None:
        set_seed(seed)
    
    # Convert percentage to decimal
    exposure_tol_cv = exposure_tolerance_cv / 100.0
    
    # Get K and validate T
    minK, maxK, T, cap, notes = choose_k_t_capped_policy(
        number_of_respondents, num_elements, maxT=24, exposure_tol_cv=exposure_tol_cv
    )
    
    # Validate that requested T doesn't exceed capacity
    if tasks_per_consumer > cap:
        raise ValueError(f"Tasks per consumer ({tasks_per_consumer}) exceeds uniqueness capacity ({cap}) for {num_elements} elements with K={minK}")
    
    # Generate design matrix
    design_df, Ks, r_stats, category_info = generate_grid_mode(
        num_consumers=number_of_respondents,
        tasks_per_consumer=tasks_per_consumer,
        num_elements=num_elements,
        minK=minK,
        maxK=maxK,
        exposure_tol_cv=exposure_tol_cv
    )
    
    # Convert to task structure
    tasks_structure = {}
    element_names = [f"E{i+1}" for i in range(num_elements)]  # Match the naming convention from generate_grid_mode
    
    for respondent_id in range(number_of_respondents):
        respondent_tasks = []
        start_idx = respondent_id * tasks_per_consumer
        end_idx = start_idx + tasks_per_consumer
        
        # Get tasks for this specific respondent
        respondent_data = design_df.iloc[start_idx:end_idx]
        
        for task_index, (_, task_row) in enumerate(respondent_data.iterrows()):
            # Create elements_shown dictionary
            elements_shown = {}
            for i, element_name in enumerate(element_names):
                # Element is only shown if it's active in this task
                element_active = int(task_row[element_name])
                elements_shown[element_name] = element_active
                
                # Element content is only shown if the element itself is shown
                if element_active and elements and i < len(elements):
                    elements_shown[f"{element_name}_content"] = getattr(elements[i], 'content', '')
                else:
                    elements_shown[f"{element_name}_content"] = ""
            
            # Clean up any _ref entries that might exist (they shouldn't be there)
            elements_shown = {k: v for k, v in elements_shown.items() if not k.endswith('_ref')}
            
            task_obj = {
                "task_id": f"{respondent_id}_{task_index}",
                "elements_shown": elements_shown,
                "task_index": task_index
            }
            respondent_tasks.append(task_obj)
        
        tasks_structure[str(respondent_id)] = respondent_tasks
    
    return {
        'tasks': tasks_structure,
        'metadata': {
            'study_type': 'grid',
            'num_elements': num_elements,
            'tasks_per_consumer': tasks_per_consumer,
            'number_of_respondents': number_of_respondents,
            'K': minK,
            'exposure_tolerance_cv': exposure_tolerance_cv,
            'exposure_stats': r_stats,
            'notes': notes
        }
    }

def generate_layer_tasks(category_info: Dict[str, List[str]], number_of_respondents: int,
                        exposure_tolerance_pct: float = 2.0, seed: Optional[int] = None,
                        elements: Optional[Dict[str, List]] = None) -> Dict[str, Any]:
    """
    Generate tasks for layer studies using the new algorithm.
    
    Args:
        category_info: Dictionary mapping category names to element lists
        number_of_respondents: Number of respondents (N)
        exposure_tolerance_pct: Exposure tolerance as percentage
        seed: Random seed for reproducibility
        elements: Optional dictionary mapping category names to StudyElement objects for content
    
    Returns:
        Dictionary containing task matrix and metadata
    """
    # Set seed if provided
    if seed is not None:
        set_seed(seed)
    
    # Auto-calculate tasks per consumer
    tasks_per_consumer, capacity = auto_pick_t_for_layer(category_info, baseline=24)
    
    # Generate design matrix
    design_df, Ks, _ = generate_layer_mode(
        num_consumers=number_of_respondents,
        tasks_per_consumer=tasks_per_consumer,
        category_info=category_info,
        tol_pct=exposure_tolerance_pct / 100.0
    )
    
    # Convert to task structure
    tasks_structure = {}
    all_elements = [e for es in category_info.values() for e in es]
    
    for respondent_id in range(number_of_respondents):
        respondent_tasks = []
        start_idx = respondent_id * tasks_per_consumer
        end_idx = start_idx + tasks_per_consumer
        
        # Get tasks for this specific respondent
        respondent_data = design_df.iloc[start_idx:end_idx]
        
        for task_index, (_, task_row) in enumerate(respondent_data.iterrows()):
            # Create elements_shown dictionary
            elements_shown = {}
            for element_name in all_elements:
                # Element is only shown if it's active in this task
                element_active = int(task_row[element_name])
                elements_shown[element_name] = element_active
                
                # Element content is only shown if the element itself is shown
                if element_active and elements:
                    # Find the element in the elements dictionary
                    element_found = False
                    for category_name, category_elements in elements.items():
                        for element in category_elements:
                            if element.name == element_name:
                                elements_shown[f"{element_name}_content"] = getattr(element, 'content', '')
                                element_found = True
                                break
                        if element_found:
                            break
                    
                    if not element_found:
                        elements_shown[f"{element_name}_content"] = ""
                else:
                    elements_shown[f"{element_name}_content"] = ""
            
            # Clean up any _ref entries that might exist (they shouldn't be there)
            elements_shown = {k: v for k, v in elements_shown.items() if not k.endswith('_ref')}
            
            task_obj = {
                "task_id": f"{respondent_id}_{task_index}",
                "elements_shown": elements_shown,
                "task_index": task_index
            }
            respondent_tasks.append(task_obj)
        
        tasks_structure[str(respondent_id)] = respondent_tasks
    
    return {
        'tasks': tasks_structure,
        'metadata': {
            'study_type': 'layer',
            'category_info': category_info,
            'tasks_per_consumer': tasks_per_consumer,
            'number_of_respondents': number_of_respondents,
            'exposure_tolerance_pct': exposure_tolerance_pct,
            'capacity': capacity
        }
    }

def generate_layer_tasks_v2(layers_data: List[Dict], number_of_respondents: int,
                           exposure_tolerance_pct: float = 2.0, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate tasks for the new layer structure (vignette-based approach).
    
    Args:
        layers_data: List of layer objects with images
        number_of_respondents: Number of respondents (N)
        exposure_tolerance_pct: Exposure tolerance as percentage
        seed: Random seed for reproducibility
    
    Returns:
        Dictionary containing task matrix and metadata
    """
    # Set seed if provided
    if seed is not None:
        set_seed(seed)
    
    # Convert layers data to category_info format for the existing algorithm
    category_info = {}
    for layer in layers_data:
        layer_name = layer['name']
        # Create element names for this layer (e.g., "Background_1", "Background_2")
        elements = [f"{layer_name}_{i+1}" for i in range(len(layer['images']))]
        category_info[layer_name] = elements
    
    # Auto-calculate tasks per consumer
    tasks_per_consumer, capacity = auto_pick_t_for_layer(category_info, baseline=24)
    
    # Generate design matrix using existing algorithm
    design_df, Ks, _ = generate_layer_mode(
        num_consumers=number_of_respondents,
        tasks_per_consumer=tasks_per_consumer,
        category_info=category_info,
        tol_pct=exposure_tolerance_pct / 100.0
    )
    
    # Convert to task structure with image content
    tasks_structure = {}
    all_elements = [e for es in category_info.values() for e in es]
    
    for respondent_id in range(number_of_respondents):
        respondent_tasks = []
        start_idx = respondent_id * tasks_per_consumer
        end_idx = start_idx + tasks_per_consumer
        
        # Get tasks for this specific respondent
        respondent_data = design_df.iloc[start_idx:end_idx]
        
        for task_index, (_, task_row) in enumerate(respondent_data.iterrows()):
            # Create elements_shown dictionary
            elements_shown = {}
            elements_shown_content = {}
            
            for element_name in all_elements:
                # Element is only shown if it's active in this task
                element_active = int(task_row[element_name])
                elements_shown[element_name] = element_active
                
                # Find the corresponding image for this element
                if element_active:
                    # Parse element name to find layer and image index
                    # Format: "LayerName_ImageIndex" (e.g., "Background_1")
                    if '_' in element_name:
                        layer_name, img_index_str = element_name.rsplit('_', 1)
                        try:
                            img_index = int(img_index_str) - 1  # Convert to 0-based index
                            
                            # Find the layer and image
                            for layer in layers_data:
                                if layer['name'] == layer_name and img_index < len(layer['images']):
                                    image = layer['images'][img_index]
                                    elements_shown_content[element_name] = {
                                        'url': image['url'],
                                        'name': image['name'],
                                        'alt_text': image.get('alt', image.get('alt_text', '')),
                                        'layer_name': layer_name,
                                        'z_index': layer['z_index']
                                    }
                                    break
                            else:
                                elements_shown_content[element_name] = None
                        except ValueError:
                            elements_shown_content[element_name] = None
                    else:
                        elements_shown_content[element_name] = None
                else:
                    elements_shown_content[element_name] = None
            
            # Clean up any _ref entries
            elements_shown = {k: v for k, v in elements_shown.items() if not k.endswith('_ref')}
            elements_shown_content = {k: v for k, v in elements_shown_content.items() if not k.endswith('_ref')}
            
            task_obj = {
                "task_id": f"{respondent_id}_{task_index}",
                "elements_shown": elements_shown,
                "elements_shown_content": elements_shown_content,
                "task_index": task_index
            }
            respondent_tasks.append(task_obj)
        
        tasks_structure[str(respondent_id)] = respondent_tasks
    
    return {
        'tasks': tasks_structure,
        'metadata': {
            'study_type': 'layer_v2',
            'layers_data': layers_data,
            'category_info': category_info,
            'tasks_per_consumer': tasks_per_consumer,
            'number_of_respondents': number_of_respondents,
            'exposure_tolerance_pct': exposure_tolerance_pct,
            'capacity': capacity
        }
    }
