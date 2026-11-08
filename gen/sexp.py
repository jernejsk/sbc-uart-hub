"""Minimal S-expression parser/writer for KiCad files."""
import re

_tok = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """Unquoted atom."""


def parse(text):
    stack, cur = [], []
    pos = 0
    n = len(text)
    while pos < n:
        m = _tok.match(text, pos)
        if not m:
            if text[pos:].strip() == '':
                break
            raise ValueError('parse error at %d' % pos)
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            s = m.group(3)[1:-1]
            cur.append(s.replace('\\"', '"').replace('\\\\', '\\'))
        else:
            cur.append(Sym(m.group(4)))
    return cur[0] if len(cur) == 1 else cur


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def dump(x, ind=0):
    if isinstance(x, list):
        if not x:
            return '()'
        simple = all(not isinstance(e, list) for e in x)
        if simple:
            return '(' + ' '.join(dump(e) for e in x) + ')'
        out = '(' + dump(x[0])
        for e in x[1:]:
            if isinstance(e, list):
                out += '\n' + '\t' * (ind + 1) + dump(e, ind + 1)
            else:
                out += ' ' + dump(e)
        return out + '\n' + '\t' * ind + ')'
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return 'yes' if x else 'no'
    if isinstance(x, (int, float)):
        r = ('%.4f' % x).rstrip('0').rstrip('.')
        return '0' if r == '-0' else r
    return q(x)


def find(node, key):
    return [e for e in node if isinstance(e, list) and e and e[0] == key]


def find1(node, key):
    r = find(node, key)
    return r[0] if r else None
