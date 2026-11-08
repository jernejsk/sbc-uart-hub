#!/usr/bin/env python3
"""Project footprints derived from the KiCad library.

PinHeader_1x03_P2.54mm_Horizontal_Edge: the stock right-angle header with all
silkscreen that lies past the plastic body's inner face removed. The board places
the body flush with the board edge (pads 4.04 mm in), so that silk would be clipped.
"""
import os
import sys

GEN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GEN)
from sexp import Sym, dump, find1, parse  # noqa: E402

SRC = '/usr/share/kicad/footprints/Connector_PinHeader_2.54mm.pretty/PinHeader_1x03_P2.54mm_Horizontal.kicad_mod'
OUT = os.path.normpath(os.path.join(GEN, '..', 'hw', 'lib', 'sbcu.pretty'))
NAME = 'PinHeader_1x03_P2.54mm_Horizontal_Edge'
EDGE_X = 3.9          # footprint-local x of the board edge (4.04) minus silk clearance


def is_silk(n):
    lay = find1(n, 'layer')
    return lay is not None and lay[1] == 'F.SilkS'


def max_x(n):
    xs = []
    for k in ('start', 'end', 'center', 'mid'):
        p = find1(n, k)
        if p is not None:
            xs.append(float(p[1]))
    return max(xs) if xs else 0.0


def main():
    fp = parse(open(SRC).read())
    out = [fp[0], NAME]
    for n in fp[2:]:
        if isinstance(n, list) and n and n[0] in ('fp_line', 'fp_rect', 'fp_poly', 'fp_arc') and is_silk(n) \
                and max_x(n) > EDGE_X:
            continue
        if isinstance(n, list) and n and n[0] == 'descr':
            n = [n[0], 'Right-angle 1x03 2.54 mm pin header, body flush with board edge, '
                       'edge-clipped silkscreen (derived from ' + os.path.basename(SRC) + ')']
        out.append(n)
    # inner face of the plastic body
    out.append([Sym('fp_line'), [Sym('start'), 1.39, -1.38], [Sym('end'), 1.39, 6.46],
                [Sym('stroke'), [Sym('width'), 0.12], [Sym('type'), Sym('solid')]], [Sym('layer'), 'F.SilkS']])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, NAME + '.kicad_mod'), 'w') as f:
        f.write(dump(out) + '\n')
    print('wrote', os.path.join(OUT, NAME + '.kicad_mod'))


if __name__ == '__main__':
    main()
