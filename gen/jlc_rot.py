#!/usr/bin/env python3
"""Check JLC assembly rotation/offset per part against JLC's own (EasyEDA) footprints.

python3 gen/jlc_rot.py <dir>      # <dir>/<LCSC>/lib.pretty/*.kicad_mod, <dir>/<LCSC>/lib.kicad_sym
                                  # (from: easyeda2kicad --footprint --symbol --lcsc_id=C.. --output <dir>/C../lib)

For each BOM line the KiCad footprint (rotation 0) is fitted onto JLC's footprint: the
rotation d in {0,90,180,270} and translation t with pads(KiCad) = Rot(d) * pads(JLC) + t.
Results go to gen/jlc_rot.json, which fab.py uses for the CPL. The JLC CPL entry for a part placed at O with rotation phi is then rotation phi + d and
position O + Rot(phi) * t. Pads are matched by number, except for 2-pin polarised parts
(LEDs) where the cathode is found by symbol pin name, and parts whose pad names differ
(geometric nearest-pad match).
"""
import csv
import glob
import math
import os
import re
import sys

import pcbnew

GEN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GEN)
import build_pcb as B  # noqa: E402
import json  # noqa: E402

ROOT = os.path.normpath(os.path.join(GEN, '..'))


def kicad_fp(name):
    for lib in glob.glob(os.path.join(B.FPDIR, '*.pretty')) + [os.path.join(B.HW, 'lib', 'sbcu.pretty')]:
        if os.path.exists(os.path.join(lib, name + '.kicad_mod')):
            return pcbnew.FootprintLoad(lib, name)
    raise KeyError(name)


def pads(fp):
    out = {}
    for p in fp.Pads():
        if not p.GetNumber():
            continue
        v = p.GetPosition()
        out.setdefault(p.GetNumber(), []).append((pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)))
    return out


def sym_pins(path):
    """pin number -> pin name from an easyeda2kicad symbol library"""
    if not os.path.exists(path):
        return {}
    txt = open(path).read()
    return {num: name for name, num in re.findall(r'\(name "([^"]*)".*?\(number "([^"]*)"', txt, re.S)}


def rot(p, deg):
    # KiCad orientation: positive = counter-clockwise on screen (y axis points down)
    a = math.radians(deg)
    x, y = p
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def body_vec(fp):
    """centroid of the footprint's graphics (silk/fab/courtyard) minus the pad centroid:
    points towards the body for parts whose pads are not symmetric about the body"""
    pts = []
    for it in fp.GraphicalItems():
        if it.GetLayer() in (pcbnew.F_SilkS, pcbnew.F_Fab, pcbnew.F_CrtYd) and it.GetClass() != 'PCB_TEXT':
            bb = it.GetBoundingBox()
            pts.append((pcbnew.ToMM(bb.GetCenter().x), pcbnew.ToMM(bb.GetCenter().y)))
    pp = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads()]
    if not pts or not pp:
        return (0.0, 0.0)
    g = (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))
    c = (sum(x for x, _ in pp) / len(pp), sum(y for _, y in pp) / len(pp))
    return (g[0] - c[0], g[1] - c[1])


def body_ok(kfp, jfp, d):
    """False when both footprints have a clear body side and rotation d puts them on opposite sides"""
    kv, jv = body_vec(kfp), body_vec(jfp)
    if math.hypot(*kv) < 0.5 or math.hypot(*jv) < 0.5:
        return True
    jr = rot(jv, d)
    return (kv[0] * jr[0] + kv[1] * jr[1]) > 0


def fit(kp, jp, pairs, ok=lambda d: True):
    """best d (deg) and t for kp ~ Rot(d) jp + t over the given (kicad_pad, jlc_pad) pairs"""
    best = None
    for d in (0, 90, 180, 270):
        if not ok(d):
            continue
        if pairs:
            a = [kp[k][0] for k, j in pairs]
            b = [rot(jp[j][0], d) for k, j in pairs]
        else:        # geometric: all pad positions, translation from centroids, nearest-pad error
            a = [q for v in kp.values() for q in v]
            b = [rot(q, d) for v in jp.values() for q in v]
        ca = (sum(x for x, _ in a) / len(a), sum(y for _, y in a) / len(a))
        cb = (sum(x for x, _ in b) / len(b), sum(y for _, y in b) / len(b))
        t = (ca[0] - cb[0], ca[1] - cb[1])
        if pairs:
            err = max(math.dist(p, (q[0] + t[0], q[1] + t[1])) for p, q in zip(a, b))
        else:
            err = max(min(math.dist(p, (q[0] + t[0], q[1] + t[1])) for q in b) for p in a)
        if best is None or err < best[2]:
            best = (d, t, err)
    return best


def main():
    src = sys.argv[1]
    board = pcbnew.LoadBoard(os.path.join(B.HW, 'sbc-uart-hub.kicad_pcb'))
    seen = {}
    for fp in board.GetFootprints():
        if fp.IsDNP() or fp.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_BOM or not fp.HasFieldByName('LCSC'):
            continue
        seen.setdefault(fp.GetFieldText('LCSC'), fp.GetFPID().GetLibItemName().wx_str())
    rows = [{'LCSC Part #': k, 'Footprint': v} for k, v in sorted(seen.items())]
    result = {}
    print('%-9s %-42s %-6s %-5s %-14s %-6s %s' % ('LCSC', 'KiCad footprint', 'match', 'd', 't (mm)', 'err', 'JLC footprint'))
    for r in rows:
        lcsc, name = r['LCSC Part #'], r['Footprint']
        mods = glob.glob(os.path.join(src, lcsc, 'lib.pretty', '*.kicad_mod'))
        if not mods:
            print('%-9s %-42s missing JLC footprint' % (lcsc, name))
            continue
        jfp = pcbnew.FootprintLoad(os.path.dirname(mods[0]), os.path.basename(mods[0])[:-10])
        kfp = kicad_fp(name)
        kp, jp = pads(kfp), pads(jfp)
        names = sym_pins(os.path.join(src, lcsc, 'lib.kicad_sym'))
        how = 'number'
        common = sorted(set(kp) & set(jp))
        pairs = [(k, k) for k in common if len(kp[k]) == 1 and len(jp[k]) == 1]
        if name.startswith('LED_'):
            # KiCad LED_*: pad 1 = cathode. Find JLC's cathode pad from the symbol pin names.
            cath = [n for n, s in names.items() if re.match(r'^(K|C|-|CATHODE|NEG)', s, re.I)]
            if len(cath) == 1:
                an = [n for n in jp if n != cath[0]][0]
                pairs = [('1', cath[0]), ('2', an)]
                how = 'K=%s' % cath[0]
            else:
                how = 'K=?'
        if len(pairs) < 2:
            pairs, how = [], 'geom'
        d, t, err = fit(kp, jp, pairs, lambda d: body_ok(kfp, jfp, d))
        if err > 0.3 and pairs:
            # pad numbers disagree with the body side (e.g. a mirrored-numbered symmetric header):
            # fall back to a geometric fit
            pairs, how = [], 'geom'
            d, t, err = fit(kp, jp, pairs, lambda d: body_ok(kfp, jfp, d))
        result[lcsc] = {'footprint': name, 'jlc_footprint': os.path.basename(mods[0])[:-10],
                        'rotation': d, 'offset': [round(t[0], 4), round(t[1], 4)], 'match': how,
                        'max_pad_error': round(err, 3)}
        print('%-9s %-42s %-6s %-5d (%5.2f,%5.2f) %-6.3f %s' % (lcsc, name, how, d, t[0], t[1], err,
                                                                  os.path.basename(mods[0])[:-10]))
    with open(os.path.join(GEN, 'jlc_rot.json'), 'w') as f:
        json.dump(dict(sorted(result.items())), f, indent=1)
        f.write('\n')
    print('wrote', os.path.join(GEN, 'jlc_rot.json'))
    return result


if __name__ == '__main__':
    main()
