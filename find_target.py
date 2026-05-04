import os
import pandas as pd

def find_file():
    for root, dirs, files in os.walk('/home/ubuntu'):
        if 'target_firms_full.csv' in files:
            print(os.path.join(root, 'target_firms_full.csv'))
            return
    print("Not found")

find_file()
