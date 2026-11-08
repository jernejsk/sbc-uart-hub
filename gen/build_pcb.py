#!/usr/bin/env python3
"""Build hw/sbc-uart-hub.kicad_pcb from the schematic netlist.

Stages (each can be re-run, the board is rebuilt from scratch every time):
  1. netlist -> footprints + nets
  2. scripted placement (rule based + pin-affinity for passives)
  3. outline, zones, silkscreen
  4. scripted USB 2.0 differential pairs
  5. Freerouting for everything else (see route.sh)
"""
import json
import math
import os
import subprocess
import sys

import pcbnew

GEN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GEN)
from sexp import find, find1, parse  # noqa: E402

HW = os.path.normpath(os.path.join(GEN, '..', 'hw'))
PRJ = os.path.join(HW, 'sbc-uart-hub')
FPDIR = '/usr/share/kicad/footprints'
MM = pcbnew.FromMM

# board geometry -----------------------------------------------------------
BW, BH = 146.0, 100.0
CONN_X0, CONN_PITCH = 34.0, 13.5        # first connector x (leftmost pin), pitch
# Header pins: 1=GND 2=TX 3=RX. The project footprint (gen/mkfp.py) numbers its pads the
# mirror of the stock one, so each signal sits where it was on the rev A JST-XH layout
# (x within 0.1 mm) and the routing could be kept from that layout.
# right-angle 2.54 mm headers: plastic body (1.5..4.04 mm behind the pads) flush with the board edge,
# pins overhang the edge by ~6 mm
HDR_P = 2.54
CONN_Y_TOP, CONN_Y_BOT = 4.04, BH - 4.04
FT_POS = {1: (52.0, 34.0, 180), 2: (106.0, 34.0, 180), 3: (52.0, 66.0, 0), 4: (106.0, 66.0, 0)}
HUB_POS = (22.0, 50.0, 180)
USB_C_POS = (4.2, 50.0, -90)

USB_W, USB_GAP = 0.22, 0.15             # 90R diff, JLC04161H-7628 (verify)
POWER_NETS = ('GND', '+3V3', '+5V', 'VBUS')


def write_project():
    pro = {
        'board': {
            'design_settings': {
                'defaults': {'board_outline_line_width': 0.1, 'copper_line_width': 0.2,
                             'silk_line_width': 0.15, 'silk_text_size_h': 0.8, 'silk_text_size_v': 0.8,
                             'silk_text_thickness': 0.15},
                'rules': {'min_clearance': 0.127, 'min_track_width': 0.1, 'min_via_diameter': 0.45,
                          'min_via_annular_width': 0.1, 'min_through_hole_diameter': 0.25,
                          'min_hole_to_hole': 0.25, 'min_hole_clearance': 0.25,
                          'min_copper_edge_clearance': 0.3, 'min_silk_clearance': 0.0,
                          'min_text_height': 0.6, 'min_text_thickness': 0.1, 'solder_mask_to_copper_clearance': 0.0,
                          'max_error': 0.005},
                'track_widths': [0.0, 0.2, 0.3, 0.5, 0.8],
                'via_dimensions': [{'diameter': 0.0, 'drill': 0.0}, {'diameter': 0.6, 'drill': 0.3},
                                   {'diameter': 0.8, 'drill': 0.4}],
                'diff_pair_dimensions': [{'gap': 0.0, 'via_gap': 0.0, 'width': 0.0},
                                         {'gap': USB_GAP, 'via_gap': 0.25, 'width': USB_W}],
            },
        },
        'meta': {'filename': 'sbc-uart-hub.kicad_pro', 'version': 3},
        'net_settings': {
            'classes': [
                dict(name='Default', clearance=0.15, track_width=0.2, via_diameter=0.6, via_drill=0.3,
                     diff_pair_width=USB_W, diff_pair_gap=USB_GAP, diff_pair_via_gap=0.25,
                     microvia_diameter=0.3, microvia_drill=0.1, bus_width=12, line_style=0, wire_width=6,
                     pcb_color='rgba(0, 0, 0, 0.000)', schematic_color='rgba(0, 0, 0, 0.000)',
                     priority=2147483647),
                dict(name='Power', clearance=0.15, track_width=0.3, via_diameter=0.6, via_drill=0.3,
                     diff_pair_width=USB_W, diff_pair_gap=USB_GAP, diff_pair_via_gap=0.25,
                     microvia_diameter=0.3, microvia_drill=0.1, bus_width=12, line_style=0, wire_width=6,
                     pcb_color='rgba(0, 0, 0, 0.000)', schematic_color='rgba(0, 0, 0, 0.000)', priority=0),
                dict(name='Supply', clearance=0.2, track_width=0.6, via_diameter=0.8, via_drill=0.4,
                     diff_pair_width=USB_W, diff_pair_gap=USB_GAP, diff_pair_via_gap=0.25,
                     microvia_diameter=0.3, microvia_drill=0.1, bus_width=12, line_style=0, wire_width=6,
                     pcb_color='rgba(0, 0, 0, 0.000)', schematic_color='rgba(0, 0, 0, 0.000)', priority=0),
                dict(name='USB', clearance=0.15, track_width=USB_W, via_diameter=0.6, via_drill=0.3,
                     diff_pair_width=USB_W, diff_pair_gap=USB_GAP, diff_pair_via_gap=0.25,
                     microvia_diameter=0.3, microvia_drill=0.1, bus_width=12, line_style=0, wire_width=6,
                     pcb_color='rgba(0, 0, 0, 0.000)', schematic_color='rgba(0, 0, 0, 0.000)', priority=1),
            ],
            'meta': {'version': 4},
            'net_colors': None,
            'netclass_assignments': None,
            'netclass_patterns': [
                {'netclass': 'Power', 'pattern': n} for n in ('GND', '+3V3', '*_1V8', '*_VPHY', '*_VPLL')
            ] + [{'netclass': 'Supply', 'pattern': n} for n in ('+5V', 'VBUS', '/Power/BUCK_SW')] + [{'netclass': 'USB', 'pattern': p} for p in ('*_DP', '*_DM')],
        },
        'schematic': {'legacy_lib_dir': '', 'legacy_lib_list': []},
        'sheets': [],
        'text_variables': {},
    }
    with open(PRJ + '.kicad_pro', 'w') as f:
        json.dump(pro, f, indent=2)


def read_netlist():
    path = os.path.join(HW, 'build', 'netlist.net')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', path,
                    PRJ + '.kicad_sch'], check=True, stdout=subprocess.DEVNULL)
    n = parse(open(path).read())
    comps = []
    for c in find(find1(n, 'components'), 'comp'):
        fields = {}
        fl = find1(c, 'fields')
        if fl:
            for f in find(fl, 'field'):
                fields[find1(f, 'name')[1]] = f[2] if len(f) > 2 else ''
        props = {find1(p, 'name')[1]: (find1(p, 'value')[1] if find1(p, 'value') else '')
                 for p in find(c, 'property')}
        sp = find1(c, 'sheetpath')
        comps.append(dict(ref=find1(c, 'ref')[1], value=find1(c, 'value')[1],
                          fp=find1(c, 'footprint')[1] if find1(c, 'footprint') else '',
                          fields=fields, props=props, sheet=find1(sp, 'names')[1], sheet_ts=find1(sp, 'tstamps')[1],
                          uuid=find1(c, 'tstamps')[1]))
    nets = []
    for net in find(find1(n, 'nets'), 'net'):
        nets.append((find1(net, 'name')[1], [(find1(x, 'ref')[1], find1(x, 'pin')[1]) for x in find(net, 'node')]))
    return comps, nets


# --------------------------------------------------------------------------

class Placer:
    def __init__(self, board, comps, nets):
        self.b = board
        self.comps = {c['ref']: c for c in comps}
        self.fps = {}
        self.netmap = {}
        self.pin_net = {}          # (ref, pin) -> short net name
        self.net_nodes = {}
        self.boxes = []            # occupied rects (x0,y0,x1,y1) mm
        self.placed = set()
        for name, nodes in nets:
            short = name.split('/')[-1]
            self.net_nodes[name] = nodes
            for r, p in nodes:
                self.pin_net[(r, p)] = name

    # ---- footprints / nets
    def build(self):
        for name in self.net_nodes:
            ni = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(ni)
            self.netmap[name] = ni
        for ref, c in sorted(self.comps.items()):
            if not c['fp']:
                continue
            lib, name = c['fp'].split(':')
            libdir = os.path.join(HW, 'lib', lib + '.pretty') if lib == 'sbcu' else os.path.join(FPDIR, lib + '.pretty')
            fp = pcbnew.FootprintLoad(libdir, name)
            fp.SetFPID(pcbnew.LIB_ID(lib, name))
            fp.SetReference(ref)
            fp.SetValue(c['value'])
            for k in ('LCSC', 'MPN', 'Channel'):
                if k in c['fields']:
                    fp.SetField(k, c['fields'][k])
                    fp.GetFieldByName(k).SetVisible(False)
            fp.SetPath(pcbnew.KIID_PATH(c['sheet_ts'] + c['uuid']))
            fp.SetSheetname(c['sheet'].strip('/').split('/')[-1] if c['sheet'] != '/' else '')
            fp.SetSheetfile(c['sheet'].strip('/').lower() + '.kicad_sch')
            attrs = fp.GetAttributes()
            if 'dnp' in c['props'] or ref.startswith('H'):
                attrs |= pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
            fp.SetAttributes(attrs)
            if 'dnp' in c['props']:
                fp.SetDNP(True)
            fp.Reference().SetTextSize(pcbnew.VECTOR2I(MM(0.6), MM(0.6)))
            fp.Reference().SetTextThickness(MM(0.1))
            self.b.Add(fp)
            self.fps[ref] = fp
        for name, nodes in self.net_nodes.items():
            for r, p in nodes:
                fp = self.fps.get(r)
                if not fp:
                    continue
                for pad in fp.Pads():
                    if pad.GetNumber() == p:
                        pad.SetNet(self.netmap[name])

    # ---- geometry helpers
    def bbox(self, fp):
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
        return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()),
                pcbnew.ToMM(bb.GetBottom()))

    def free(self, box, margin=0.15):
        x0, y0, x1, y1 = box
        if x0 < 0.6 or y0 < 0.6 or x1 > BW - 0.6 or y1 > BH - 0.6:
            return False
        for a in self.boxes:
            if x0 < a[2] + margin and x1 > a[0] - margin and y0 < a[3] + margin and y1 > a[1] - margin:
                return False
        return True

    def put(self, ref, x, y, rot=0, force=False, keep=True):
        fp = self.fps[ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        box = self.bbox(fp)
        if not force and not self.free(box):
            return False
        if keep:
            self.boxes.append(box)
        self.placed.add(ref)
        return True

    def reserve(self, x0, y0, x1, y1):
        self.boxes.append((x0, y0, x1, y1))

    def pad_pos(self, ref, pin):
        for pad in self.fps[ref].Pads():
            if pad.GetNumber() == pin:
                p = pad.GetPosition()
                return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
        raise KeyError((ref, pin))

    def pad_net(self, ref, pin):
        for pad in self.fps[ref].Pads():
            if pad.GetNumber() == pin:
                return pad.GetNet()
        raise KeyError((ref, pin))

    def near(self, ref, ax, ay, nx, ny, rot=None, start=1.2, maxd=14.0):
        """Place ref as close as possible to (ax,ay) going outward along (nx,ny),
        sliding tangentially."""
        if rot is None:
            rot = 0 if abs(nx) > abs(ny) else 90
        tx, ty = -ny, nx
        d = start
        while d < maxd:
            for k in range(0, 40):
                off = ((k + 1) // 2) * 0.55 * (1 if k % 2 else -1)
                x = ax + nx * d + tx * off
                y = ay + ny * d + ty * off
                if self.put(ref, x, y, rot):
                    return True
            d += 0.5
        return False

    def fallback(self, ref, cx, cy):
        for r in range(0, 60):
            for a in range(0, 360, 20):
                x = cx + r * 0.7 * math.cos(math.radians(a))
                y = cy + r * 0.7 * math.sin(math.radians(a))
                if self.put(ref, x, y, 0):
                    return True
        raise RuntimeError('cannot place ' + ref)


def outward(placer, ic, pin):
    """unit normal pointing from IC centre towards pin side."""
    fp = placer.fps[ic]
    c = fp.GetPosition()
    cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
    px, py = placer.pad_pos(ic, pin)
    dx, dy = px - cx, py - cy
    if abs(dx) > abs(dy):
        return (1 if dx > 0 else -1), 0
    return 0, (1 if dy > 0 else -1)


def short(n):
    return n.split('/')[-1]


# --------------------------------------------------------------------------
# USB 2.0 downstream pairs (hub -> FT).  Both chips number DM before DP
# counter-clockwise, so every pair needs a polarity swap: DP dives to B.Cu
# and crosses under DM in the FT breakout.

HALF = (USB_W + USB_GAP) / 2
# lane: FT -> (x of vertical run, list of centre-line points after the hub)
LANE_X = {1: 68.0, 2: 122.0, 4: 91.0, 3: 37.0}
HUB_FT_PINS = {1: ('9', '8'), 2: ('7', '6'), 4: ('4', '3'), 3: ('2', '1')}   # (DP, DM) on hub
BREAK_START = (-13.0, -0.5)


def ft_xform(ft_n):
    x, y, rot = FT_POS[ft_n]
    if rot == 180:
        return lambda p: (x - p[0], y - p[1])
    return lambda p: (x + p[0], y + p[1])


def lane_centre(P, ft_n, hub):
    dp, dm = HUB_FT_PINS[ft_n]
    (_, ydp), (_, ydm) = P.pad_pos(hub, dp), P.pad_pos(hub, dm)
    yc = (ydp + ydm) / 2
    xv = LANE_X[ft_n]
    ex, ey = ft_xform(ft_n)(BREAK_START)
    up = ey < yc
    s = -1 if up else 1
    toward = 1 if ex < xv else -1        # final horizontal direction sign (from xv to ex)
    pts = [(26.0, yc), (xv - 1.5, yc), (xv, yc + s * 1.5), (xv, ey - s * 1.5), (xv + toward * 1.5, ey), (ex, ey)]
    return pts


def offset_poly(pts, d):
    """offset to the left of travel by d (screen coords, y down)."""
    out = []
    norms = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        dx, dy = (x1 - x0) / L, (y1 - y0) / L
        norms.append((dy, -dx))
    for i, (x, y) in enumerate(pts):
        if i == 0:
            n = norms[0]
            out.append((x + n[0] * d, y + n[1] * d))
        elif i == len(pts) - 1:
            n = norms[-1]
            out.append((x + n[0] * d, y + n[1] * d))
        else:
            a, b = norms[i - 1], norms[i]
            k = 1 + a[0] * b[0] + a[1] * b[1]
            out.append((x + (a[0] + b[0]) / k * d, y + (a[1] + b[1]) / k * d))
    return out


BREAKOUT = {
    'dp_top1': [(-13.0, -0.5 - HALF), (-12.4, -0.5 - HALF), (-11.7, -1.385)],
    'dp_bot': [(-11.7, -1.385), (-9.565, 0.75)],
    'dp_top2': [(-9.565, 0.75), (-8.565, -0.25), (-5.67, -0.25)],
    'dm': [(-13.0, -0.5 + HALF), (-9.2, -0.5 + HALF), (-8.765, -0.75), (-5.67, -0.75)],
    'vias': [(-11.7, -1.385), (-9.565, 0.75)],
    'box': (-13.6, -2.1, -7.4, 1.5),
}


def usb_reserve(P, hub):
    for ft_n in (1, 2, 3, 4):
        pts = lane_centre(P, ft_n, hub)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            P.reserve(min(x0, x1) - 0.8, min(y0, y1) - 0.8, max(x0, x1) + 0.8, max(y0, y1) + 0.8)
        xf = ft_xform(ft_n)
        bx0, by0, bx1, by1 = BREAKOUT['box']
        (ax, ay), (cx, cy) = xf((bx0, by0)), xf((bx1, by1))
        P.reserve(min(ax, cx), min(ay, cy), max(ax, cx), max(ay, cy))
    # hub VDDA33 (pin 5) escape via between the lanes
    P.reserve(24.5, 49.4, 27.2, 50.6)


def add_track(board, net, pts, layer, width):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(MM(x0), MM(y0)))
        t.SetEnd(pcbnew.VECTOR2I(MM(x1), MM(y1)))
        t.SetLayer(layer)
        t.SetWidth(MM(width))
        t.SetNet(net)
        t.SetLocked(True)
        board.Add(t)


def add_via(board, net, x, y, dia=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    v.SetWidth(MM(dia))
    v.SetDrill(MM(drill))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    v.SetLocked(True)
    board.Add(v)


def j1_vbus(board, P, j1='J1'):
    """Tie the two USB-C VBUS pad pairs (A4/B9 and A9/B4) together: short F.Cu stubs to
    vias and a B.Cu link. The autorouter tends to leave this connection open."""
    net = P.board_net('VBUS') if hasattr(P, 'board_net') else board.FindNet('VBUS')
    (xa, ya), (xb, yb) = P.pad_pos(j1, 'A4'), P.pad_pos(j1, 'A9')
    vx = xa + 1.25
    for y in (ya, yb):
        add_track(board, net, [(xa, y), (vx, y)], pcbnew.F_Cu, 0.45)
        add_via(board, net, vx, y)
    add_track(board, net, [(vx, ya), (vx, yb)], pcbnew.B_Cu, 0.6)


def usb_route(board, P, hub):
    for ft_n in (1, 2, 3, 4):
        dp_pin, dm_pin = HUB_FT_PINS[ft_n]
        dpn = P.pad_net(hub, dp_pin)
        dmn = P.pad_net(hub, dm_pin)
        ftref = P.ft_ref[ft_n]
        assert P.pad_net(ftref, '8').GetNetname() == dpn.GetNetname() and P.pad_net(ftref, '7').GetNetname() == dmn.GetNetname(), (ft_n, dpn.GetNetname())
        pts = lane_centre(P, ft_n, hub)
        dp = offset_poly(pts, HALF)
        dm = offset_poly(pts, -HALF)
        hx, hyp = P.pad_pos(hub, dp_pin)
        _, hym = P.pad_pos(hub, dm_pin)
        dp = [(hx, hyp), (25.6, hyp)] + dp
        dm = [(hx, hym), (25.6, hym)] + dm
        xf = ft_xform(ft_n)
        add_track(board, dpn, dp, pcbnew.F_Cu, USB_W)
        add_track(board, dmn, dm, pcbnew.F_Cu, USB_W)
        add_track(board, dpn, [xf(p) for p in BREAKOUT['dp_top1']], pcbnew.F_Cu, USB_W)
        add_track(board, dpn, [xf(p) for p in BREAKOUT['dp_bot']], pcbnew.B_Cu, USB_W)
        add_track(board, dpn, [xf(p) for p in BREAKOUT['dp_top2']], pcbnew.F_Cu, USB_W)
        add_track(board, dmn, [xf(p) for p in BREAKOUT['dm']], pcbnew.F_Cu, USB_W)
        for v in BREAKOUT['vias']:
            add_via(board, dpn, *xf(v))
    # hub exposed pad: 4 stitching vias to the GND plane (0.3 mm drill, JLC standard)
    gnd = P.pad_net(hub, '37')
    hx0, hy0 = HUB_POS[0], HUB_POS[1]
    for dx in (-0.8, 0.8):
        for dy in (-0.8, 0.8):
            add_via(board, gnd, hx0 + dx, hy0 + dy, dia=0.5, drill=0.3)
    # hub VDDA33 pin 5 -> via to 3V3 plane
    n5 = P.pad_net(hub, '5')
    x5, y5 = P.pad_pos(hub, '5')
    add_track(board, n5, [(x5, y5), (26.6, y5)], pcbnew.F_Cu, 0.2)
    add_via(board, n5, 26.6, y5)



def place_all(P):
    comps = P.comps

    def refs_where(pred):
        return sorted([r for r, c in comps.items() if c['fp'] and pred(c)],
                      key=lambda r: (r.rstrip('0123456789'), int(''.join(ch for ch in r if ch.isdigit()) or 0)))

    def nets_of(ref):
        return {p: P.pin_net.get((ref, p)) for p in [pad.GetNumber() for pad in P.fps[ref].Pads()]}

    # ---------------- fixed big parts
    P.put('J1', *USB_C_POS, force=True)
    for h, (x, y) in zip(('H1', 'H2', 'H3', 'H4'), ((3.5, 3.5), (BW - 3.5, 3.5), (3.5, BH - 3.5),
                                                    (BW - 3.5, BH - 3.5))):
        P.put(h, x, y, force=True)

    ft = {}
    for r in refs_where(lambda c: c['value'] == 'FT4232HL'):
        n = int(comps[r]['sheet'].strip('/')[2:])
        ft[n] = r
        x, y, rot = FT_POS[n]
        P.put(r, x, y, rot, force=True)
    hub = refs_where(lambda c: c['value'] == 'USB2514B')[0]
    P.put(hub, *HUB_POS, force=True)
    P.ft_ref = ft
    P.hub = hub
    usb_reserve(P, hub)


    # ---------------- channel blocks (connectors, LEDs, series R, ESD, buffers)
    conns = refs_where(lambda c: c['fields'].get('Channel'))
    for r in conns:
        ch = int(comps[r]['fields']['Channel'][2:])
        i = (ch - 1) % 8
        top = ch <= 8
        x = CONN_X0 + i * CONN_PITCH
        if top:
            P.put(r, x, CONN_Y_TOP, 90, force=True)                 # left to right: RX (pad 3), TX, GND (pad 1)
        else:
            P.put(r, x + 2 * HDR_P, CONN_Y_BOT, 270, force=True)    # left to right: GND (pad 1), TX, RX (pad 3)
    jref = {int(comps[r]['fields']['Channel'][2:]): r for r in conns}

    def chnets(ch):
        return 'CH%02d_TX' % ch, 'CH%02d_RX' % ch

    for ft_n in range(1, 5):
        sheet = '/FT%d/' % ft_n
        top = ft_n <= 2
        sgn = 1 if top else -1                 # direction into the board
        ybase = CONN_Y_TOP if top else CONN_Y_BOT
        for pair in range(2):
            chs = [4 * (ft_n - 1) + 2 * pair + k + 1 for k in range(2)]
            xs = [CONN_X0 + ((c - 1) % 8) * CONN_PITCH for c in chs]
            xm = (xs[0] + xs[1] + 5.0) / 2
            # buffer for this pair
            buf = [r for r in refs_where(lambda c: c['sheet'] == sheet and c['value'] == '74LVC125APW')
                   if any(short(P.pin_net.get((r, '3'), '')).startswith('FT%d_%s' % (ft_n, 'AC'[pair])) for _ in [0])]
            assert len(buf) == 1, buf
            P.put(buf[0], xm, ybase + sgn * 13.5, 90 if top else 270, force=True)
            esd = [r for r in refs_where(lambda c: c['sheet'] == sheet and c['value'] == 'ESDA6V1-5SC6')
                   if short(P.pin_net.get((r, '1'), '')) == 'CH%02d_TX' % chs[0]][0]
            P.put(esd, xm, ybase + sgn * 6.5, 0, force=True)
            for k, ch in enumerate(chs):
                x = xs[k]
                txn, rxn = chnets(ch)
                port = 'ABCD'[(ch - 1) % 4]
                # LED + 1k next to the connector (outside edge of the pair)
                led = [r for r in refs_where(lambda c: c['sheet'] == sheet and c['value'] == 'green')
                       if short(P.pin_net.get((r, '1'), '')) == 'FT%d_%s_DTR_N' % (ft_n, port)][0]
                lx = x + 9.25
                P.put(led, lx, ybase + sgn * 0.6, 90, force=True)
                rled = [r for r in refs_where(lambda c: c['sheet'] == sheet and c['value'] == '1k')
                        if short(P.pin_net.get((r, '2'), '')) == 'FT%d_%s_LED_A' % (ft_n, port)][0]
                P.put(rled, lx, ybase + sgn * 3.2, 90, force=True)
                # series resistors right behind the connector (RX pin at x, TX pin at x + 2.54)
                for r in refs_where(lambda c: c['sheet'] == sheet and c['value'] == '220R'):
                    ns = {short(v) for v in nets_of(r).values() if v}
                    if txn in ns:
                        P.put(r, x + 1.25, ybase + sgn * 9.0, 90, force=True)
                    if rxn in ns:
                        P.put(r, x + 3.75, ybase + sgn * 9.0, 90, force=True)

    # ---------------- pin-affinity placement for everything else
    ics = refs_where(lambda c: c['ref'].startswith('U') or c['ref'].startswith('Y') or c['ref'] == 'J1')
    ic_pins = {}
    for ic in ics:
        for pad in P.fps[ic].Pads():
            n = P.pin_net.get((ic, pad.GetNumber()))
            if n:
                ic_pins.setdefault(n, []).append((ic, pad.GetNumber()))

    # explicit companions: EEPROM and crystal next to their FT
    for ft_n, u in ft.items():
        sheet = '/FT%d/' % ft_n
        ee = refs_where(lambda c: c['sheet'] == sheet and c['value'] == '93LC56B')[0]
        ax, ay = P.pad_pos(u, '62')
        nx, ny = outward(P, u, '62')
        P.near(ee, ax, ay, nx, ny, rot=0, start=4.5)
        y = refs_where(lambda c: c['sheet'] == sheet and c['value'] == '12MHz')[0]
        ax, ay = P.pad_pos(u, '2')
        nx, ny = outward(P, u, '2')
        P.near(y, ax, ay, nx, ny, rot=0, start=4.0)
    y = refs_where(lambda c: c['sheet'] == '/Hub/' and c['value'] == '24MHz')[0]
    ax, ay = P.pad_pos(hub, '33')
    P.near(y, ax, ay, *outward(P, hub, '33'), rot=0, start=3.5)
    # buck + USB ESD near connector
    usbesd = refs_where(lambda c: c['value'] == 'USBLC6-2SC6')[0]
    P.put(usbesd, 13.0, 50.0, 90, force=True)
    buck = refs_where(lambda c: c['value'] == 'TLV62569DBV')[0]
    P.put(buck, 10.0, 70.0, 0, force=True)
    for r in (usbesd, buck):
        ics.append(r)
        for pad in P.fps[r].Pads():
            n = P.pin_net.get((r, pad.GetNumber()))
            if n:
                ic_pins.setdefault(n, []).append((r, pad.GetNumber()))

    supply_rr = {}
    rest = [r for r in refs_where(lambda c: True) if r not in P.placed]
    # order: things with specific signal nets first, then decoupling
    def prio(r):
        ns = [n for n in nets_of(r).values() if n and short(n) not in POWER_NETS]
        return (0 if ns else 1, r)
    for r in sorted(rest, key=prio):
        ns = [n for n in nets_of(r).values() if n]
        sig = [n for n in ns if short(n) not in POWER_NETS]
        cand = []
        for n in sig:
            for ic, pin in ic_pins.get(n, []):
                if ic != r and ic in P.placed:
                    cand.append((ic, pin))
        # prefer the buffer for channel parts, FT for others
        if cand:
            cand.sort(key=lambda t: (0 if comps[t[0]]['value'] == '74LVC125APW' else
                                     1 if comps[t[0]]['value'].startswith('FT') else 2))
            ic, pin = cand[0]
        else:
            # pure supply decoupling: round robin over supply pins of ICs on same sheet
            sheet = comps[r]['sheet']
            pins = []
            for n in ns:
                if short(n) in ('GND',):
                    continue
                for ic, pin in ic_pins.get(n, []):
                    if comps[ic]['sheet'] == sheet and ic in P.placed and ic != r:
                        pins.append((ic, pin))
            if not pins:
                P.fallback(r, 20, 80)
                continue
            key = (sheet, tuple(sorted(set(ns))))
            i = supply_rr.get(key, 0)
            supply_rr[key] = i + 1
            ic, pin = pins[i % len(pins)]
        ax, ay = P.pad_pos(ic, pin)
        nx, ny = outward(P, ic, pin)
        start = 1.6 if comps[ic]['value'] not in ('FT4232HL',) else 1.4
        if not P.near(r, ax, ay, nx, ny, start=start):
            P.fallback(r, ax, ay)


def outline(board):
    rect = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECT)
    rect.SetStart(pcbnew.VECTOR2I(0, 0))
    rect.SetEnd(pcbnew.VECTOR2I(MM(BW), MM(BH)))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(MM(0.1))
    board.Add(rect)


def add_zone(board, netname, layer, prio=0, clearance=0.2, inset=0.4):
    net = board.FindNet(netname)
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(MM(clearance))
    z.SetMinThickness(MM(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(MM(0.25))
    z.SetThermalReliefSpokeWidth(MM(0.3))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((inset, inset), (BW - inset, inset), (BW - inset, BH - inset), (inset, BH - inset)):
        ol.Append(MM(x), MM(y))
    board.Add(z)
    return z


def fill_zones(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def main():
    write_project()
    comps, nets = read_netlist()
    board = pcbnew.NewBoard(PRJ + '.kicad_pcb')
    board.SetCopperLayerCount(4)
    board.SetLayerName(pcbnew.In1_Cu, 'In1.GND')
    board.SetLayerName(pcbnew.In2_Cu, 'In2.3V3')
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    P = Placer(board, comps, nets)
    P.build()
    place_all(P)
    usb_route(board, P, P.hub)
    j1_vbus(board, P)
    outline(board)
    add_zone(board, 'GND', pcbnew.In1_Cu)
    add_zone(board, '+3V3', pcbnew.In2_Cu)
    from fanout import fanout
    n, failed = fanout(board, bw=BW, bh=BH)
    print('fanout vias', n, 'failed', failed)
    missing = [r for r in P.fps if r not in P.placed]
    print('footprints', len(P.fps), 'unplaced', missing)
    board.Save(PRJ + '.kicad_pcb')
    return board, P


if __name__ == '__main__':
    main()
