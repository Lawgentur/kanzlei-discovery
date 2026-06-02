import csv
import os

master_file = 'media/jobs_master_full.csv'
output_file = 'target_firms_full.csv'

firms = set()
if os.path.exists(master_file):
    with open(master_file, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle potential BOM or weird characters in header
            kanzlei_key = 'Kanzlei'
            if kanzlei_key not in row:
                # Fallback: check keys for something containing 'Kanzlei'
                for k in row.keys():
                    if 'Kanzlei' in k:
                        kanzlei_key = k
                        break
            
            val = row.get(kanzlei_key)
            if val:
                firms.add(val.strip())

print(f"Found {len(firms)} unique firms")

with open(output_file, mode='w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Kanzlei'])
    for firm in sorted(list(firms)):
        writer.writerow([firm])

print(f"Created {output_file} with {len(firms)} entries.")
