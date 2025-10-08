import pandas as pd
import csv

# File paths
file1 = 'Skin_Microbiome_GRID_150_responses_2025-10-08_1641.csv'
file2 = 'Skin_Microbiome_(1-150_responds)_GRID_150_responses_2025-10-08_1554.csv'
output_file = 'combined_output_fixed.csv'

def process_file(filename, start_panelist=1):
    """Process a CSV file and reassign panelist numbers sequentially."""
    rows = []
    current_panelist = start_panelist
    row_count = 0
    
    with open(filename, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        header = next(reader)  # Get header row
        rows.append(header)  # Add header to output
        
        for row in reader:
            # Reassign panelist number (first column)
            row[0] = current_panelist
            rows.append(row)
            
            row_count += 1
            # Every 96 rows, move to next panelist
            if row_count % 96 == 0:
                current_panelist += 1
                print(f"Completed panelist {current_panelist - 1} (96 rows)")
    
    print(f"File {filename}: {len(rows)-1} data rows, {current_panelist - start_panelist} panelists")
    return rows, current_panelist

# Process both files
print("Processing file 1...")
rows1, next_panelist = process_file(file1, start_panelist=1)

print(f"\nProcessing file 2...")
rows2, final_panelist = process_file(file2, start_panelist=next_panelist)

# Combine the data (skip header from second file)
combined_rows = rows1 + rows2[1:]  # Skip header from second file

# Write combined file
print(f"\nWriting combined file...")
with open(output_file, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerows(combined_rows)

print(f"✅ Combined file saved: {output_file}")
print(f"📊 Total rows: {len(combined_rows)}")
print(f"👥 Total panelists: {final_panelist - 1}")
print(f"📋 Rows per panelist: 96")

# Verify the result
print(f"\n🔍 Verification:")
print(f"First panelist range: 1 to {next_panelist - 1}")
print(f"Second panelist range: {next_panelist} to {final_panelist - 1}")
print(f"Expected total rows: {(final_panelist - 1) * 96}")
print(f"Actual total rows: {len(combined_rows) - 1}")  # -1 for header