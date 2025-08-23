# common.py
import pandas as pd
import numpy as np
import io
import sys

rng = np.random.default_rng()

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

def vignette_signature_pairs(cat_elem_pairs):
    """Canonical signature for per-respondent uniqueness (layout mode)."""
    return tuple(sorted(cat_elem_pairs, key=lambda x: x[0]))

def vignette_signature_elements(elem_list):
    """Canonical signature for per-respondent uniqueness (grid mode)."""
    return tuple(sorted(elem_list))
