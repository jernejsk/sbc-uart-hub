#!/usr/bin/env python3
"""Post-route finishing: silkscreen, outer-layer GND pours, zone fill.

python3 gen/finish.py      (operates on hw/sbc-uart-hub.kicad_pcb in place)
"""
import os
import sys

import pcbnew

GEN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GEN)
import build_pcb as B  # noqa: E402

MM = pcbnew.FromMM
PCB = B.PRJ + '.kicad_pcb'
TAG = 'sbcu-finish'          # marks items we add, so re-running is idempotent


def text(board, s, x, y, layer, size=1.0, thick=0.15, rot=0, mirror=False, just=None):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(thick))
    t.SetTextAngleDegrees(rot)
    if mirror:
        t.SetMirrored(True)
    if just == 'left':
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    board.Add(t)
    return t


def rect(board, x0, y0, x1, y1, layer, w=0.15):
    r = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
    r.SetStart(pcbnew.VECTOR2I(MM(x0), MM(y0)))
    r.SetEnd(pcbnew.VECTOR2I(MM(x1), MM(y1)))
    r.SetLayer(layer)
    r.SetWidth(MM(w))
    board.Add(r)


def clear_previous(board):
    for d in list(board.GetDrawings()):
        if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            board.Delete(d)
    for z in list(board.Zones()):
        if z.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            board.Delete(z)


def silkscreen(board):
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pfx = ref.rstrip('0123456789')
        r = fp.Reference()
        r.SetVisible((pfx == 'U' and fp.GetValue() != 'USBLC6-2SC6') or ref == 'J1')
        if pfx == 'U':
            r.SetTextAngleDegrees(0)
            if fp.GetValue() in ('FT4232HL', '74LVC125APW'):
                r.SetPosition(fp.GetPosition())
            else:
                bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
                r.SetPosition(pcbnew.VECTOR2I(bb.GetCenter().x, bb.GetTop() - MM(0.6)))
            big = fp.GetValue() in ('FT4232HL', 'USB2514B')
            sz = 1.2 if big else 0.6
            r.SetTextSize(pcbnew.VECTOR2I(MM(sz), MM(sz)))
            r.SetTextThickness(MM(0.15 if big else 0.1))
        if ref == 'J1':
            for pad in fp.Pads():
                if pad.GetNumber() == 'S1':
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        fp.Value().SetVisible(False)

    # channel labels (front) + write-on boxes (back)
    for fp in board.GetFootprints():
        ch = fp.GetFieldText('Channel') if fp.HasFieldByName('Channel') else ''
        if not ch:
            continue
        n = int(ch[2:])
        p1 = fp.FindPadByNumber('1').GetPosition()
        p3 = fp.FindPadByNumber('3').GetPosition()
        cx = pcbnew.ToMM(p1.x + p3.x) / 2
        py = pcbnew.ToMM(p1.y)
        top = n <= 8
        sgn = 1 if top else -1
        text(board, ch, cx, py + sgn * 3.9, pcbnew.F_SilkS, size=1.0, thick=0.18)
        # back side: write-on box with pin legend, mirrored
        by0 = py + sgn * 2.2
        by1 = py + sgn * 10.0
        rect(board, cx - 5.9, min(by0, by1), cx + 5.9, max(by0, by1), pcbnew.B_SilkS)
        text(board, '%s  GND TX RX' % ch if not top else '%s  RX TX GND' % ch, cx, py + sgn * 3.5,
             pcbnew.B_SilkS, size=0.7, thick=0.12, mirror=True)

    # front legend
    text(board, 'SBC UART HUB  rev A', 9.0, 88.5, pcbnew.F_SilkS, size=1.2, thick=0.2, just='left')
    text(board, '16x UART: USB2514B + 4x FT4232H', 9.0, 90.6, pcbnew.F_SilkS, size=0.8, thick=0.13, just='left')
    text(board, 'XH: 1=GND(sq) 2=TX out 3=RX in', 9.0, 92.3, pcbnew.F_SilkS, size=0.8, thick=0.13,
         just='left')
    text(board, 'LED = port open (DTR), TX gated', 13.0, 7.0, pcbnew.F_SilkS, size=0.8, thick=0.13)
    text(board, 'USB', 2.0, 42.5, pcbnew.F_SilkS, size=1.0, thick=0.18, rot=90)
    # back legend
    text(board, 'SBC UART HUB rev A - write labgrid place names in the boxes', B.BW / 2, B.BH / 2 - 3,
         pcbnew.B_SilkS, size=1.2, thick=0.2, mirror=True)
    text(board, 'ttyUSB order: FT1=CH01-04 FT2=CH05-08 FT3=CH09-12 FT4=CH13-16 (EEPROM serial SBCU-n)',
         B.BW / 2, B.BH / 2, pcbnew.B_SilkS, size=0.9, thick=0.15, mirror=True)
    text(board, 'TX is Hi-Z unless the port is open (DTR asserted). No VCC on the DUT cable.',
         B.BW / 2, B.BH / 2 + 2.5, pcbnew.B_SilkS, size=0.9, thick=0.15, mirror=True)


def pours(board):
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = B.add_zone(board, 'GND', layer, prio=0, clearance=0.3, inset=0.5)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)


def clean_dangling(board):
    """Remove autorouter leftovers: signal vias used on one layer only and
    unlocked track stubs with a free end."""
    plane = ('GND', '+3V3')

    def key(p):
        return (round(p.x / 1000), round(p.y / 1000))     # 1 um grid

    removed = 0
    for _ in range(10):
        pads = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                pads.setdefault(pad.GetNetname(), []).append(pad)
        ends = {}
        for t in board.GetTracks():
            if t.GetClass() == 'PCB_VIA':
                continue
            for p in (t.GetStart(), t.GetEnd()):
                ends.setdefault((t.GetNetname(), key(p)), []).append(t)
        vias = {(v.GetNetname(), key(v.GetPosition())): v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA'}
        kill = []
        for (net, k), v in vias.items():
            if net in plane or v.IsLocked():
                continue
            layers = {t.GetLayer() for t in ends.get((net, k), [])}
            if any(pad.HitTest(v.GetPosition()) for pad in pads.get(net, [])):
                layers.add(pcbnew.F_Cu)
            if len(layers) < 2:
                kill.append(v)
        for t in board.GetTracks():
            if t.GetClass() == 'PCB_VIA' or t.IsLocked():
                continue
            net = t.GetNetname()
            for p in (t.GetStart(), t.GetEnd()):
                k = key(p)
                if len(ends.get((net, k), [])) > 1 or (net, k) in vias:
                    continue
                if any(pad.HitTest(p) and pad.IsOnLayer(t.GetLayer()) for pad in pads.get(net, [])):
                    continue
                kill.append(t)
                break
        if not kill:
            break
        seen = set()
        for item in kill:
            k = item.m_Uuid.AsString()
            if k in seen:
                continue
            seen.add(k)
            board.Delete(item)
            removed += 1
    return removed


def main():
    board = pcbnew.LoadBoard(PCB)
    B.write_project()
    comps, _ = B.read_netlist()
    for c in comps:
        fp = board.FindFootprintByReference(c['ref'])
        if fp and 'dnp' in c['props']:
            fp.SetDNP(True)
        if fp:
            fp.SetValue(c['value'])
    clear_previous(board)
    print('removed dangling items:', clean_dangling(board))
    silkscreen(board)
    pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print('finished', PCB)


if __name__ == '__main__':
    main()
