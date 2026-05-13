import yaml, glob, os, sys
sys.stdout.reconfigure(encoding='utf-8')


def n(s):
    return str(s).strip().lower().replace(' ', '').replace('-', '').replace('_', '')


claimed = {}
for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), '..', 'dict', '*.yaml'))):
    name = os.path.basename(f)
    for it in (yaml.safe_load(open(f, encoding='utf-8')) or []):
        for k in [it['term']] + (it.get('aliases') or []):
            nk = n(k)
            if not nk:
                continue
            if nk in claimed and claimed[nk][0] != it['term']:
                a_term, a_file = claimed[nk]
                b_term, b_file = it['term'], name
                print(f'COLLISION {nk!r}: {a_term!r} ({a_file}) vs {b_term!r} ({b_file})')
            claimed[nk] = (it['term'], name)
