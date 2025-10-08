import pandas as pd

# File paths - update these with your actual file paths
file1 = 'Skin_Microbiome_GRID_150_responses_2025-10-08_1641.csv'
file2 = 'Skin_Microbiome_(1-150_responds)_GRID_150_responses_2025-10-08_1554.csv'
output_file = 'combined_output.csv'

# Read both CSV files
df1 = pd.read_csv(file1)
df2 = pd.read_csv(file2)

# Assuming the panelist column is named 'Panelist' or 'panelist_id'
# Update this column name based on your actual CSV structure
panelist_column = 'Panelist'  # Change this to match your column name

# Find the maximum panelist number in the first file
max_panelist_file1 = df1[panelist_column].max()

print(f"Maximum panelist number in file 1: {max_panelist_file1}")

# Update panelist numbers in the second file to start from max+1
# Calculate the offset needed
min_panelist_file2 = df2[panelist_column].min()
offset = max_panelist_file1 - min_panelist_file2 + 1

df2[panelist_column] = df2[panelist_column] + offset

print(f"Panelist numbers in file 2 adjusted by offset: {offset}")
print(f"New range in file 2: {df2[panelist_column].min()} to {df2[panelist_column].max()}")

# Combine both dataframes
combined_df = pd.concat([df1, df2], ignore_index=True)

# Verify rows per panelist (should be 96)
rows_per_panelist = combined_df.groupby(panelist_column).size()
print("\nRows per panelist:")
print(rows_per_panelist.value_counts())

# Save the combined CSV
combined_df.to_csv(output_file, index=False)

print(f"\nCombined CSV saved to: {output_file}")
print(f"Total rows: {len(combined_df)}")
print(f"Total panelists: {combined_df[panelist_column].nunique()}")