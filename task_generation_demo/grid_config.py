# grid_config.py
import os, json, argparse
from datetime import datetime
import numpy as np
import pandas as pd
import common  # for rng seeding (common.rng)
from grid_logic import choose_k_t_capped_policy, generate_grid_mode

DEFAULTS_PATH = "grid_config.json"

def load_defaults(path=DEFAULTS_PATH):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    # Only essentials.
    return {
        "seed": data.get("seed", None),
        "out_dir": data.get("out_dir", "designs"),
    }

def basic_analyze(design_df):
    work = design_df.drop(columns=["Consumer ID"])
    el_counts = work.sum(axis=0)
    row_sums = work.sum(axis=1)

    mean_exposure = el_counts.mean()
    std_exposure = el_counts.std(ddof=0)  # population std
    cv = (std_exposure / mean_exposure) if mean_exposure > 0 else 0.0

    lines = []
    lines.append("--- Design Analysis Report ---")
    lines.append("\n## 1. Category Balance: All")
    lines.append(f"  - Total active flags: {int(work.values.sum())}")
    lines.append("\n## 2. Element Exposure")
    lines.append(str(el_counts))
    lines.append(f"  - Mean: {mean_exposure:.3f} | Std: {std_exposure:.3f} | CV: {100*cv:.2f}%")
    lines.append("\n## 3. Vignette Structure")
    lines.append(f"  - Active elements per vignette: min={int(row_sums.min())} max={int(row_sums.max())}")
    return "\n".join(lines)

def save_outputs(project_name, N, E, Ks, design_df, out_dir):
    sanitized = project_name.replace(" ", "_").strip()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(out_dir, f"{sanitized}_{ts}")
    os.makedirs(folder, exist_ok=True)

    design_path = os.path.join(folder, f"{sanitized}_design.csv")
    design_df.to_csv(design_path, index=False)

    # exposure stats
    work = design_df.drop(columns=["Consumer ID"])
    el_counts = work.sum(axis=0)
    mean_exposure = float(el_counts.mean())
    std_exposure = float(el_counts.std(ddof=0))
    cv = float((std_exposure / mean_exposure) if mean_exposure > 0 else 0.0)

    params = {
        "mode": "grid",
        "project_name": project_name,
        "num_consumers": int(N),
        "num_elements": int(E),
        "tasks_per_consumer": int(Ks.size // N),
        "K_summary": {"min": int(Ks.min()), "max": int(Ks.max()), "sum": int(Ks.sum())},
        "exposure_mean": mean_exposure,
        "exposure_std": std_exposure,
        "exposure_cv_pct": 100.0 * cv
    }
    with open(os.path.join(folder, f"{sanitized}_parameters.json"), "w", encoding="utf-8") as f:
        json.dump(params, f, indent=4)

    report = basic_analyze(design_df)
    with open(os.path.join(folder, f"{sanitized}_analysis_report.txt"), "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ Files saved in '{folder}'")
    print(f"   • Design CSV: {design_path}")
    print(f"   • Mean exposure: {mean_exposure:.3f} | Std: {std_exposure:.3f} | CV: {100*cv:.2f}%")
    print("   • Analysis report and parameters JSON included.")

def main():
    cfg = load_defaults()

    # Seed RNG (do BEFORE importing grid_logic so it sees the seeded rng)
    if cfg["seed"] is not None:
        common.rng = np.random.default_rng(cfg["seed"])

    # Import after seeding
    from grid_logic import generate_grid_mode

    ap = argparse.ArgumentParser(description="Grid design runner (prompts only for project, N, E).")
    ap.add_argument("-p", "--project-name", type=str, help="Project name")
    ap.add_argument("-n", "--num-consumers", type=int, help="Respondents (N)")
    ap.add_argument("-e", "--num-elements", type=int, help="Elements (E)")
    args = ap.parse_args()

    project_name = args.project_name or input("Project name: ").strip()
    N = int(args.num_consumers or int(input("Number of respondents (N): ").strip()))
    E = int(args.num_elements or int(input("Number of elements (E): ").strip()))

    # Assumptions
    if E < 4:
        raise SystemExit("Number of elements (E) must be at least 4 (K in [2,4]).")

    # Hard-capped policy (SOFT exposure): T ≤ 24, no repeats, ~equal exposure (≤1% std-dev), constant K
    minK, maxK, T, cap, notes = choose_k_t_capped_policy(N, E, maxT=24, exposure_tol_cv=0.01)

    print(f"\n[PLAN] E={E} → K={minK} (constant), C(E,K)={cap}, chosen T={T} (no m-modulus), N={N}")
    for s in notes:
        print(" ", s)
    print("Building design with per-respondent uniqueness and ≤1% exposure std-dev…")

    design_df, Ks, r_stats, _ = generate_grid_mode(
        num_consumers=N,
        tasks_per_consumer=T,
        num_elements=E,
        minK=minK,
        maxK=maxK,
        exposure_tol_cv=0.01
    )

    save_outputs(project_name, N, E, Ks, design_df, cfg["out_dir"])

if __name__ == "__main__":
    main()
