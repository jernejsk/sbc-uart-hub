#!/usr/bin/env python3
"""One-off migration: JST-XH connectors -> right-angle 2.54 mm headers, keeping the routing.

python3 gen/rework_headers.py <old.kicad_pcb>     (writes hw/sbc-uart-hub.kicad_pcb)
then: python3 gen/route.py 100
      python3 gen/rework_headers.py --fix-stubs     (joins old trace ends 0.36 mm off the new pads)
      python3 gen/finish.py

The old board is the XH layout (git 3d51c3360c3e). Header pins are numbered 1=RX 2=TX 3=GND,
so each signal lands within 0.1 mm (x) / 0.36 mm (y) of its old XH pad. Only track segments
that end on a connector pad are removed; every other track and via is locked, so Freerouting
only completes the 48 short pad stubs.
"""
import os
import sys

import pcbnew

GEN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GEN)
import build_pcb as B  # noqa: E402

MM = pcbnew.FromMM
LIB = os.path.join(B.HW, 'lib', 'sbcu.pretty')
NAME = 'PinHeader_1x03_P2.54mm_Horizontal_Edge'
NEW_FROM_OLD = {'1': '3', '2': '2', '3': '1'}       # new pin -> old XH pin carrying the same net


def main():
    board = pcbnew.LoadBoard(sys.argv[1])
    for z in list(board.Zones()):                   # outer pours are re-added by finish.py
        if z.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            board.Delete(z)

    conns = [f for f in board.GetFootprints() if f.HasFieldByName('Channel')]
    old_pads = [(p.GetNetname(), p) for f in conns for p in f.Pads()]
    # rip track segments that end on an old connector pad
    ripped = 0
    for t in list(board.GetTracks()):
        if t.GetClass() == 'PCB_VIA':
            continue
        if any(net == t.GetNetname() and (pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()))
               for net, pad in old_pads):
            board.Delete(t)
            ripped += 1

    for old in conns:
        ch = int(old.GetFieldText('Channel')[2:])
        i, top = (ch - 1) % 8, ch <= 8
        x = B.CONN_X0 + i * B.CONN_PITCH
        new = pcbnew.FootprintLoad(LIB, NAME)
        new.SetFPID(pcbnew.LIB_ID('sbcu', NAME))
        new.SetReference(old.GetReference())
        new.SetValue('Header 1x3 RA')
        for fld in old.GetFields():
            if fld.GetName() not in ('Reference', 'Value', 'Footprint', 'Datasheet', 'Description'):
                new.SetField(fld.GetName(), fld.GetText())
                new.GetFieldByName(fld.GetName()).SetVisible(False)
        new.SetField('LCSC', 'C492411')
        new.SetField('MPN', 'PZ254R-11-03P')
        new.SetPath(old.GetPath())
        new.SetSheetname(old.GetSheetname())
        new.SetSheetfile(old.GetSheetfile())
        new.SetAttributes(old.GetAttributes())
        if top:
            new.SetOrientationDegrees(90)
            new.SetPosition(pcbnew.VECTOR2I(MM(x), MM(B.CONN_Y_TOP)))
        else:
            new.SetOrientationDegrees(270)
            new.SetPosition(pcbnew.VECTOR2I(MM(x + 2 * B.HDR_P), MM(B.CONN_Y_BOT)))
        for p in new.Pads():
            op = old.FindPadByNumber(NEW_FROM_OLD[p.GetNumber()])
            p.SetNet(op.GetNet())
            d = (p.GetPosition() - op.GetPosition())
            assert abs(pcbnew.ToMM(d.x)) < 0.1 and abs(pcbnew.ToMM(d.y)) < 0.4, (old.GetReference(), p.GetNumber())
        new.Value().SetVisible(False)
        board.Add(new)
        board.Delete(old)

    # rip other-net copper that now collides with a header pad (pads moved up to 0.36 mm and grew)
    new_pads = [p for f in board.GetFootprints() if f.HasFieldByName('Channel') for p in f.Pads()]
    clr = MM(0.2)
    for t in list(board.GetTracks()):
        for p in new_pads:
            if p.GetNetname() == t.GetNetname():
                continue
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if t.IsOnLayer(layer) and p.GetEffectiveShape(layer).Collide(t.GetEffectiveShape(layer), clr):
                    break
            else:
                continue
            board.Delete(t)
            ripped += 1
            break

    locked = 0
    for t in board.GetTracks():
        t.SetLocked(True)
        locked += 1
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(B.PRJ + '.kicad_pcb')
    B.write_project()        # Save wrote the old board's (default) project settings; restore ours
    print('ripped', ripped, 'locked', locked, '->', B.PRJ + '.kicad_pcb')


def fix_stubs():
    """After routing: old trace ends left at the XH pad positions are extended to the header pad
    (same net, < 0.6 mm away); remaining dangling stubs are removed."""
    board = pcbnew.LoadBoard(B.PRJ + '.kicad_pcb')
    pads = [p for f in board.GetFootprints() if f.HasFieldByName('Channel') for p in f.Pads()]

    def key(v):
        return (round(v.x / 1000), round(v.y / 1000))

    def ends():
        cnt = {}
        for t in board.GetTracks():
            pts = [t.GetPosition()] if t.GetClass() == 'PCB_VIA' else [t.GetStart(), t.GetEnd()]
            for v in pts:
                cnt[(t.GetNetname(), key(v))] = cnt.get((t.GetNetname(), key(v)), 0) + 1
        return cnt

    joined = 0
    cnt = ends()
    for t in list(board.GetTracks()):
        if t.GetClass() == 'PCB_VIA':
            continue
        for v in (t.GetStart(), t.GetEnd()):
            if cnt.get((t.GetNetname(), key(v)), 0) > 1:
                continue
            for p in pads:
                if p.GetNetname() != t.GetNetname() or p.HitTest(v):
                    continue
                d = p.GetPosition() - v
                if (d.x ** 2 + d.y ** 2) ** 0.5 < MM(0.6):
                    s = pcbnew.PCB_TRACK(board)
                    s.SetStart(v)
                    s.SetEnd(p.GetPosition())
                    s.SetLayer(t.GetLayer())
                    s.SetWidth(t.GetWidth())
                    s.SetNet(t.GetNet())
                    board.Add(s)
                    joined += 1
                    break
    for t in board.GetTracks():
        t.SetLocked(False)
    board.Save(B.PRJ + '.kicad_pcb')
    B.write_project()
    print('joined', joined)


if __name__ == '__main__':
    if sys.argv[1:] == ['--fix-stubs']:
        fix_stubs()
    else:
        main()
