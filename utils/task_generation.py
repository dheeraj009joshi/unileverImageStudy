"""
Task Generation Logic for IPED Studies
Based on the algorithms from task_generation_demo directory
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import random
from collections import Counter
import os
import time
import signal
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

# Global RNG for consistent seeding
_rng = np.random.default_rng()

# Worker function for multiprocessing (must be at module level for pickling)
def _build_one_worker(args):
    """
    Worker function that runs in a separate process.
    Returns: (resp_id, rows, X_df, report)
    """
    (resp_id, T, category_info, E, A_min_used, base_seed, log_every_rows,
     study_mode, max_active_per_row) = args
    
    # Keep progress cadence
    global LOG_EVERY_ROWS
    LOG_EVERY_ROWS = log_every_rows
    
    rows, X, report = build_respondent_with_uniqueness(
        T, category_info, E, A_min_used, base_seed, resp_id,
        study_mode, max_active_per_row
    )
    return (resp_id, rows, X, report)

# Constants from final_builder_parallel.py
PER_ELEM_EXPOSURES = 3     # minimum exposures per element
MIN_ACTIVE_PER_ROW = 2     # min actives per vignette
SAFETY_ROWS        = 3     # OLS safety above P
GLOBAL_RESTARTS    = 200   # rebuild attempts per respondent (brute force inside builder)
SWAP_TRIES         = 8000  # swap tries per row (brute force for uniqueness/targets)
HARD_CAP_SWAP_TRIES = 30000  # extra attempts to enforce MAX_ACTIVE_PER_ROW hard cap
BASE_SEED          = 12345
LOG_EVERY_ROWS     = 25

# Study modes
DEFAULT_STUDY_MODE = "layout"   # "layout" or "grid"
GRID_MAX_ACTIVE    = 4          # grid constraint

# Absence policy: absences per category >= ceil(ABSENCE_RATIO * E)
ABSENCE_RATIO      = 2.0   # 1.0 ≈ "absences ~ exposures"; 2.0 = "twice exposures", etc.

# Row-mix shaping (controls variation in # of active categories per row)
ROW_MIX_MODE       = "wide"  # "dense" (old behavior) or "wide" (more 3s & 5s)
ROW_MIX_WIDEN      = 0.40    # fraction of rows to push to (base-1); same + deficit go to (base+1)

# Optional "don't think, just pick a ratio" knob for T
T_RATIO            = 1.50    # scale rows/respondent above minimal feasible T

# Per-respondent safety: enforce **no duplicate columns** in each person's design matrix
PER_RESP_UNIQUE_COLS_ENFORCE = True

# Planner preferences
CAPACITY_SLACK     = 1       # try to keep at least this many patterns un-used (avoid T==cap)

# Professor gate (QC) knobs
QC_RANDOM_Y_K      = 5       # number of random dependent variables per respondent
QC_KAPPA_MAX       = 1e6     # condition number upper bound (tight)
QC_RANK_TOL        = 1e-12   # singular value cutoff for rank
QC_LS_TOL          = 1e-6    # tolerance on normal equations residual
VIF_TOL_MIN        = 1e-6    # per-column tolerance = 1 / max(VIF) threshold

def set_seed(seed: Optional[int] = None):
    """Set the global random seed for task generation."""
    global _rng
    if seed is not None:
        _rng = np.random.default_rng(seed)
        random.seed(seed)

# Helper functions from final_builder_parallel.py
def is_abs(val: str) -> bool:
    return isinstance(val, str) and str(val).startswith("__ABS__")

def sig_pair(cat: str, val: str) -> Tuple[str, str]:
    return (cat, "__ABS__") if is_abs(val) else (cat, str(val))

def params_main_effects(category_info: Dict[str, List[str]]) -> int:
    C = len(category_info)
    M = sum(len(v) for v in category_info.values())
    return M - C + 1  # intercept + (n_c - 1) per category

def visible_capacity(category_info: Dict[str, List[str]],
                     min_active: int,
                     max_active: Optional[int] = None) -> int:
    """Absence-collapsed count of distinct row patterns with ≥ min_active actives,
       optionally capped at ≤ max_active actives per row."""
    cats = list(category_info.keys())
    m = [len(category_info[c]) for c in cats]
    C = len(m)
    coeff = [0]*(C+1); coeff[0] = 1
    for mi in m:
        nxt=[0]*(C+1)
        for k in range(C+1):
            if coeff[k]==0: continue
            nxt[k] += coeff[k]           # ABS choice
            if k+1<=C: nxt[k+1] += coeff[k]*mi  # choose an element
        coeff = nxt
    hi = C if max_active is None else min(max_active, C)
    lo = max(min_active, 0)
    if lo > hi:
        return 0
    return sum(coeff[k] for k in range(lo, hi+1))

def one_hot_df_from_rows(rows: List[Dict[str,str]], category_info: Dict[str,List[str]]) -> pd.DataFrame:
    cats = list(category_info.keys())
    elems = [e for es in category_info.values() for e in es]
    recs = []
    for row in rows:
        d = {e: 0 for e in elems}
        for c in cats:
            ch = row[c]
            if ch in elems: d[ch] = 1
        recs.append(d)
    return pd.DataFrame(recs, columns=elems)

def per_respondent_duplicate_pairs(X: pd.DataFrame) -> List[Tuple[str,str]]:
    """Return list of (colA, colB) that are exact duplicates within this respondent."""
    col_map = {}
    dups = []
    for col in X.columns:
        key = tuple(int(v) for v in X[col].tolist())
        if key in col_map:
            dups.append((col_map[key], col))
    else:
            col_map[key] = col
    return dups

def max_cross_category_correlation(X: pd.DataFrame, category_info: Dict[str,List[str]]) -> Tuple[float, Tuple[str,str]]:
    """Compute max absolute Pearson r across elements from different categories."""
    cat_of = {}
    for c, es in category_info.items():
        for e in es:
            cat_of[e] = c
    max_abs_r = 0.0
    max_pair = ("","")
    cols = list(X.columns)
    for i in range(len(cols)):
        e1 = cols[i]
        for j in range(i+1, len(cols)):
            e2 = cols[j]
            if cat_of[e1] == cat_of[e2]:
                continue
            r = np.corrcoef(X[e1].to_numpy(), X[e2].to_numpy())[0,1]
            if abs(r) > max_abs_r:
                max_abs_r = abs(r)
                max_pair = (e1, e2)
    return float(max_abs_r), max_pair

def professor_gate(X: pd.DataFrame,
                   k: int = QC_RANDOM_Y_K,
                   kappa_max: float = QC_KAPPA_MAX,
                   rank_tol: float = QC_RANK_TOL,
                   ls_tol: float = QC_LS_TOL,
                   rng_seed: Optional[int] = None) -> Tuple[bool, dict]:
    """
    Gate (no intercept), optimized:
      - zero-variance columns = 0
      - full rank by SVD (rank == p)
      - condition number ≤ kappa_max
      - min tolerance (1 / max VIF) ≥ VIF_TOL_MIN
      - K random-DV fits: rank==p and normal-eq residual small, all K/ K
    """
    Xn = X.to_numpy(dtype=float)
    n, p = Xn.shape

    # ---------- cheap early exits ----------
    col_var = Xn.var(axis=0)
    zero_var = int(np.sum(col_var == 0.0))
    if zero_var:
        return False, {
            "zero_var": int(zero_var), "rank": 0, "p": int(p),
            "s_min": float("nan"), "s_max": float("nan"), "kappa": float("inf"),
            "dup_pairs": 0, "max_vif": float("inf"), "min_tolerance": 0.0,
            "tolerance_ok": False, "corr_inv_exact": False,
            "fit_rank_passes": 0, "ls_passes": 0, "ls_total": int(k), "passed": False,
        }

    dups = per_respondent_duplicate_pairs(X)
    if dups:
        return False, {
            "zero_var": 0, "rank": 0, "p": int(p),
            "s_min": float("nan"), "s_max": float("nan"), "kappa": float("inf"),
            "dup_pairs": int(len(dups)), "max_vif": float("inf"), "min_tolerance": 0.0,
            "tolerance_ok": False, "corr_inv_exact": False,
            "fit_rank_passes": 0, "ls_passes": 0, "ls_total": int(k), "passed": False,
        }

    # ---------- one SVD (rank & kappa) ----------
    U, s, Vt = np.linalg.svd(Xn, full_matrices=False)
    rank = int(np.sum(s > QC_RANK_TOL))
    full_rank = (rank == p)
    s_min = float(np.min(s)) if s.size else float('nan')
    s_max = float(np.max(s)) if s.size else float('nan')
    kappa = float(s_max / s_min) if s_min > 0 else float('inf')
    if (not full_rank) or (kappa > kappa_max):
        return False, {
            "zero_var": 0, "rank": int(rank), "p": int(p),
            "s_min": float(s_min), "s_max": float(s_max), "kappa": float(kappa),
            "dup_pairs": 0, "max_vif": float("inf"), "min_tolerance": 0.0,
            "tolerance_ok": False, "corr_inv_exact": False,
            "fit_rank_passes": 0, "ls_passes": 0, "ls_total": int(k), "passed": False,
        }

    # ---------- tolerance / VIF via correlation inverse ----------
    XT = Xn.T
    G  = XT @ Xn
    norms = np.sqrt(np.diag(G))
    eps = 1e-15
    norms = np.where(norms < eps, eps, norms)
    D_inv = np.diag(1.0 / norms)
    Rcorr = D_inv @ G @ D_inv
    try:
        Rinv = np.linalg.inv(Rcorr)
        inv_ok = True
    except np.linalg.LinAlgError:
        Rinv = np.linalg.pinv(Rcorr, rcond=QC_RANK_TOL)
        inv_ok = False
    vif = np.maximum(np.diag(Rinv), 1.0)
    max_vif = float(np.max(vif))
    min_tolerance = float(1.0 / max_vif)
    tolerance_ok = (min_tolerance >= VIF_TOL_MIN)
    if not tolerance_ok:
        return False, {
            "zero_var": 0, "rank": int(rank), "p": int(p),
            "s_min": float(s_min), "s_max": float(s_max), "kappa": float(kappa),
            "dup_pairs": 0, "max_vif": float(max_vif), "min_tolerance": float(min_tolerance),
            "tolerance_ok": False, "corr_inv_exact": bool(inv_ok),
            "fit_rank_passes": 0, "ls_passes": 0, "ls_total": int(k), "passed": False,
        }

    # ---------- batched stress tests (QR once, K solves) ----------
    Q, R = np.linalg.qr(Xn, mode="reduced")  # X = Q R
    rng = np.random.default_rng(rng_seed)
    Y = rng.integers(1, 10, size=(n, k)).astype(float)  # n x K
    QTy = Q.T @ Y                                        # p x K
    B = np.linalg.solve(R, QTy)

    # rank check per RHS
    rdiag_ok = np.all(np.abs(np.diag(R)) > QC_RANK_TOL)
    fit_rank_passes = int(k if rdiag_ok else 0)

    # normal-equations residuals for all K
    XT = Xn.T
    G_B   = (XT @ Xn) @ B
    XTy   = XT @ Y
    RES   = G_B - XTy
    lhs   = np.linalg.norm(RES, axis=0)
    rhs   = np.linalg.norm(XTy, axis=0) + 1e-12
    ls_passes = int(np.sum(lhs <= QC_LS_TOL * rhs))

    passed = (fit_rank_passes == k) and (ls_passes == k)
    stats = {
        "zero_var": 0,
        "rank": int(rank), "p": int(p),
        "s_min": float(s_min), "s_max": float(s_max), "kappa": float(kappa),
        "dup_pairs": 0,
        "max_vif": float(max_vif), "min_tolerance": float(min_tolerance),
        "tolerance_ok": bool(tolerance_ok), "corr_inv_exact": bool(inv_ok),
        "fit_rank_passes": int(fit_rank_passes),
        "ls_passes": int(ls_passes), "ls_total": int(k),
        "passed": bool(passed),
    }
    return passed, stats

def build_respondent_with_uniqueness(T: int,
                                     category_info: Dict[str, List[str]],
                                     E: int,
                                     A_min: int,
                                     base_seed: int,
                                     resp_index: int,
                                     study_mode: str,
                                     max_active_per_row: Optional[int]):
    """
    Build a single respondent, enforcing:
      • no duplicate columns
      • Professor Gate (rank, κ, K random-y) — LOOPS UNTIL PASS (infinite rebuild).
    This function never raises on QC/build failure; it keeps trying new RNG streams until success.
    """
    tries = 0
    last_status_print = 0
    while True:
        tries += 1
        rng_seed = base_seed + resp_index*7919 + tries*104729  # big prime stride
        rng = np.random.default_rng(rng_seed)

        rows = None
        try:
            rows = build_with_restarts_advanced(T, category_info, E, A_min, rng, study_mode, max_active_per_row)
        except Exception:
            rows = None

        if rows is None:
            if tries - last_status_print >= 20:
                print(f"  ↻ No feasible rows yet (tries={tries}). Continuing…")
                last_status_print = tries
            continue

        # Per-respondent uniqueness + QC gate
        X = one_hot_df_from_rows(rows, category_info)
        dup_pairs = per_respondent_duplicate_pairs(X)
        gate_ok, gate_stats = professor_gate(
            X,
            k=QC_RANDOM_Y_K,
            kappa_max=QC_KAPPA_MAX,
            rank_tol=QC_RANK_TOL,
            ls_tol=QC_LS_TOL,
            rng_seed=rng_seed + 17
        )

        enforce_dups_ok = (not PER_RESP_UNIQUE_COLS_ENFORCE) or (len(dup_pairs) == 0)
        all_ok = gate_ok and enforce_dups_ok

        if all_ok:
            max_r, pair = max_cross_category_correlation(X, category_info)
            report = {
                "zero_var": gate_stats.get("zero_var", 0),
                "dup_pairs": len(dup_pairs),
                "rank": gate_stats.get("rank", 0),
                "p": gate_stats.get("p", 0),
                "s_min": gate_stats.get("s_min", float("nan")),
                "s_max": gate_stats.get("s_max", float("nan")),
                "kappa": gate_stats.get("kappa", float("nan")),
                "max_vif": gate_stats.get("max_vif", float("nan")),
                "min_tolerance": gate_stats.get("min_tolerance", float("nan")),
                "tolerance_ok": gate_stats.get("tolerance_ok", True),
                "fit_rank_passes": gate_stats.get("fit_rank_passes", 0),
                "ls_passes": gate_stats.get("ls_passes", 0),
                "ls_total": gate_stats.get("ls_total", QC_RANDOM_Y_K),
                "max_abs_r": float(max_r),
                "max_r_pair": pair,
                "gate_passed": True,
            }
            if tries > 1:
                print(f"  ✓ Respondent passed QC after {tries} tries (κ={gate_stats['kappa']:.2g}).")
            else:
                print("  ✓ Respondent passed QC on first try.")
            return rows, X, report

        # Not OK—compact heartbeat every 20 tries
        if tries - last_status_print >= 20:
            kappa = gate_stats.get("kappa", float("inf"))
            print(
                f"  ⚠️ QC retry (tries={tries}): "
                f"dups={len(dup_pairs)}, gate={gate_ok}, "
                f"rank={gate_stats.get('rank','?')}/{gate_stats.get('p','?')}, "
                f"κ≈{kappa:.2g}, ls={gate_stats.get('ls_passes',0)}/{gate_stats.get('ls_total',QC_RANDOM_Y_K)}"
            )
            last_status_print = tries
        # Loop continues until pass

def preflight_lock_T(T: int,
                     category_info: Dict[str, List[str]],
                     E: int,
                     A_min_used: int,
                     study_mode: str,
                     max_active_per_row: Optional[int]) -> Tuple[int, Dict[str,int]]:
    rng = np.random.default_rng(BASE_SEED + 999_999)
    cap = visible_capacity(category_info,
                           MIN_ACTIVE_PER_ROW,
                           (max_active_per_row if study_mode == "grid" else None))

    def try_build(T_try: int) -> bool:
        for _ in range(GLOBAL_RESTARTS):
            if build_once_advanced(T_try, category_info, E, A_min_used, rng, study_mode, max_active_per_row) is not None:
                return True
        return False

    if try_build(T):
        A_map = {c: max(A_min_used, T - len(category_info[c]) * E) for c in category_info}
        return T, A_map

    for extra in range(1, 4):  # bump at most +3
        T2 = T + extra
        if T2 > cap:
            break
        if try_build(T2):
            A_map = {c: max(A_min_used, T2 - len(category_info[c]) * E) for c in category_info}
            return T2, A_map

    raise RuntimeError("Preflight failed even after a small global T bump; consider more elements/categories or adjust ABSENCE_RATIO/T_RATIO.")

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

# Advanced algorithm constants (from final_builder_parallel.py)
PER_ELEM_EXPOSURES = 3     # minimum exposures per element
MIN_ACTIVE_PER_ROW = 2     # min actives per vignette
SAFETY_ROWS = 3            # OLS safety above P
GLOBAL_RESTARTS = 200      # rebuild attempts per respondent
SWAP_TRIES = 8000          # swap tries per row
HARD_CAP_SWAP_TRIES = 30000  # extra attempts to enforce MAX_ACTIVE_PER_ROW hard cap
ABSENCE_RATIO = 2.0        # absences per category >= ceil(ABSENCE_RATIO * E)
ROW_MIX_MODE = "wide"      # "dense" or "wide" row-mix mode
ROW_MIX_WIDEN = 0.40       # fraction of rows to push to (base-1)
T_RATIO = 1.10             # scale rows/respondent above minimal feasible T
CAPACITY_SLACK = 1         # try to keep at least this many patterns un-used

def vignette_signature_pairs(cat_elem_pairs):
    """Canonical signature for per-respondent uniqueness (layout mode)."""
    return tuple(sorted(cat_elem_pairs, key=lambda x: x[0]))

def is_abs(val: str) -> bool:
    """Check if a value represents an absence."""
    return isinstance(val, str) and str(val).startswith("__ABS__")

def sig_pair(cat: str, val: str) -> Tuple[str, str]:
    """Create signature pair for category and value."""
    return (cat, "__ABS__") if is_abs(val) else (cat, str(val))

def params_main_effects(category_info: Dict[str, List[str]]) -> int:
    """Calculate number of main effects parameters."""
    C = len(category_info)
    M = sum(len(v) for v in category_info.values())
    return M - C + 1  # intercept + (n_c - 1) per category

def visible_capacity(category_info: Dict[str, List[str]], min_active: int, max_active: Optional[int] = None) -> int:
    """Calculate visible capacity for category combinations."""
    cats = list(category_info.keys())
    m = [len(category_info[c]) for c in cats]
    C = len(m)
    coeff = [0]*(C+1)
    coeff[0] = 1
    for mi in m:
        nxt = [0]*(C+1)
        for k in range(C+1):
            if coeff[k] == 0: continue
            nxt[k] += coeff[k]           # ABS choice
            if k+1 <= C: nxt[k+1] += coeff[k]*mi  # choose an element
        coeff = nxt
    hi = C if max_active is None else min(max_active, C)
    lo = max(min_active, 0)
    if lo > hi:
        return 0
    return sum(coeff[k] for k in range(lo, hi+1))

def plan_T_E_auto(category_info: Dict[str, List[str]], study_mode: str = "layout", max_active_per_row: Optional[int] = None) -> Tuple[int, int, Dict[str, int], float, int]:
    """Plan T and E automatically with advanced algorithm."""
    cats = list(category_info.keys())
    q = {c: len(category_info[c]) for c in cats}
    C = len(cats)
    M = sum(q.values())
    P = params_main_effects(category_info)
    cap = visible_capacity(category_info, MIN_ACTIVE_PER_ROW, max_active_per_row)

    # For small studies, use simpler approach
    if cap < 10:
        # Use the old auto_pick_t_for_layer approach for small studies
        T, _ = auto_pick_t_for_layer(category_info, baseline=12)
        E = max(1, T // M)  # Simple exposure calculation
        A_min_used = max(1, int(ABSENCE_RATIO * E))
        A_map = {c: max(A_min_used, T - q[c]*E) for c in cats}
        avg_k = (M * E) / T
        return T, E, A_map, avg_k, A_min_used

    # Start from identifiability floor and scale by T_RATIO
    T = max(P + SAFETY_ROWS, 2)
    if T_RATIO and T_RATIO > 1.0:
        T = int(math.ceil(T * float(T_RATIO)))

    # Helper: maximum feasible E at a given T
    def E_upper_at_T(T_try: int) -> int:
        # For each category c: T - q[c]*E >= ceil(ABSENCE_RATIO * E)
        bound_ratio = min(int(math.floor(T_try / (q[c] + ABSENCE_RATIO))) for c in cats)
        # Per-row active cap: total 1s = M*E <= T * rowcap
        rowcap = (max_active_per_row if (study_mode == "grid" and max_active_per_row is not None) else C)
        bound_rowcap = int(math.floor(T_try * rowcap / M))
        return min(bound_ratio, bound_rowcap)

    slack = CAPACITY_SLACK
    while True:
        if T > max(cap - slack, 0):
            if T > cap:
                # Fall back to simple approach for small studies
                T, _ = auto_pick_t_for_layer(category_info, baseline=12)
                E = max(1, T // M)
                A_min_used = max(1, int(ABSENCE_RATIO * E))
                A_map = {c: max(A_min_used, T - q[c]*E) for c in cats}
                avg_k = (M * E) / T
                return T, E, A_map, avg_k, A_min_used
            slack = 0
        E_up = E_upper_at_T(T)
        if E_up >= PER_ELEM_EXPOSURES:
            E = E_up
            break
        T += 1

    A_min_used = int(math.ceil(ABSENCE_RATIO * E))
    A_map = {c: T - q[c]*E for c in cats}  # by construction >= A_min_used
    avg_k = (M * E) / T
    return T, E, A_map, avg_k, A_min_used

def plan_row_mix(T: int, total_ones: int, min_k: int, max_k: int, mode: str = "wide", widen: float = 0.40) -> List[int]:
    """Plan row mix for variation in active categories per row."""
    if total_ones < T*min_k or total_ones > T*max_k:
        # For small studies, use simple uniform distribution
        if T <= 50:  # Increased threshold for small studies
            base = total_ones // T
            remainder = total_ones % T
            targets = [base] * T
            for i in range(remainder):
                targets[i] += 1
            return targets
        else:
            raise ValueError("total_ones not representable; adjust T/E.")
    
    if mode == "dense":
        k0 = min(max_k, max(min_k+1, 4))
        targets = [k0] * T
        deficit = total_ones - sum(targets)
        i = 0
        while deficit > 0:
            if targets[i] < max_k:
                step = min(max_k - targets[i], deficit)
                targets[i] += step
                deficit -= step
            i = (i + 1) % T
        i = 0
        while deficit < 0:
            if targets[i] > min_k:
                step = min(targets[i] - min_k, -deficit)
                targets[i] -= step
                deficit += step
            i = (i + 1) % T
        assert sum(targets) == total_ones
        return targets

    # wide mode
    base = total_ones // T
    deficit = total_ones - base*T
    base = max(min_k, min(max_k, base))
    targets = [base] * T
    down_cap = T if (base - 1) >= min_k else 0
    pair_count = min(max(0, int(round(widen * T))), down_cap, T)

    # push some rows to base-1
    idx = 0
    down_done = 0
    while down_done < pair_count and idx < T:
        if targets[idx] - 1 >= min_k:
            targets[idx] -= 1
            down_done += 1
        idx += 1

    # balance with +1s: one per downshift plus the global deficit
    up_needed = pair_count + deficit
    idx = 0
    up_done = 0
    while up_done < up_needed and idx < T:
        if targets[idx] + 1 <= max_k:
            targets[idx] += 1
            up_done += 1
        idx += 1
    if up_done < up_needed:
        for i in range(T):
            if up_done >= up_needed: break
            if targets[i] + 1 <= max_k:
                targets[i] += 1
                up_done += 1

    assert sum(targets) == total_ones, "Row-mix sum mismatch; adjust widen or constraints."
    assert all(min_k <= k <= max_k for k in targets), "Row-mix bounds violated."
    return targets

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

def build_once_advanced(T: int, category_info: Dict[str, List[str]], E: int, A_min: int, rng: np.random.Generator, study_mode: str = "layout", max_active_per_row: Optional[int] = None) -> Optional[List[Dict[str, str]]]:
    """
    Build rows with exact exposures/absences using advanced algorithm.
    Returns rows or None.
    """
    cats = list(category_info.keys())
    M = sum(len(category_info[c]) for c in cats)
    total_ones = M * E

    # Build token pools with EXACT exposures and required ABS (derived from T & E)
    pools: Dict[str, List[str]] = {}
    for c in cats:
        elems = category_info[c]
        tokens = []
        for e in elems:
            tokens.extend([e] * E)
        abs_count = T - E * len(elems)
        if abs_count < A_min:
            return None
        tokens.extend([f"__ABS__{c}"] * int(abs_count))
        if len(tokens) != T:
            return None
        rng.shuffle(tokens)
        pools[c] = tokens

    # Target actives per row
    allowed_max = (max_active_per_row if (study_mode == "grid" and max_active_per_row is not None) else len(cats))
    targets = plan_row_mix(
        T, total_ones, MIN_ACTIVE_PER_ROW, allowed_max,
        mode=ROW_MIX_MODE, widen=ROW_MIX_WIDEN
    )

    # Assemble rows by aligned index
    rows = [{c: pools[c][t] for c in cats} for t in range(T)]

    def active_count(rr: int) -> int:
        return sum(1 for c in cats if not is_abs(rows[rr][c]))
    
    def vis_sig(rr: int) -> Tuple[Tuple[str, str], ...]:
        return tuple(sig_pair(c, rows[rr][c]) for c in cats)

    seen: Counter = Counter()
    sig_of: Dict[int, Tuple[Tuple[str,str], ...]] = {}

    # Phase 1: build with uniqueness and bounds
    for r in range(T):
        s_r = vis_sig(r)
        within_cap = (active_count(r) <= allowed_max)
        ok = (MIN_ACTIVE_PER_ROW <= active_count(r) and within_cap and seen[s_r] == 0)
        if ok:
            seen[s_r] += 1
            sig_of[r] = s_r
        else:
            best = None
            best_gain = -10**9
            for _ in range(SWAP_TRIES):
                rc = int(rng.integers(0, r+1))
                c = rng.choice(cats)

                rows[r][c], rows[rc][c] = rows[rc][c], rows[r][c]
                new_r_sig = vis_sig(r)
                new_rc_sig = vis_sig(rc) if rc < r else None

                valid = True
                # enforce bounds at both rows
                if active_count(r) < MIN_ACTIVE_PER_ROW or active_count(r) > allowed_max: valid = False
                if rc < r and (active_count(rc) < MIN_ACTIVE_PER_ROW or active_count(rc) > allowed_max): valid = False

                if valid:
                    if new_r_sig != s_r and seen.get(new_r_sig, 0) > 0: valid = False
                    if valid and rc < r:
                        old_rc_sig = sig_of[rc]
                        if new_rc_sig != old_rc_sig and seen.get(new_rc_sig, 0) > 0: valid = False

                if valid:
                    gain = -abs(active_count(r) - targets[r])
                    if rc < r:
                        gain += -abs(active_count(rc) - targets[rc])
                    if gain > best_gain:
                        best_gain = gain
                        best = (rc, c, new_r_sig, new_rc_sig)

                rows[r][c], rows[rc][c] = rows[rc][c], rows[r][c]  # rollback

            if best is None:
                return None
            rc, c, new_r_sig, new_rc_sig = best
            rows[r][c], rows[rc][c] = rows[rc][c], rows[r][c]
            if s_r in seen:
                seen[s_r] -= 1
                if seen[s_r] <= 0: del seen[s_r]
            seen[new_r_sig] = seen.get(new_r_sig, 0) + 1
            sig_of[r] = new_r_sig
            if rc < r:
                old_rc_sig = sig_of[rc]
                if old_rc_sig in seen:
                    seen[old_rc_sig] -= 1
                    if seen[old_rc_sig] <= 0: del seen[old_rc_sig]
                seen[new_rc_sig] = seen.get(new_rc_sig, 0) + 1
                sig_of[rc] = new_rc_sig

    # Phase 2: Hard-cap enforcement (grid only)
    if study_mode == "grid":
        over_idx = [i for i in range(T) if active_count(i) > allowed_max]
        under_ok_idx = [i for i in range(T) if active_count(i) < allowed_max]

        tries = 0
        while over_idx and tries < HARD_CAP_SWAP_TRIES:
            tries += 1
            r = over_idx[tries % len(over_idx)]
            act_cats = [c for c in cats if not is_abs(rows[r][c])]
            if not act_cats:
                over_idx = [i for i in range(T) if active_count(i) > allowed_max]
                continue
            c = act_cats[tries % len(act_cats)]

            # prefer rows with absence in c and currently under the cap
            candidates = [i for i in under_ok_idx if is_abs(rows[i][c])]
            if not candidates:
                candidates = [i for i in range(T) if i != r and is_abs(rows[i][c])]
            found = False
            for s in candidates:
                if s == r: continue
                rows[r][c], rows[s][c] = rows[s][c], rows[r][c]
                if (MIN_ACTIVE_PER_ROW <= active_count(r) <= allowed_max) and (MIN_ACTIVE_PER_ROW <= active_count(s) <= allowed_max):
                    found = True
                    break
                rows[r][c], rows[s][c] = rows[s][c], rows[r][c]

            over_idx = [i for i in range(T) if active_count(i) > allowed_max]
            under_ok_idx = [i for i in range(T) if active_count(i) < allowed_max]

        if over_idx:
            return None  # fail this attempt; caller will restart

    # Final checks
    sigs = [vis_sig(i) for i in range(T)]
    if len(set(sigs)) != T:
        return None
    if any(active_count(i) < MIN_ACTIVE_PER_ROW for i in range(T)):
        return None
    if study_mode == "grid" and any(active_count(i) > allowed_max for i in range(T)):
        return None
    return rows

def build_with_restarts_advanced(T: int, category_info: Dict[str, List[str]], E: int, A_min: int, rng: np.random.Generator, study_mode: str = "layout", max_active_per_row: Optional[int] = None) -> Optional[List[Dict[str, str]]]:
    """Fixed-T builder with heavy retries. Returns rows or None."""
    for attempt in range(1, GLOBAL_RESTARTS+1):
        rows = build_once_advanced(T, category_info, E, A_min, rng, study_mode, max_active_per_row)
        if rows is not None:
            return rows
    return None

def generate_layer_mode_advanced(num_consumers: int, category_info: Dict[str, List[str]], seed: Optional[int] = None) -> Tuple[pd.DataFrame, np.ndarray, Dict]:
    """
    Generate layer mode using advanced algorithm from final_builder_parallel.py.
    Falls back to original algorithm for small studies.
    Returns design_df, Ks, metadata.
    """
    # Check if this is a small study that should use the original algorithm
    total_elements = sum(len(elems) for elems in category_info.values())
    if total_elements <= 5:  # Only use original for very small studies
        # Use original algorithm for small studies
        tasks_per_consumer, capacity = auto_pick_t_for_layer(category_info, baseline=12)
        design_df, Ks, _ = generate_layer_mode(
            num_consumers=num_consumers,
            tasks_per_consumer=tasks_per_consumer,
            category_info=category_info,
            tol_pct=0.02
        )
        metadata = {
            "T": tasks_per_consumer,
            "E": 1,  # Simple exposure for small studies
            "A_map": {},
            "avg_k": len(category_info),
            "A_min_used": 0,
            "study_mode": "layout",
            "algorithm": "original"
        }
        return design_df, Ks, metadata
    
    # Set up RNG
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()
    
    # Plan T and E automatically
    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(category_info, study_mode="layout")
    
    # Build design for each respondent
    all_rows = []
    cats = list(category_info.keys())
    all_elements = [e for es in category_info.values() for e in es]
    
    for respondent_id in range(num_consumers):
        # Build rows for this respondent
        rows = build_with_restarts_advanced(T, category_info, E, A_min_used, rng, study_mode="layout")
        if rows is None:
            # Fall back to original algorithm if advanced fails
            tasks_per_consumer, capacity = auto_pick_t_for_layer(category_info, baseline=12)
            design_df, Ks, _ = generate_layer_mode(
                num_consumers=num_consumers,
                tasks_per_consumer=tasks_per_consumer,
                category_info=category_info,
                tol_pct=0.02
            )
            metadata = {
                "T": tasks_per_consumer,
                "E": 1,
                "A_map": {},
                "avg_k": len(category_info),
                "A_min_used": 0,
                "study_mode": "layout",
                "algorithm": "original_fallback"
            }
            return design_df, Ks, metadata
        
        # Convert to design matrix format
        for row in rows:
            design_row = {"Consumer ID": f"C{respondent_id + 1}"}
            for element in all_elements:
                # Find which category this element belongs to
                element_category = None
                for cat, elems in category_info.items():
                    if element in elems:
                        element_category = cat
                        break
                
                if element_category and not is_abs(row[element_category]) and row[element_category] == element:
                    design_row[element] = 1
                else:
                    design_row[element] = 0
            
            all_rows.append(design_row)
    
    # Create DataFrame
    design_df = pd.DataFrame(all_rows)
    
    # K is exactly the number of categories active per vignette (all categories for layout mode)
    Ks = np.full(len(design_df), len(cats), dtype=int)
    
    # Metadata
    metadata = {
        "T": T,
        "E": E,
        "A_map": A_map,
        "avg_k": avg_k,
        "A_min_used": A_min_used,
        "study_mode": "layout",
        "algorithm": "advanced"
    }
    
    return design_df, Ks, metadata

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

def generate_grid_tasks_v2(categories_data: List[Dict], number_of_respondents: int, 
                          exposure_tolerance_cv: float = 1.0, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate tasks for grid studies using the advanced algorithm with category-based structure.
    
    Args:
        categories_data: List of category dictionaries with elements
        number_of_respondents: Number of respondents (N)
        exposure_tolerance_cv: Exposure tolerance as coefficient of variation percentage
        seed: Random seed for reproducibility
    
    Returns:
        Dictionary containing task matrix and metadata
    """
    # Set seed if provided
    if seed is not None:
        set_seed(seed)
    
    # Convert categories_data to category_info format for the advanced algorithm
    category_info = {}
    all_elements = []
    
    for i, category in enumerate(categories_data):
        category_name = category.get('category_name', f'Category_{i+1}')
        elements = category.get('elements', [])
        
        # Create element names for this category
        element_names = []
        for j, element in enumerate(elements):
            element_name = f"{category_name}_{j+1}"
            element_names.append(element_name)
            all_elements.append({
                'name': element_name,
                'category': category_name,
                'element_data': element
            })
        
        category_info[category_name] = element_names
    
    # Calculate total elements
    total_elements = len(all_elements)
    
    # Use main function logic from final_builder_parallel.py
    # Extract variables for main function
    C = len(category_info)  # Number of categories
    N = number_of_respondents  # Number of respondents
    
    # Use grid mode for grid studies
    mode = "grid"
    max_active_per_row = 4  # Grid studies have max 4 active categories per row
    
    # Set global seed if provided
    if seed is not None:
        global BASE_SEED
        BASE_SEED = seed
    
    # Plan automatically (ratio-aware absence + T_RATIO)
    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(category_info, mode, max_active_per_row)
    
    # Set logging cadence: one progress line per respondent
    global LOG_EVERY_ROWS
    LOG_EVERY_ROWS = max(T, 25)
    
    # Preflight lock T, but do not abort if it can't lock.
    try:
        T, A_map = preflight_lock_T(T, category_info, E, A_min_used, mode, max_active_per_row)
    except RuntimeError as e:
        print(f"⚠️ Preflight could not lock T ({e}). Proceeding with T={T} in rebuild-until-pass mode.")
        A_map = {c: max(A_min_used, T - len(category_info[c]) * E) for c in category_info}
    
    # Recompute avg_k in case T was bumped
    M = sum(len(category_info[c]) for c in category_info)
    avg_k = (M * E) / T
    
    # Build each respondent with **per-respondent unique columns** + **Professor Gate**
    all_rows_per_resp = []
    per_resp_reports: Dict[int, dict] = {}
    
    # Build respondents concurrently using ProcessPoolExecutor (same as final_builder_parallel.py)
    
    # Set up multiprocessing
    max_workers = min(os.cpu_count() or 1, N)
    
    try:
        mp.set_start_method("spawn")
    except RuntimeError:
        pass  # already set
    
    print(f"🚀 Building {N} respondents concurrently with {max_workers} workers...")
    
    # Prepare tasks for parallel execution
    tasks = []
    for r in range(1, N+1):
        tasks.append((r, T, category_info, E, A_min_used, BASE_SEED, LOG_EVERY_ROWS,
                      mode, max_active_per_row))
    
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_build_one_worker, t): t[0] for t in tasks}
        done = 0
        for fut in as_completed(futures):
            resp_id = futures[fut]
            try:
                rid, rows, X, report = fut.result()
            except Exception as e:
                raise RuntimeError(f"Worker for respondent {resp_id} failed") from e
            
            per_resp_reports[rid] = report
            all_rows_per_resp.append((rid, rows))
            done += 1
            if done % 5 == 0 or done == N:
                print(f"  • Completed {done}/{N} respondents")
    
    # Sort by respondent ID to maintain order
    all_rows_per_resp.sort(key=lambda t: t[0])
    
    # Convert to design matrix format
    design_df = one_hot_df_from_rows(all_rows_per_resp[0][1], category_info)
    for resp_id, rows in all_rows_per_resp[1:]:
        resp_df = one_hot_df_from_rows(rows, category_info)
        design_df = pd.concat([design_df, resp_df], ignore_index=True)
    
    # Add Consumer_ID column
    consumer_ids = []
    for resp_id, rows in all_rows_per_resp:
        consumer_ids.extend([resp_id] * len(rows))
    design_df['Consumer_ID'] = consumer_ids
    
    # Extract tasks_per_consumer from the generated design
    # Use N (over-generated respondents) to compute per-consumer task count
    tasks_per_consumer = max(1, len(design_df) // N)
    capacity = len(design_df)
    
    # Convert to task structure with element content
    tasks_structure = {}
    
    for respondent_id in range(N):
        respondent_tasks = []
        start_idx = respondent_id * tasks_per_consumer
        end_idx = start_idx + tasks_per_consumer
        
        # Get tasks for this specific respondent
        respondent_data = design_df.iloc[start_idx:end_idx]
        
        for task_index, (_, task_row) in enumerate(respondent_data.iterrows()):
            # Create elements_shown dictionary
            elements_shown = {}
            elements_shown_content = {}
            
            for element_info in all_elements:
                element_name = element_info['name']
                element_data = element_info['element_data']
                
                # Element is only shown if it's active in this task
                element_active = int(task_row[element_name])
                elements_shown[element_name] = element_active
                
                # Find the corresponding content for this element
                if element_active:
                    elements_shown_content[element_name] = {
                        'url': element_data.get('content', ''),
                        'name': element_data.get('name', ''),
                        'alt_text': element_data.get('alt_text', ''),
                        'category_name': element_info['category'],
                        'element_type': element_data.get('element_type', 'image')
                    }
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
            'study_type': 'grid_v2',
            'categories_data': categories_data,
            'category_info': category_info,
            'tasks_per_consumer': tasks_per_consumer,
            'number_of_respondents': number_of_respondents,
            'exposure_tolerance_cv': exposure_tolerance_cv,
            'capacity': capacity,
            'algorithm': 'advanced_parallel',
            'study_mode': mode,
            'max_active_per_row': max_active_per_row
        }
    }

def generate_grid_tasks(num_elements: int, tasks_per_consumer: int, number_of_respondents: int, 
                       exposure_tolerance_cv: float = 1.0, seed: Optional[int] = None, 
                       elements: Optional[List] = None) -> Dict[str, Any]:
    """
    Legacy function for grid studies - kept for backward compatibility.
    Use generate_grid_tasks_v2 for new category-based structure.
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
    Generate tasks for the new layer structure using advanced algorithms from final_builder_parallel.py.
    
    Args:
        layers_data: List of layer objects with images
        number_of_respondents: Number of respondents (N)
        exposure_tolerance_pct: Exposure tolerance as percentage (legacy parameter, not used in new algorithm)
        seed: Random seed for reproducibility
    
    Returns:
        Dictionary containing task matrix and metadata
    """
    print(f"🚀 Starting layer task generation for {number_of_respondents} respondents...")
    start_time = time.time()
    print(f"⏰ Start time: {time.strftime('%H:%M:%S', time.localtime(start_time))}")
    
    # Set seed if provided
    if seed is not None:
        set_seed(seed)
    
    # Convert layers data to category_info format
    category_info = {}
    for layer in layers_data:
        layer_name = layer['name']
        # Create element names for this layer (e.g., "Background_1", "Background_2")
        elements = [f"{layer_name}_{i+1}" for i in range(len(layer['images']))]
        category_info[layer_name] = elements
    
    # Use main function logic from final_builder_parallel.py
    # Extract variables for main function
    C = len(category_info)  # Number of categories
    # Generate 5x respondents for buffer
    N = number_of_respondents * 5
    
    # Use layout mode for layer studies
    mode = "layout"
    max_active_per_row = C  # In layout mode, allow up to the # of categories
    
    # Set global seed if provided
    if seed is not None:
        global BASE_SEED
        BASE_SEED = seed
    
    # Plan automatically (ratio-aware absence + T_RATIO)
    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(category_info, mode, max_active_per_row)
    
    # Set logging cadence: one progress line per respondent
    global LOG_EVERY_ROWS
    LOG_EVERY_ROWS = max(T, 25)
    
    # Preflight lock T, but do not abort if it can't lock.
    try:
        T, A_map = preflight_lock_T(T, category_info, E, A_min_used, mode, max_active_per_row)
    except RuntimeError as e:
        print(f"⚠️ Preflight could not lock T ({e}). Proceeding with T={T} in rebuild-until-pass mode.")
        A_map = {c: max(A_min_used, T - len(category_info[c]) * E) for c in category_info}
    
    # Recompute avg_k in case T was bumped
    M = sum(len(category_info[c]) for c in category_info)
    avg_k = (M * E) / T
    
    # Build each respondent with **per-respondent unique columns** + **Professor Gate**
    all_rows_per_resp = []
    per_resp_reports: Dict[int, dict] = {}
    
    # Build respondents concurrently using ProcessPoolExecutor (same as final_builder_parallel.py)
    
    # Set up multiprocessing
    max_workers = min(os.cpu_count() or 1, N)
    
    try:
        mp.set_start_method("spawn")
    except RuntimeError:
        pass  # already set
    
    print(f"🚀 Building {N} respondents concurrently with {max_workers} workers...")
    
    # Prepare tasks for parallel execution
    tasks = []
    for r in range(1, N+1):
        tasks.append((r, T, category_info, E, A_min_used, BASE_SEED, LOG_EVERY_ROWS,
                      mode, max_active_per_row))
    
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_build_one_worker, t): t[0] for t in tasks}
        done = 0
        for fut in as_completed(futures):
            resp_id = futures[fut]
            try:
                rid, rows, X, report = fut.result()
            except Exception as e:
                raise RuntimeError(f"Worker for respondent {resp_id} failed") from e
            
            per_resp_reports[rid] = report
            all_rows_per_resp.append((rid, rows))
            done += 1
            if done % 5 == 0 or done == N:
                print(f"  • Completed {done}/{N} respondents")
    
    # Sort by respondent ID to maintain order
    all_rows_per_resp.sort(key=lambda t: t[0])
    
    # Convert to design matrix format
    design_df = one_hot_df_from_rows(all_rows_per_resp[0][1], category_info)
    for resp_id, rows in all_rows_per_resp[1:]:
        resp_df = one_hot_df_from_rows(rows, category_info)
        design_df = pd.concat([design_df, resp_df], ignore_index=True)
    
    # Add Consumer_ID column
    consumer_ids = []
    for resp_id, rows in all_rows_per_resp:
        consumer_ids.extend([resp_id] * len(rows))
    design_df['Consumer_ID'] = consumer_ids
    
    # Extract tasks_per_consumer from the generated design using over-generated N
    tasks_per_consumer = max(1, len(design_df) // N)
    capacity = len(design_df)
    
    # Convert to task structure with image content
    tasks_structure = {}
    all_elements = [e for es in category_info.values() for e in es]
    
    for respondent_id in range(N):
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
    
    end_time = time.time()
    total_duration = end_time - start_time
    end_time_str = time.strftime('%H:%M:%S', time.localtime(end_time))
    print(f"✅ Layer task generation completed at {end_time_str}")
    print(f"⏱️ Total duration: {total_duration:.2f} seconds")
    print(f"📊 Performance: {number_of_respondents} respondents in {total_duration:.2f}s = {number_of_respondents/total_duration:.2f} respondents/second")
    
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

def generate_grid_tasks_v2(categories_data: List[Dict], number_of_respondents: int, 
                          exposure_tolerance_cv: float = 1.0, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate tasks for grid studies using EXACT logic from final_builder_parallel.py main function.
    
    Args:
        categories_data: List of category objects with elements
        number_of_respondents: Number of respondents (N)
        exposure_tolerance_cv: Exposure tolerance coefficient of variation
        seed: Random seed for reproducibility
    
    Returns:
        Dictionary containing task matrix and metadata
    """
    print(f"🚀 Starting grid task generation for {number_of_respondents} respondents...")
    start_time = time.time()
    print(f"⏰ Start time: {time.strftime('%H:%M:%S', time.localtime(start_time))}")
    
    # Set seed if provided
    if seed is not None:
        global BASE_SEED
        BASE_SEED = seed
    
    # Convert categories_data to category_info format (EXACT same as main function)
    category_info: Dict[str, List[str]] = {}
    for category in categories_data:
        category_name = category['category_name']
        category_info[category_name] = [f"{category_name}_{j+1}" for j in range(len(category['elements']))]
    
    # EXACT same logic as main function in final_builder_parallel.py
    C = len(category_info)
    # Generate 5x respondents for buffer
    N = number_of_respondents * 5
    
    # --- Study mode & per-row active cap --- (EXACT same as main function)
    mode = "grid"  # Grid mode
    max_active_per_row = min(GRID_MAX_ACTIVE, C)  # EXACT same logic
    
    # Sanity: cap must not be below the minimum actives rule (EXACT same as main function)
    if max_active_per_row < MIN_ACTIVE_PER_ROW:
        raise ValueError(
            f"MAX_ACTIVE_PER_ROW ({max_active_per_row}) < MIN_ACTIVE_PER_ROW ({MIN_ACTIVE_PER_ROW}). "
            "Increase categories or relax settings."
        )
    
    # Plan automatically (ratio-aware absence + T_RATIO) (EXACT same as main function)
    planning_start = time.time()
    print(f"📊 Starting planning phase at {time.strftime('%H:%M:%S', time.localtime(planning_start))}")
    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(category_info, mode, max_active_per_row)
    planning_duration = time.time() - planning_start
    print(f"⏱️ Planning completed in {planning_duration:.2f} seconds")
    
    # Set logging cadence: one progress line per respondent (EXACT same as main function)
    global LOG_EVERY_ROWS
    LOG_EVERY_ROWS = max(T, 25)
    
    # Preflight lock T, but do not abort if it can't lock. (EXACT same as main function)
    preflight_start = time.time()
    print(f"🔒 Starting preflight lock at {time.strftime('%H:%M:%S', time.localtime(preflight_start))}")
    try:
        T, A_map = preflight_lock_T(T, category_info, E, A_min_used, mode, max_active_per_row)
        preflight_duration = time.time() - preflight_start
        print(f"✅ Preflight lock successful in {preflight_duration:.2f} seconds")
    except RuntimeError as e:
        preflight_duration = time.time() - preflight_start
        print(f"⚠️ Preflight could not lock T ({e}) after {preflight_duration:.2f} seconds. Proceeding with T={T} in rebuild-until-pass mode.")
        A_map = {c: max(A_min_used, T - len(category_info[c]) * E) for c in category_info}
    
    # Recompute avg_k in case T was bumped (EXACT same as main function)
    M = sum(len(category_info[c]) for c in category_info)
    avg_k = (M * E) / T
    
    print(f"\n[Plan] FINAL T={T}, E={E}, avg actives ≈ {avg_k:.2f} (ABSENCE_RATIO={ABSENCE_RATIO}, A_min used = {A_min_used}, T_RATIO={T_RATIO})")
    print(f"[Plan] Row-mix mode: {ROW_MIX_MODE}, widen={ROW_MIX_WIDEN}")
    print("[Plan] Absences per category:", ", ".join([f"{c}:{A_map[c]}" for c in category_info]))
    
    # Build each respondent with **per-respondent unique columns** + **Professor Gate** (EXACT same as main function)
    all_rows_per_resp = []
    per_resp_reports: Dict[int, dict] = {}
    
    # --------- PARALLEL BY RESPONDENT ---------- (EXACT same as main function)
    max_workers = min(os.cpu_count() or 1, N)
    print(f"👥 Using {max_workers} workers for parallel processing")
    
    parallel_start = time.time()
    print(f"🔄 Starting parallel processing at {time.strftime('%H:%M:%S', time.localtime(parallel_start))}")
    
    try:
        mp.set_start_method("spawn")
    except RuntimeError:
        pass  # already set
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks (EXACT same as main function)
        futures = []
        for resp_id in range(N):
            future = executor.submit(_build_one_worker, (
                resp_id, T, category_info, E, A_min_used, BASE_SEED, LOG_EVERY_ROWS,
                mode, max_active_per_row
            ))
            futures.append((resp_id, future))
        
        # Collect results as they complete (EXACT same as main function)
        completed_count = 0
        # Create a mapping from Future to resp_id
        future_to_resp_id = {future: resp_id for resp_id, future in futures}
        
        for future in as_completed([f[1] for f in futures]):
            try:
                resp_id, rows, X_df, report = future.result()
                all_rows_per_resp.append((resp_id, rows))
                per_resp_reports[resp_id] = report
                completed_count += 1
                current_time = time.strftime('%H:%M:%S', time.localtime())
                print(f"✅ Built respondent {resp_id+1}/{N} at {current_time} ({completed_count}/{N} completed)")
            except Exception as e:
                completed_count += 1
                current_time = time.strftime('%H:%M:%S', time.localtime())
                print(f"❌ Failed to build respondent {resp_id+1} at {current_time}: {e}")
                per_resp_reports[resp_id] = {'status': 'failed', 'error': str(e)}
    
    parallel_duration = time.time() - parallel_start
    print(f"⏱️ Parallel processing completed in {parallel_duration:.2f} seconds")
    
    # Sort results by respondent ID (EXACT same as main function)
    all_rows_per_resp.sort(key=lambda t: t[0])
    
    # Convert to design matrix format (EXACT same as main function)
    if all_rows_per_resp:
        design_df = one_hot_df_from_rows(all_rows_per_resp[0][1], category_info)
        for resp_id, rows in all_rows_per_resp[1:]:
            resp_df = one_hot_df_from_rows(rows, category_info)
            design_df = pd.concat([design_df, resp_df], ignore_index=True)
        
        # Add Consumer_ID column (EXACT same as main function)
        consumer_ids = []
        for resp_id, rows in all_rows_per_resp:
            consumer_ids.extend([resp_id] * len(rows))
        design_df['Consumer_ID'] = consumer_ids
        
        # Extract tasks_per_consumer from the generated design
        tasks_per_consumer = max(1, len(design_df) // N)
        capacity = len(design_df)
        
        # Convert to task structure with image content (GRID SPECIFIC OUTPUT FORMAT)
        tasks_structure = {}
        all_elements = [e for es in category_info.values() for e in es]
        
        # Build tasks for all over-generated respondents (5x)
        for respondent_id in range(N):
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
                        # Parse element name to find category and element index
                        # Format: "CategoryName_ElementIndex" (e.g., "Category1_1")
                        if '_' in element_name:
                            category_name, elem_index_str = element_name.rsplit('_', 1)
                            try:
                                elem_index = int(elem_index_str) - 1  # Convert to 0-based index
                                
                                # Find the category and element
                                for category in categories_data:
                                    if category['category_name'] == category_name and elem_index < len(category['elements']):
                                        element = category['elements'][elem_index]
                                        elements_shown_content[element_name] = {
                                            'element_id': element['element_id'],
                                            'name': element['name'],
                                            'content': element['content'],
                                            'alt_text': element.get('alt_text', element['name']),
                                            'element_type': element['element_type'],
                                            'category_name': category_name
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
        
        end_time = time.time()
        total_duration = end_time - start_time
        end_time_str = time.strftime('%H:%M:%S', time.localtime(end_time))
        print(f"✅ Grid task generation completed at {end_time_str}")
        print(f"⏱️ Total duration: {total_duration:.2f} seconds")
        print(f"📊 Performance: {number_of_respondents} respondents in {total_duration:.2f}s = {number_of_respondents/total_duration:.2f} respondents/second")
        
        return {
            'tasks': tasks_structure,
            'metadata': {
                'study_type': 'grid_v2',
                'categories_data': categories_data,
                'category_info': category_info,
                'tasks_per_consumer': tasks_per_consumer,
                'number_of_respondents': number_of_respondents,
                'exposure_tolerance_cv': exposure_tolerance_cv,
                'capacity': capacity,
                'algorithm': 'final_builder_parallel_exact'
            }
        }
    else:
        raise RuntimeError("Failed to generate any valid designs")

def generate_grid_tasks_simple(categories_data: List[Dict], number_of_respondents: int, 
                              exposure_tolerance_cv: float = 1.0, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Simple fallback task generation for grid studies.
    """
    print("🔄 Using simple task generation approach...")
    
    # Set seed if provided
    if seed is not None:
        set_seed(seed)
    
    # Convert categories_data to category_info format
    category_info = {}
    for category in categories_data:
        category_name = category['category_name']
        elements = [f"{category_name}_{i+1}" for i in range(len(category['elements']))]
        category_info[category_name] = elements
    
    # Simple approach: use the legacy generate_grid_tasks function
    return generate_grid_tasks_legacy(category_info, number_of_respondents, exposure_tolerance_cv, seed)
