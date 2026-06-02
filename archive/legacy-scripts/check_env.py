import os
print("CWD:", os.getcwd())
print("Files:", os.listdir('.'))
if os.path.exists('target_firms.csv'):
    with open('target_firms.csv', 'r') as f:
        print("target_firms.csv lines:", len(f.readlines()))
