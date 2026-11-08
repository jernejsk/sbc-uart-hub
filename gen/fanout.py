"""Via fan-out of plane nets (GND, +3V3) for SMD pads on F.Cu."""
import math

import pcbnew

TOMM = pcbnew.ToMM
MM = pcbnew.FromMM


class Obstacles:
    def __init__(self, cell=2.0):
        self.cell = cell
        self.grid = {}

    def _cells(self, x0, y0, x1, y1):
        c = self.cell
        for i in range(int(math.floor(x0 / c)), int(math.floor(x1 / c)) + 1):
            for j in range(int(math.floor(y0 / c)), int(math.floor(y1 / c)) + 1):
                yield (i, j)

    def add(self, kind, geom, net, layers):
        if kind == 'rect':
            x0, y0, x1, y1 = geom
        elif kind == 'circle':
            x, y, r = geom
            x0, y0, x1, y1 = x - r, y - r, x + r, y + r
        else:  # seg
            ax, ay, bx, by, w = geom
            x0, y0, x1, y1 = min(ax, bx) - w, min(ay, by) - w, max(ax, bx) + w, max(ay, by) + w
        item = (kind, geom, net, layers)
        for c in self._cells(x0, y0, x1, y1):
            self.grid.setdefault(c, []).append(item)

    def near(self, x0, y0, x1, y1):
        seen = set()
        for c in self._cells(x0, y0, x1, y1):
            for it in self.grid.get(c, ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    yield it


def _pt_rect(px, py, r):
    x0, y0, x1, y1 = r
    dx = max(x0 - px, 0, px - x1)
    dy = max(y0 - py, 0, py - y1)
    return math.hypot(dx, dy)


def _pt_seg(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _dist_item_point(it, px, py):
    kind, g, _, _ = it
    if kind == 'rect':
        return _pt_rect(px, py, g)
    if kind == 'circle':
        return math.hypot(px - g[0], py - g[1]) - g[2]
    return _pt_seg(px, py, g[0], g[1], g[2], g[3]) - g[4] / 2


def build_obstacles(board):
    obs = Obstacles()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            r = (TOMM(bb.GetLeft()), TOMM(bb.GetTop()), TOMM(bb.GetRight()), TOMM(bb.GetBottom()))
            tht = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            layers = 'all' if tht else ('F' if pad.IsOnLayer(pcbnew.F_Cu) else 'B')
            obs.add('rect', r, pad.GetNetname(), layers)
    for t in board.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            obs.add('circle', (TOMM(p.x), TOMM(p.y), TOMM(t.GetWidth(pcbnew.F_Cu)) / 2), t.GetNetname(), 'all')
        else:
            s, e = t.GetStart(), t.GetEnd()
            lay = 'F' if t.GetLayer() == pcbnew.F_Cu else 'B'
            obs.add('seg', (TOMM(s.x), TOMM(s.y), TOMM(e.x), TOMM(e.y), TOMM(t.GetWidth())), t.GetNetname(), lay)
    return obs


def via_ok(obs, net, x, y, r, clr, bw, bh, edge=0.6):
    if x - r < edge or y - r < edge or x + r > bw - edge or y + r > bh - edge:
        return False
    for it in obs.near(x - r - clr - 1, y - r - clr - 1, x + r + clr + 1, y + r + clr + 1):
        if it[2] == net and it[0] != 'rect':
            # same-net via/track: allow, but keep vias apart
            if it[0] == 'circle' and _dist_item_point(it, x, y) < r + 0.1:
                return False
            continue
        if it[2] == net and it[0] == 'rect':
            continue
        if _dist_item_point(it, x, y) < r + clr:
            return False
    return True


def seg_ok(obs, net, ax, ay, bx, by, w, clr, own_rect):
    L = math.hypot(bx - ax, by - ay)
    n = max(2, int(L / 0.05))
    for it in obs.near(min(ax, bx) - 1, min(ay, by) - 1, max(ax, bx) + 1, max(ay, by) + 1):
        if it[2] == net or it[3] == 'B':
            continue
        for k in range(n + 1):
            px, py = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
            if _dist_item_point(it, px, py) < w / 2 + clr:
                return False
    return True


def fanout(board, nets=('GND', '+3V3'), bw=146.0, bh=100.0, via_d=0.5, drill=0.3, tw=0.25, clr=0.16,
           skip_refs=()):
    obs = build_obstacles(board)
    netinfo = {n: board.FindNet(n) for n in nets}
    placed, failed = 0, []
    r = via_d / 2
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if fp.GetReference() in skip_refs:
            continue
        fc = fp.GetPosition()
        fx, fy = TOMM(fc.x), TOMM(fc.y)
        for pad in fp.Pads():
            net = pad.GetNetname()
            if net not in nets or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            bb = pad.GetBoundingBox()
            rect = (TOMM(bb.GetLeft()), TOMM(bb.GetTop()), TOMM(bb.GetRight()), TOMM(bb.GetBottom()))
            px, py = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            # already has a same-net via inside the pad (e.g. exposed pad)
            if any(it[0] == 'circle' and it[2] == net and _pt_rect(it[1][0], it[1][1], rect) == 0
                   for it in obs.near(*rect)):
                continue
            hx, hy = (rect[2] - rect[0]) / 2, (rect[3] - rect[1]) / 2
            dx, dy = px - fx, py - fy
            if abs(dx) < 1e-3 and abs(dy) < 1e-3:
                dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)]
            elif abs(dx) >= abs(dy):
                s = 1 if dx > 0 else -1
                dirs = [(s, 0), (0, 1), (0, -1), (-s, 0)]
            else:
                s = 1 if dy > 0 else -1
                dirs = [(0, s), (1, 0), (-1, 0), (0, -s)]
            done = False
            for ux, uy in dirs:
                ext = hx if ux else hy
                for k in range(10):
                    d = ext + r + 0.12 + k * 0.25
                    for lat in (0, 0.45, -0.45, 0.9, -0.9):
                        vx = px + ux * d + (-uy) * lat
                        vy = py + uy * d + ux * lat
                        if not via_ok(obs, net, vx, vy, r, clr, bw, bh):
                            continue
                        if not seg_ok(obs, net, px, py, vx, vy, tw, clr, rect):
                            continue
                        t = pcbnew.PCB_TRACK(board)
                        t.SetStart(pcbnew.VECTOR2I(MM(px), MM(py)))
                        t.SetEnd(pcbnew.VECTOR2I(MM(vx), MM(vy)))
                        t.SetLayer(pcbnew.F_Cu)
                        t.SetWidth(MM(tw))
                        t.SetNet(netinfo[net])
                        t.SetLocked(True)
                        board.Add(t)
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(pcbnew.VECTOR2I(MM(vx), MM(vy)))
                        v.SetWidth(MM(via_d))
                        v.SetDrill(MM(drill))
                        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                        v.SetNet(netinfo[net])
                        v.SetLocked(True)
                        board.Add(v)
                        obs.add('circle', (vx, vy, r), net, 'all')
                        obs.add('seg', (px, py, vx, vy, tw), net, 'F')
                        placed += 1
                        done = True
                        break
                    if done:
                        break
                if done:
                    break
            if not done:
                failed.append('%s.%s' % (fp.GetReference(), pad.GetNumber()))
    return placed, failed
