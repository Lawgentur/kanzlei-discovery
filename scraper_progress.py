import os
import csv

def check_progress():
    master_file = 'jobs_master.csv'
    target_file = 'target_firms_full.csv'
    
    if not os.path.exists(master_file):
        print("Master-Datei nicht gefunden.")
        return
        
    with open(master_file, 'r', encoding='utf-8') as f:
        master_count = sum(1 for line in f) - 1
        
    print(f"Aktueller Stand in jobs_master.csv: {master_count} Einträge.")

check_progress()
