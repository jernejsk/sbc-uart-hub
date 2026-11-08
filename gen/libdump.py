"""Dump pins of a KiCad library symbol: libdump.py Lib:Name"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sexp import parse, find, find1

SYMDIR = '/usr/share/kicad/symbols'


def load_symbol(libname, name, symdir=SYMDIR):
    path = libname if libname.endswith('.kicad_sym') else os.path.join(symdir, libname + '.kicad_sym')
    lib = parse(open(path).read())
    syms = {s[1]: s for s in find(lib, 'symbol')}
    return syms, syms[name]


def pins(libname, name, symdir=SYMDIR):
    syms, s = load_symbol(libname, name, symdir)
    ext = find1(s, 'extends')
    base = syms[ext[1]] if ext else s
    out = []
    for unit in find(base, 'symbol'):
        uname = unit[1]
        un = int(uname.split('_')[-2])
        for p in find(unit, 'pin'):
            at = find1(p, 'at')
            out.append(dict(unit=un, type=str(p[1]), name=find1(p, 'name')[1],
                            num=find1(p, 'number')[1], x=float(at[1]), y=float(at[2]),
                            rot=float(at[3]) if len(at) > 3 else 0.0,
                            hidden=any(str(e) == 'hide' for e in p) or bool(find1(p, 'hide'))))
    return out


if __name__ == '__main__':
    lib, name = sys.argv[1].split(':')
    for p in sorted(pins(lib, name), key=lambda p: (p['unit'], p['num'].zfill(4))):
        print('u%d %4s %-14s %-14s (%g,%g) r%g%s' % (p['unit'], p['num'], p['name'], p['type'],
              p['x'], p['y'], p['rot'], ' H' if p['hidden'] else ''))
