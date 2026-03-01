from oil.memory.actions import _parse_categories, _is_negated
import re
text = 'Do not rollback. Investigate the change, then restart if needed.'
tokens = re.sub(r'[\"' + "'" + r',;!?]', '', text.lower()).split()
print('tokens:', tokens)
for i, t in enumerate(tokens):
    print(f'  [{i}] {repr(t)}  is_negated={_is_negated(tokens, i)}')
