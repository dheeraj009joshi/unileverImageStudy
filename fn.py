import pandas as pd
import numpy as np
import json
import os
import sys
import io
from datetime import datetime
from itertools import combinations

def get_user_input(prompt, type, min_val=None, max_val=None):
    """Gets and validates user input."""
    while True:
        try:
            if type == str:
                value = input(prompt)
                if not value.strip():
                    print("Project name cannot be empty.")
                    continue
            else:
                value = type(input(prompt))
                if min_val is not None and value < min_val:
                    print(f"Please enter a value greater than or equal to {min_val}.")
                elif max_val is not None and value > max_val:
                    print(f"Please enter a value less than or equal to {max_val}.")
                else:
                    return value
            return value
        except ValueError:
            print("Invalid input. Please enter a valid number.")

def analyze_design(design_df):
    """Analyzes the generated design and returns a report string."""
    output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = output

    print("--- Design Analysis Report ---")
    
    # Constraint Check
    print("\n## 1. Constraint Check: Active Elements per Task")
    row_sums = design_df.sum(axis=1)
    min_sum = row_sums.min()
    max_sum = row_sums.max()
    print(f"  - The number of active elements per task ranges from {min_sum} to {max_sum}.")
    
    # Main Effect Balance
    print("\n## 2. Main Effect Balance: Appearance of Each Element")
    element_counts = design_df.sum(axis=0)
    print("  - Total appearances for each element:")
    print(element_counts)
    avg_count = element_counts.mean()
    std_dev = element_counts.std()
    print(f"  - Average appearances per element: {avg_count:.2f}")
    print(f"  - Standard deviation: {std_dev:.2f}")

    # Pairwise Balance
    print("\n## 3. Pairwise Balance: Co-occurrence of Elements")
    co_occurrence_matrix = np.dot(design_df.T, design_df)
    pairwise_counts = []
    num_elements = design_df.shape[1]
    for i, j in combinations(range(num_elements), 2):
        pair_count = co_occurrence_matrix[i, j]
        pairwise_counts.append(pair_count)
    
    pairwise_counts_series = pd.Series(pairwise_counts)
    min_pair_count = pairwise_counts_series.min()
    max_pair_count = pairwise_counts_series.max()
    avg_pair_count = pairwise_counts_series.mean()
    std_dev_pair = pairwise_counts_series.std()
    
    print(f"  - Pairwise counts range from {min_pair_count} to {max_pair_count}.")
    print(f"  - Average co-occurrence: {avg_pair_count:.2f}")
    print(f"  - Standard deviation: {std_dev_pair:.2f}")

    sys.stdout = original_stdout
    
    return output.getvalue()

def generate_ideamap_design():
    """Generates an IdeaMap-style design based on user input."""
    print("--- IdeaMap Design Generator ---")
    print("Please enter your design parameters:")

    project_name = get_user_input("Enter a project name (e.g., MyNewProductStudy): ", str)
    num_elements = get_user_input("Number of elements (e.g., 16): ", int, min_val=2)
    tasks_per_consumer = get_user_input("Number of tasks per consumer (e.g., 24): ", int, min_val=1)
    num_consumers = get_user_input("Number of consumers (e.g., 200): ", int, min_val=1)
    min_active = get_user_input("Minimum number of active elements per task (e.g., 3): ", int, min_val=0, max_val=num_elements)
    max_active = get_user_input("Maximum number of active elements per task (e.g., 4): ", int, min_val=min_active, max_val=num_elements)

    total_tasks = tasks_per_consumer * num_consumers
    print(f"\nGenerating a total of {total_tasks} tasks...")

    design_data = []
    candidate_pool = []
    num_candidates_to_generate = total_tasks * 20
    
    while len(candidate_pool) < num_candidates_to_generate:
        random_task = np.random.randint(0, 2, num_elements)
        if min_active <= sum(random_task) <= max_active:
            candidate_pool.append(random_task)
            
    if len(candidate_pool) < total_tasks:
        final_tasks = candidate_pool
    else:
        final_tasks = np.array(candidate_pool)[np.random.choice(len(candidate_pool), total_tasks, replace=False)]

    element_names = [f"E{i+1}" for i in range(num_elements)]
    design_df = pd.DataFrame(final_tasks, columns=element_names)
    consumer_ids = [f"C{i+1}" for i in range(num_consumers) for _ in range(tasks_per_consumer)]
    design_df.insert(0, "Consumer ID", consumer_ids)

    # File and Folder Management
    sanitized_name = project_name.replace(" ", "_").strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{sanitized_name}_{timestamp}"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    # Save design files
    design_df.to_csv(os.path.join(folder_name, f"{sanitized_name}_design.csv"), index=False)
    
    params = {
        "project_name": project_name,
        "num_elements": num_elements,
        "tasks_per_consumer": tasks_per_consumer,
        "num_consumers": num_consumers,
        "min_active_elements": min_active,
        "max_active_elements": max_active,
        "total_tasks": total_tasks
    }
    with open(os.path.join(folder_name, f"{sanitized_name}_parameters.json"), "w") as f:
        json.dump(params, f, indent=4)

    # Run and save the analysis report
    analysis_report = analyze_design(design_df.drop(columns=['Consumer ID']))
    with open(os.path.join(folder_name, f"{sanitized_name}_analysis_report.txt"), "w") as f:
        f.write(analysis_report)
        
    print(f"\n✅ All files successfully generated and saved to the folder '{folder_name}'")

if __name__ == "__main__":
    generate_ideamap_design()