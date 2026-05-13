import yaml, glob, os, sys
sys.stdout.reconfigure(encoding='utf-8')
fs = sorted(glob.glob(os.path.join(os.path.dirname(__file__), '..', 'dict', '*.yaml')))
total = 0
for f in fs:
    n = len(yaml.safe_load(open(f, encoding='utf-8')) or [])
    total += n
    print(f'{os.path.basename(f):<18} {n:>5}')
print('---')
print(f'files: {len(fs)}, total: {total}')
