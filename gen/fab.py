#!/usr/bin/env python3
"""Fabrication outputs for JLCPCB: gerbers+drill zip, BOM, CPL, schematic PDF, renders.

python3 gen/fab.py [--boards N]
"""
import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pcbnew

GEN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GEN)
ROOT = os.path.normpath(os.path.join(GEN, '..'))
HW = os.path.join(ROOT, 'hw')
FAB = os.path.join(ROOT, 'fab')
PCB = os.path.join(HW, 'sbc-uart-hub.kicad_pcb')
SCH = os.path.join(HW, 'sbc-uart-hub.kicad_sch')

# Per-LCSC rotation/offset onto JLC's own footprints, measured by gen/jlc_rot.py.
JLC_ROT = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jlc_rot.json')))


def kicad_rot(p, deg):
    # KiCad orientation: positive = counter-clockwise on screen (y axis down)
    a = math.radians(deg)
    return (p[0] * math.cos(a) + p[1] * math.sin(a), -p[0] * math.sin(a) + p[1] * math.cos(a))


def run(*a):
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def gerbers():
    g = os.path.join(FAB, 'gerbers')
    shutil.rmtree(g, ignore_errors=True)
    os.makedirs(g)
    run('kicad-cli', 'pcb', 'export', 'gerbers', '-o', g + '/', '--layers',
        'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts',
        '--subtract-soldermask', PCB)
    run('kicad-cli', 'pcb', 'export', 'drill', '-o', g + '/', '--format', 'excellon', '--excellon-units', 'mm',
        '--excellon-separate-th', PCB)
    z = os.path.join(FAB, 'sbc-uart-hub-gerbers.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(g)):
            zf.write(os.path.join(g, f), f)
    return z


def bom_cpl(boards):
    board = pcbnew.LoadBoard(PCB)
    groups = {}
    cpl = []
    for fp in board.GetFootprints():
        a = fp.GetAttributes()
        if fp.IsDNP() or a & pcbnew.FP_EXCLUDE_FROM_BOM:
            continue
        lcsc = fp.GetFieldText('LCSC') if fp.HasFieldByName('LCSC') else ''
        if not lcsc:
            raise SystemExit('no LCSC field on ' + fp.GetReference())
        name = fp.GetFPID().GetLibItemName().wx_str()
        key = (lcsc, fp.GetValue(), name)
        groups.setdefault(key, []).append(fp.GetReference())
        if a & pcbnew.FP_EXCLUDE_FROM_POS_FILES:
            continue
        pos = fp.GetPosition()
        phi = fp.GetOrientationDegrees()
        if lcsc not in JLC_ROT:
            raise SystemExit('%s (%s) not in jlc_rot.json, run gen/jlc_rot.py' % (lcsc, fp.GetReference()))
        j = JLC_ROT[lcsc]
        tx, ty = kicad_rot(j['offset'], phi)
        x, y = pcbnew.ToMM(pos.x) + tx, pcbnew.ToMM(pos.y) + ty
        cpl.append((fp.GetReference(), x, -y, 'Top' if fp.GetLayer() == pcbnew.F_Cu else 'Bottom',
                    (phi + j['rotation']) % 360))
    nat = lambda r: (re.sub(r'\d', '', r), int(re.sub(r'\D', '', r) or 0))
    with open(os.path.join(FAB, 'bom_jlc.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #', 'Qty'])
        for (lcsc, val, name), refs in sorted(groups.items(), key=lambda kv: nat(sorted(kv[1], key=nat)[0])):
            w.writerow([val, ','.join(sorted(refs, key=nat)), name, lcsc, len(refs)])
    with open(os.path.join(FAB, 'cpl_jlc.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for r in sorted(cpl, key=lambda r: nat(r[0])):
            w.writerow([r[0], '%.4fmm' % r[1], '%.4fmm' % r[2], r[3], '%g' % r[4]])
    return groups


def stock_check(groups, boards):
    import jlc
    bad = []
    total = 0.0
    for (lcsc, val, name), refs in sorted(groups.items()):
        need = len(refs) * boards
        hits = [c for c in jlc.search(lcsc, 5) if c.get('componentCode') == lcsc]
        st = hits[0].get('stockCount') if hits else 0
        price = 0.0
        if hits:
            for pr in hits[0].get('componentPrices') or []:
                if pr['startNumber'] <= need and (pr['endNumber'] == -1 or need <= pr['endNumber']):
                    price = pr['productPrice']
            lib = hits[0].get('componentLibraryType')
        else:
            lib = '?'
        total += price * need
        flag = '' if st and st >= 10 * need else '  <-- LOW STOCK'
        print('%-9s %-5s %-22s need %4d stock %-8s $%.4f%s' % (lcsc, lib, val[:22], need, st, price, flag))
        if flag:
            bad.append(lcsc)
    print('approx. component cost for %d boards: $%.2f' % (boards, total))
    return bad


def docs():
    run('kicad-cli', 'sch', 'export', 'pdf', '-o', os.path.join(FAB, 'sbc-uart-hub-schematic.pdf'), SCH)
    for side in ('top', 'bottom'):
        subprocess.run(['kicad-cli', 'pcb', 'render', '--side', side, '--width', '2400', '--height', '1700',
                        '--quality', 'high', '-o', os.path.join(FAB, 'render-%s.png' % side), PCB],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--boards', type=int, default=5)
    ap.add_argument('--no-stock', action='store_true')
    ap.add_argument('--no-docs', action='store_true')
    a = ap.parse_args()
    os.makedirs(FAB, exist_ok=True)
    z = gerbers()
    groups = bom_cpl(a.boards)
    print('gerbers:', z)
    print('BOM lines:', len(groups), ' placements:', sum(len(v) for v in groups.values()))
    if not a.no_docs:
        docs()
    if not a.no_stock:
        bad = stock_check(groups, a.boards)
        if bad:
            sys.exit('stock problems: ' + ' '.join(bad))


if __name__ == '__main__':
    main()
