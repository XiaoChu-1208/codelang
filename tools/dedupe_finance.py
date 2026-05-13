"""Strip finance.yaml entries / aliases that would collide with other dict
yamls or with earlier finance entries under the build_dict normalization.

Drop rules:
  - drop an entry if its term normalizes to a key already claimed by another yaml
    (whether that came from a term or an alias).
  - drop an alias if its normalized form collides with anything already claimed.

Preserves all comments and structure in finance.yaml.
"""
import yaml, glob, os, sys, re
sys.stdout.reconfigure(encoding='utf-8')

DICT_DIR = os.path.join(os.path.dirname(__file__), '..', 'dict')
FINANCE = os.path.join(DICT_DIR, 'finance.yaml')


def normalize(s):
    return str(s).strip().lower().replace(' ', '').replace('-', '').replace('_', '')


# 1) keys reserved by OTHER yamls
reserved = {}  # normalized_key -> "term (in file)"
for f in sorted(glob.glob(os.path.join(DICT_DIR, '*.yaml'))):
    if os.path.basename(f) == 'finance.yaml':
        continue
    name = os.path.basename(f)
    for it in (yaml.safe_load(open(f, encoding='utf-8')) or []):
        owner = f'{it["term"]} ({name})'
        reserved.setdefault(normalize(it['term']), owner)
        for a in (it.get('aliases') or []):
            reserved.setdefault(normalize(a), owner)

# 2) Walk finance entries in order. Track claimed normalized keys.
data = yaml.safe_load(open(FINANCE, encoding='utf-8')) or []
claimed = dict(reserved)  # start with reserved keys
dropped_entries = []
alias_overrides = {}     # term -> kept-aliases-list (only set when modified)
for it in data:
    term = it['term']
    term_nk = normalize(term)
    if term_nk in claimed:
        dropped_entries.append((term, claimed[term_nk]))
        continue
    claimed[term_nk] = f'{term} (finance.yaml)'

    original_aliases = it.get('aliases') or []
    kept = []
    modified = False
    for a in original_aliases:
        nk = normalize(a)
        if not nk or nk == term_nk:
            kept.append(a)
            continue
        if nk in claimed:
            modified = True
            continue
        claimed[nk] = f'{term} (finance.yaml)'
        kept.append(a)
    if modified:
        alias_overrides[term] = kept

# 3) Read lines, rewrite alias lines for modified entries, drop entry blocks
#    for dropped entries.
dropped_set = {t for t, _ in dropped_entries}
with open(FINANCE, encoding='utf-8') as f:
    lines = f.readlines()

out = []
i = 0
while i < len(lines):
    line = lines[i]
    m = re.match(r'^- term: (.+)$', line.rstrip())
    if m:
        term = m.group(1)
        if term in dropped_set:
            # skip entire block: from this "- term:" until next blank line, then skip the blank
            j = i + 1
            while j < len(lines) and lines[j].strip() != '':
                j += 1
            if j < len(lines) and lines[j].strip() == '':
                j += 1
            i = j
            continue
        # Possibly modify aliases of this entry: emit term line, then look ahead
        out.append(line)
        i += 1
        # If next line is aliases:, optionally rewrite
        if i < len(lines) and re.match(r'^  aliases: \[', lines[i]):
            if term in alias_overrides:
                kept = alias_overrides[term]
                if kept:
                    out.append(f'  aliases: [{", ".join(kept)}]\n')
                else:
                    out.append('  aliases: []\n')
            else:
                out.append(lines[i])
            i += 1
        continue
    out.append(line)
    i += 1

with open(FINANCE, 'w', encoding='utf-8') as f:
    f.writelines(out)

print(f'dropped {len(dropped_entries)} entries whose term collides with another yaml:')
for term, owner in dropped_entries:
    print(f'  - {term!r} (already owned by {owner})')
print(f'modified aliases on {len(alias_overrides)} entries')
