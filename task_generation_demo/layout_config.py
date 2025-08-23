import os
from datetime import datetime
from common import analyze_design
from layout_logic import generate_layer_mode, auto_pick_t_for_layer

def _sanitize(name: str) -> str:
    return name.replace(" ", "_").strip()

def _prompt_int(prompt, min_val=None):
    while True:
        raw = input(f"{prompt}: ").strip()
        try:
            val = int(raw)
        except Exception:
            print("Please enter an integer.")
            continue
        if min_val is not None and val < min_val:
            print(f"Please enter a value ≥ {min_val}.")
            continue
        return val

def _default_cat_name(i):
    import string
    letters = list(string.ascii_uppercase)
    if i < len(letters):
        return letters[i]
    return f"{letters[i % 26]}{i // 26 + 1}"

def main():
    print("== Layer Mode ==")
    project_name = input("Project name: ").strip()
    while not project_name:
        project_name = input("Project name (cannot be empty): ").strip()

    N = _prompt_int("Number of respondents (N)", min_val=1)

    num_categories = _prompt_int("How many categories?", min_val=1)
    category_info = {}
    for i in range(num_categories):
        default_name = _default_cat_name(i)
        name = input(f"  Name for category #{i+1} [{default_name}]: ").strip() or default_name
        elems = _prompt_int(f"  How many elements in category '{name}'?", min_val=1)
        category_info[name] = [f"{name}_{j+1}" for j in range(elems)]

    # Tasks per consumer: default 24, but clip to uniqueness capacity if smaller
    Tpc, cap = auto_pick_t_for_layer(category_info, baseline=24)
    if Tpc < 24:
        print(f"[INFO] Per-respondent uniqueness capacity is {cap}; "
              f"tasks per consumer clipped to T={Tpc}.")
    else:
        print(f"[INFO] Tasks per consumer set to T={Tpc} (baseline 24).")

    print("\n[LAYER MODE] Building design (one element per category per vignette), "
          "per-respondent uniqueness, and fixed 2% within-category exposure tolerance…")

    design_df, Ks, _ = generate_layer_mode(
        num_consumers=N,
        tasks_per_consumer=Tpc,
        category_info=category_info,
        tol_pct=0.02  # fixed, not prompted
    )

    # Save outputs
    sanitized = _sanitize(project_name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = f"{sanitized}_{ts}"
    os.makedirs(folder, exist_ok=True)

    design_path = os.path.join(folder, f"{sanitized}_design.csv")
    design_df.to_csv(design_path, index=False)

    params_path = os.path.join(folder, f"{sanitized}_parameters.txt")
    with open(params_path, "w", encoding="utf-8") as f:
        f.write(f"mode=layer\n")
        f.write(f"project_name={project_name}\n")
        f.write(f"num_consumers={N}\n")
        f.write(f"tasks_per_consumer={int(Ks.size // N)}\n")
        f.write(f"categories={list(category_info.keys())}\n")
        f.write(f"category_sizes={{" + ", ".join([f'{k}:{len(v)}' for k,v in category_info.items()]) + "}}\n")
        f.write(f"tolerance_pct_layer=2.0\n")

    report = analyze_design(design_df, category_info)
    report_path = os.path.join(folder, f"{sanitized}_analysis_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ Files saved in '{folder}'")
    print(f"   • Design CSV: {design_path}")
    print(f"   • Parameters: {params_path}")
    print(f"   • Analysis report: {report_path}")

if __name__ == "__main__":
    main()
