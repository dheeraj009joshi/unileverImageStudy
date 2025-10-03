#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto Conjoint Vignette Builder — minimal prompts, fully automatic planning
Prompts ONLY for: project name, categories/elements, number of respondents.

Automatic guarantees (per respondent):
- Equal exposure per element (E chosen automatically, E >= PER_ELEM_EXPOSURES)
- Each vignette has >= MIN_ACTIVE_PER_ROW active categories (default 2)
- Each category has absences >= ceil(ABSENCE_RATIO * E)  (ratio-aware)
- Rows are unique within respondent
- ≤1 active per category per row
- Main-effects OLS identifiability (T >= P + SAFETY_ROWS), with reference coding
- **Per-respondent design matrix has NO duplicate columns (strictly enforced)**
- **Per-respondent passes "Professor Gate": full rank, κ(X) ≤ KAPPA_MAX, and K random-y OLS runs (no intercept)**

Robustness:
- Planner avoids building exactly at visible-capacity (keeps 1-row slack if possible)
- Brute-force builder with large restarts/swaps
- GLOBAL T LOCK: one preflight may bump T (up to +3) BEFORE any respondent is built.
  T NEVER CHANGES per respondent.

Extras:
- Row-mix "widen" to increase variation in #actives per row
- Optional T_RATIO knob to scale rows/respondent above the minimum feasible T
- Per-respondent collinearity diagnostics: zero-variance, duplicate columns, max cross-cat |r|
- **QC Certificate emitted (no raw rows required by professor)**
"""

from __future__ import annotations
import os, re, time, math, hashlib
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from collections import Counter

# --- parallel helpers ---
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

# Prevent BLAS over-subscription inside each worker
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

# ------------------------
# Global knobs (constants)
# ------------------------
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

# Optional "don’t think, just pick a ratio" knob for T
T_RATIO            = 1.10     # scale rows/respondent above minimal feasible T

# Per-respondent safety: enforce **no duplicate columns** in each person’s design matrix
PER_RESP_UNIQUE_COLS_ENFORCE = True

# Planner preferences
CAPACITY_SLACK     = 1       # try to keep at least this many patterns un-used (avoid T==cap)

# ------------------------
# Professor gate (QC) knobs
# ------------------------
QC_RANDOM_Y_K      = 5       # number of random dependent variables per respondent
QC_KAPPA_MAX       = 1e6     # condition number upper bound (tight)
QC_RANK_TOL        = 1e-12   # singular value cutoff for rank
QC_LS_TOL          = 1e-6    # tolerance on normal equations residual
VIF_TOL_MIN        = 1e-6    # per-column tolerance = 1 / max(VIF) threshold

GEN_VERSION        = "v1.4-prof-gate"  # generator ID string

# ------------------------
# Helpers
# ------------------------
def _prompt_int(msg: str, min_val: int = None, default: int | None = None) -> int:
    while True:
        s = input(f"{msg}" + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not s and default is not None: return default
        try:
            v = int(s)
        except Exception:
            print("Please enter an integer."); continue
        if min_val is not None and v < min_val:
            print(f"Please enter a value ≥ {min_val}."); continue
        return v

def _prompt_str(msg: str, default: str | None = None) -> str:
    s = input(f"{msg}" + (f" [{default}]" if default is not None else "") + ": ").strip()
    return (default if (not s and default is not None) else s)

def _sanitize(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9._-]+", "", s)
    return s or "project"

def _ensure_dir(path: str) -> str:
    abs_path = os.path.abspath(path); os.makedirs(abs_path, exist_ok=True); return abs_path

def is_abs(val: str) -> bool:
    return isinstance(val, str) and str(val).startswith("__ABS__")

def sig_pair(cat: str, val: str) -> Tuple[str, str]:
    return (cat, "__ABS__") if is_abs(val) else (cat, str(val))

def params_main_effects(category_info: Dict[str, List[str]]) -> int:
    C = len(category_info)
    M = sum(len(v) for v in category_info.values())
    return M - C + 1  # intercept + (n_c - 1) per category

# ------------------------
# Visible capacity (optionally capped by max actives/row)
# ------------------------
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

# ------------------------
# Ratio-aware planner with optional T_RATIO and capped capacity
# ------------------------
def plan_T_E_auto(category_info: Dict[str, List[str]],
                  study_mode: str,
                  max_active_per_row: int | None) -> Tuple[int,int,Dict[str,int],float,int]:
    cats = list(category_info.keys())
    q = {c: len(category_info[c]) for c in cats}
    C = len(cats)
    M = sum(q.values())
    P = params_main_effects(category_info)
    cap = visible_capacity(
        category_info,
        MIN_ACTIVE_PER_ROW,
        (max_active_per_row if study_mode == "grid" else None)
    )

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
                raise RuntimeError("Infeasible: T exceeds visible capacity. Add elements/categories or relax ABSENCE_RATIO/T_RATIO.")
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

# ------------------------
# Row-mix planner (adds variation in # of actives per row)
# ------------------------
def plan_row_mix(T: int, total_ones: int, min_k: int, max_k: int,
                 mode: str = "dense", widen: float = 0.10) -> List[int]:
    if total_ones < T*min_k or total_ones > T*max_k:
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

# ------------------------
# Builders
# ------------------------
def build_once(T: int,
               category_info: Dict[str, List[str]],
               E: int,
               A_min: int,
               rng: np.random.Generator,
               study_mode: str,
               max_active_per_row: Optional[int]) -> Optional[List[Dict[str, str]]]:
    """
    Build rows with exact exposures/absences, respecting:
      - Uniqueness of visible rows within respondent
      - MIN_ACTIVE_PER_ROW and (if grid) MAX_ACTIVE_PER_ROW
      - Row-mix target actives (soft)
      - Final sweep to enforce hard cap in grid mode
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
    def vis_sig(rr: int) -> Tuple[Tuple[str,str], ...]:
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

        if (r+1) % LOG_EVERY_ROWS == 0:
            print(f"  • Built {r+1}/{T} rows...")

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

def build_with_restarts(T: int,
                        category_info: Dict[str, List[str]],
                        E: int,
                        A_min: int,
                        rng: np.random.Generator,
                        study_mode: str,
                        max_active_per_row: Optional[int]) -> Optional[List[Dict[str, str]]]:
    """Fixed-T builder: heavy retries, NEVER changes T. Returns rows or None (no exception)."""
    for attempt in range(1, GLOBAL_RESTARTS+1):
        rows = build_once(T, category_info, E, A_min, rng, study_mode, max_active_per_row)
        if rows is not None:
            print("  ✓ Success.")
            return rows
        if attempt % 50 == 0:
            print(f"  ↻ Retrying… ({attempt}/{GLOBAL_RESTARTS})")
    return None

# ------------------------
# Per-respondent diagnostics & enforcement
# ------------------------
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
            rows = build_with_restarts(T, category_info, E, A_min, rng, study_mode, max_active_per_row)
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

# ------------------------
# Global preflight to lock T (may bump once; duplicates NOT checked here)
# ------------------------
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
            if build_once(T_try, category_info, E, A_min_used, rng, study_mode, max_active_per_row) is not None:
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

# ------------------------
# IO
# ------------------------
def _sha256_of_dataframe_csv(df: pd.DataFrame) -> str:
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()

def write_combined_outputs(out_dir: str, project_slug: str, all_rows_per_resp,
                           category_info, T: int, E: int, A_map: Dict[str,int],
                           avg_k: float, A_min_used: int,
                           per_resp_reports: Dict[int,dict],
                           study_mode: str):
    out_dir = _ensure_dir(out_dir)
    cats = list(category_info.keys())
    elems = [e for es in category_info.values() for e in es]

    # ---- Build vignettes and design-matrix tables ----
    vignettes_records = []
    X_records = []
    for consumer_id, rows in all_rows_per_resp:
        for row in rows:
            rec = {"Consumer_ID": consumer_id}
            rec.update({c: row[c] for c in cats})
            vignettes_records.append(rec)

            xrow = {"Consumer_ID": consumer_id}
            for e in elems:
                xrow[e] = 0
            for c in cats:
                ch = row[c]
                if ch in elems:
                    xrow[ch] = 1
            X_records.append(xrow)

    v_df = pd.DataFrame(vignettes_records, columns=["Consumer_ID"] + cats)
    d_df = pd.DataFrame(X_records,    columns=["Consumer_ID"] + elems)

    vpath = os.path.join(out_dir, f"{project_slug}_vignettes_all.csv")
    dpath = os.path.join(out_dir, f"{project_slug}_design_matrix_all.csv")
    v_df.to_csv(vpath, index=False)
    d_df.to_csv(dpath, index=False)

    # ---- QC certificate ----
    dataset_id = _sha256_of_dataframe_csv(d_df)
    spath = os.path.join(out_dir, f"{project_slug}_QC_certificate.txt")

    with open(spath, "w", encoding="utf-8") as f:
        M = len(elems); C = len(cats); P = params_main_effects(category_info)
        f.write("=== QC CERTIFICATE (Professor Gate) ===\n")
        f.write(f"Project: {project_slug}\n")
        f.write(f"Generator: {GEN_VERSION}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Dataset ID (SHA-256 of design matrix CSV): {dataset_id}\n")
        f.write(f"Base RNG seed: {BASE_SEED}\n\n")

        # Configuration (includes study mode)
        f.write("Configuration:\n")
        f.write(f"  Study mode: {study_mode}")
        if study_mode == "grid":
            f.write(f" (max actives/row ≤ {min(GRID_MAX_ACTIVE, C)})")
        f.write("\n")
        f.write(f"  Categories: {', '.join([f'{c}({len(category_info[c])})' for c in cats])}\n")
        f.write(f"  Rows/respondent (T): {T}\n")
        f.write(f"  Exposures/element (E): {E}\n")
        f.write(f"  Absence policy: ABSENCE_RATIO = {ABSENCE_RATIO}  (A_min used = {A_min_used})\n")
        f.write(f"  T ratio knob: T_RATIO = {T_RATIO}\n")
        f.write(f"  Row-mix: mode={ROW_MIX_MODE}, widen={ROW_MIX_WIDEN}\n\n")

        # Identifiability
        f.write("Identifiability (main effects, reference coding):\n")
        f.write(f"  P (parameters) = {P} = 1 + Σ(q_j - 1)\n")
        f.write(f"  Identifiable?  = {'YES' if T > P else 'NO'} (recommend T ≥ P + 2)\n\n")

        # Gate thresholds
        f.write("Professor Gate thresholds:\n")
        f.write(f"  Condition number ≤ {QC_KAPPA_MAX:.1e}\n")
        f.write(f"  Min tolerance (1/max VIF) ≥ {VIF_TOL_MIN:.1e}\n")
        f.write(f"  Random-DV stress tests: {QC_RANDOM_Y_K}/{QC_RANDOM_Y_K} must pass (rank=p, residual ≤ {QC_LS_TOL:.1e})\n\n")

        # Per-respondent summary
        grouped = d_df.groupby("Consumer_ID")
        worst_kappa = 0.0
        worst_resp: Optional[int] = None
        all_gate_pass = True

        f.write("Per-respondent QC summary:\n")
        for cid, g in grouped:
            rep = per_resp_reports.get(int(cid), {})
            all_gate_pass = all_gate_pass and bool(rep.get("gate_passed", False))
            kappa_val = float(rep.get("kappa", 0.0))
            if kappa_val >= worst_kappa:
                worst_kappa = kappa_val
                worst_resp = cid

            # exposure and absence distributions
            row_actives = g[elems].sum(axis=1).to_numpy()
            abs_counts = {}
            for c in cats:
                sub = g[[e for e in elems if e.startswith(c + "_")]]
                abs_counts[c] = int((sub.sum(axis=1) == 0).sum())

            f.write(f"\n  Consumer_ID={cid}\n")
            f.write(f"    Element exposures: all exactly {E}\n")
            f.write("    Per-category absences: " + ", ".join(f"{c}:{abs_counts[c]}" for c in cats) + "\n")
            f.write(f"    Row actives (min/max/mean): {int(row_actives.min())}/{int(row_actives.max())}/{float(row_actives.mean()):.2f}\n")

            # Distribution of #actives per row
            vc = pd.Series(row_actives).value_counts().to_dict()
            k_min = max(MIN_ACTIVE_PER_ROW, int(row_actives.min()))
            k_max = int(row_actives.max())
            for k in range(k_min, k_max + 1):
                f.write(f"      - {k} Actives: {int(vc.get(k, 0))}\n")

            # Collinearity checks
            f.write("    Collinearity checks:\n")
            f.write(f"      - Zero-variance columns: {rep.get('zero_var', 0)}\n")
            f.write(f"      - Exact duplicate pairs: {rep.get('dup_pairs', 0)}\n")
            f.write(f"      - Rank / p: {rep.get('rank', 'NA')} / {rep.get('p', 'NA')}\n")
            f.write(f"      - s_min / s_max: {rep.get('s_min', float('nan'))} / {rep.get('s_max', float('nan'))}\n")
            f.write(f"      - Condition number κ(X): {rep.get('kappa', float('nan'))}  (threshold ≤ {QC_KAPPA_MAX:.0f})\n")
            f.write(f"      - Max VIF / Min tolerance: {rep.get('max_vif', float('nan'))} / {rep.get('min_tolerance', float('nan'))}\n")
            f.write(f"      - Random-DV fits (rank / LS): {rep.get('fit_rank_passes',0)}/{rep.get('ls_total',QC_RANDOM_Y_K)}  &  {rep.get('ls_passes',0)}/{rep.get('ls_total',QC_RANDOM_Y_K)}\n")
            f.write(f"      - Max cross-cat |r|: {rep.get('max_abs_r', float('nan')):.3f} (pair: {rep.get('max_r_pair', ('',''))[0]} vs {rep.get('max_r_pair', ('',''))[1]})\n")
            f.write(f"      - Professor Gate: {'PASS' if rep.get('gate_passed', False) else 'FAIL'}\n")

        # Global verdict
        f.write("\nGlobal QC verdict:\n")
        f.write(f"  All respondents passed Professor Gate: {'YES' if all_gate_pass else 'NO'}\n")
        f.write(f"  Worst-case κ(X) across respondents: {worst_kappa:.4g} (Consumer_ID={worst_resp})\n")

    print("\n[Saved]")
    print(f"  • Vignettes CSV (combined):     {os.path.abspath(vpath)}")
    print(f"  • Design matrix CSV (combined): {os.path.abspath(dpath)}")
    print(f"  • QC Certificate TXT:           {os.path.abspath(spath)}")



# ------------------------
# Worker wrapper (process-safe)
# ------------------------
def _build_one_worker(args):
    """
    Runs in a separate process. No file I/O here.
    Returns: (resp_id, rows, X_df, report)
    """
    (resp_id, T, category_info, E, A_min_used, base_seed, log_every_rows,
     study_mode, max_active_per_row) = args

    # keep progress cadence
    global LOG_EVERY_ROWS
    LOG_EVERY_ROWS = log_every_rows

    rows, X, report = build_respondent_with_uniqueness(
        T, category_info, E, A_min_used, base_seed, resp_id,
        study_mode, max_active_per_row
    )
    return (resp_id, rows, X, report)

# ------------------------
# Main
# ------------------------
def main():
    print("== Auto Conjoint Vignette Builder (auto absence, wider row mix, GLOBAL T LOCK, per-respondent unique columns, Professor Gate) ==\n")
    project = _prompt_str("Project name", default="auto_test")
    project_slug = _sanitize(project)

    C = _prompt_int("How many categories? (≥3)", min_val=3, default=5)
    category_info: Dict[str, List[str]] = {}
    for i in range(C):
        name = _prompt_str(f"  Name for category #{i+1}", default=chr(ord('A') + (i % 26)))
        m   = _prompt_int(f"  How many elements in '{name}'?", min_val=1, default=3)
        category_info[name] = [f"{name}_{j+1}" for j in range(m)]

    N = _prompt_int("Number of respondents (N)", min_val=1, default=1)

    # --- Study mode & per-row active cap ---
    mode = _prompt_str("Study mode ('layout' or 'grid')", default=DEFAULT_STUDY_MODE).strip().lower()
    if mode not in ("layout", "grid"):
        print("Invalid mode; defaulting to 'layout'.")
        mode = "layout"

    # In grid mode, hard-cap actives per row; in layout, allow up to the # of categories
    max_active_per_row = min(GRID_MAX_ACTIVE, C) if mode == "grid" else C

    # Sanity: cap must not be below the minimum actives rule
    if max_active_per_row < MIN_ACTIVE_PER_ROW:
        raise ValueError(
            f"MAX_ACTIVE_PER_ROW ({max_active_per_row}) < MIN_ACTIVE_PER_ROW ({MIN_ACTIVE_PER_ROW}). "
            "Increase categories or relax settings."
        )

    # Plan automatically (ratio-aware absence + T_RATIO)
    T, E, A_map, avg_k, A_min_used = plan_T_E_auto(category_info, mode, max_active_per_row)

    # Set logging cadence: one progress line per respondent
    global LOG_EVERY_ROWS
    LOG_EVERY_ROWS = max(T, 25)

    # Preflight lock T, but do not abort if it can’t lock.
    try:
        T, A_map = preflight_lock_T(T, category_info, E, A_min_used, mode, max_active_per_row)
    except RuntimeError as e:
        print(f"⚠️ Preflight could not lock T ({e}). Proceeding with T={T} in rebuild-until-pass mode.")
        A_map = {c: max(A_min_used, T - len(category_info[c]) * E) for c in category_info}

    # Recompute avg_k in case T was bumped
    M = sum(len(category_info[c]) for c in category_info)
    avg_k = (M * E) / T

    print(f"\n[Plan] FINAL T={T}, E={E}, avg actives ≈ {avg_k:.2f} (ABSENCE_RATIO={ABSENCE_RATIO}, A_min used = {A_min_used}, T_RATIO={T_RATIO})")
    print(f"[Plan] Row-mix mode: {ROW_MIX_MODE}, widen={ROW_MIX_WIDEN}")
    print("[Plan] Absences per category:", ", ".join([f"{c}:{A_map[c]}" for c in category_info]))

    # Build each respondent with **per-respondent unique columns** + **Professor Gate**
    out_dir = _ensure_dir(f"./{project_slug}_{time.strftime('%Y%m%d_%H%M%S')}")
    all_rows_per_resp = []
    per_resp_reports: Dict[int, dict] = {}

    # --------- PARALLEL BY RESPONDENT ----------
    max_workers = min(os.cpu_count() or 1, N)

    try:
        mp.set_start_method("spawn")
    except RuntimeError:
        pass  # already set

    print(f"\n[Parallel] Launching up to {max_workers} workers…")

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

    all_rows_per_resp.sort(key=lambda t: t[0])

    write_combined_outputs(out_dir, project_slug, all_rows_per_resp, category_info,
                           T, E, A_map, avg_k, A_min_used, per_resp_reports, mode)
    print("\nDone.")

# if __name__ == "__main__":
#     main()
