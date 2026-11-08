"""Tiny KiCad 9 schematic writer.

Connectivity is made purely with labels / power symbols placed on pin
endpoints, so the generator never has to route wires.  Every net that is
used on more than one sheet becomes a global label, power nets use power
symbols.
"""
import copy
import os
import uuid as _uuid

from sexp import Sym, dump, find, find1, parse

SYMDIR = '/usr/share/kicad/symbols'
PROJECT = 'sbc-uart-hub'
POWER_NETS = {'GND', '+3V3', '+5V', 'VBUS'}

_ns = _uuid.UUID('6c1b8d8e-3f5a-4c39-9f3e-2b9c0d1a7e55')


def uid(*key):
    """Deterministic UUIDs so regenerating gives stable files/diffs."""
    return str(_uuid.uuid5(_ns, '/'.join(str(k) for k in key)))


S = Sym

# --------------------------------------------------------------------------
# library handling

_libcache = {}


def _lib(libname):
    if libname not in _libcache:
        tree = parse(open(os.path.join(SYMDIR, libname + '.kicad_sym')).read())
        _libcache[libname] = {s[1]: s for s in find(tree, 'symbol')}
    return _libcache[libname]


def lib_symbol(lib_id):
    """Return flattened library symbol (with name = lib_id)."""
    libname, name = lib_id.split(':')
    syms = _lib(libname)
    s = copy.deepcopy(syms[name])
    ext = find1(s, 'extends')
    if ext:
        base = copy.deepcopy(lib_symbol(libname + ':' + ext[1]))
        bname = ext[1]
        props = find(s, 'property')
        out = [S('symbol'), lib_id]
        for e in base[2:]:
            if isinstance(e, list) and e and e[0] == 'property':
                continue
            if isinstance(e, list) and e and e[0] == 'symbol':
                e = copy.deepcopy(e)
                e[1] = e[1].replace(bname.split(':')[-1] + '_', name + '_', 1)
                out.append(e)
                continue
            out.append(e)
        # insert derived properties after flags
        idx = 2
        while idx < len(out) and not (isinstance(out[idx], list) and out[idx][0] == 'symbol'):
            idx += 1
        names = {p[1] for p in props}
        merged = props + [p for p in find(base, 'property') if p[1] not in names]
        for p in merged:
            out.insert(idx, p)
            idx += 1
        return out
    s[1] = lib_id
    return s


def sym_pins(lib_id):
    """pins: list of dict(unit, num, name, type, x, y, rot) (lib coords)."""
    s = lib_symbol(lib_id)
    out = []
    for u in find(s, 'symbol'):
        parts = u[1].split('_')
        unit = int(parts[-2])
        for p in find(u, 'pin'):
            at = find1(p, 'at')
            out.append(dict(unit=unit, type=str(p[1]), name=find1(p, 'name')[1], num=find1(p, 'number')[1],
                            x=float(at[1]), y=float(at[2]), rot=float(at[3]) if len(at) > 3 else 0.0))
    return out


def rot_vec(x, y, rot):
    """Rotate a screen-space vector by symbol rotation (deg, CCW on screen)."""
    r = int(rot) % 360
    for _ in range(r // 90):
        x, y = y, -x
    return x, y


def _snap(v):
    return round(v / 1.27) * 1.27


# --------------------------------------------------------------------------

class Sheet:
    def __init__(self, design, name, fname, page, title):
        self.d = design
        self.name = name
        self.fname = fname
        self.page = page
        self.title = title
        self.uuid = uid('sheet', name)
        self.items = []
        self.lib_ids = set()
        self.pinpos = []          # (net, x, y, outward, sheet-local)
        self.nc = []
        self.texts = []

    # ---------------- symbol placement
    def place(self, lib_id, ref, value, at, rot=0, unit=1, fields=None, pins=None, dnp=False,
              in_bom=True, on_board=True, hide_value=False, fp=''):
        """pins: {pin_number: net or None(=no connect)}; pins not listed must be
        connected elsewhere (other unit) or are an error."""
        self.lib_ids.add(lib_id)
        x, y = at
        x, y = _snap(x), _snap(y)
        su = uid(self.name, ref, unit)
        props = [
            ('Reference', ref, (x + 2.54, y - 3.81), False),
            ('Value', value, (x + 2.54, y + 3.81), hide_value),
            ('Footprint', fp, (x, y), True),
            ('Datasheet', '~', (x, y), True),
        ]
        for k, v in (fields or {}).items():
            props.append((k, v, (x, y), True))
        node = [S('symbol'), [S('lib_id'), lib_id], [S('at'), x, y, rot], [S('unit'), unit],
                [S('exclude_from_sim'), S('no')], [S('in_bom'), S('yes' if in_bom else 'no')],
                [S('on_board'), S('yes' if on_board else 'no')], [S('dnp'), S('yes' if dnp else 'no')],
                [S('uuid'), su]]
        for k, v, (px, py), hide in props:
            eff = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]
            if hide:
                eff.append([S('hide'), S('yes')])
            node.append([S('property'), k, v, [S('at'), px, py, 0], eff])
        allpins = [p for p in sym_pins(lib_id) if p['unit'] in (0, unit)]
        seen = set()
        for p in allpins:
            if p['num'] in seen:
                continue
            seen.add(p['num'])
            node.append([S('pin'), p['num'], [S('uuid'), uid(self.name, ref, unit, 'pin', p['num'])]])
        node.append([S('instances'), [S('project'), PROJECT,
                                      [S('path'), '/' + self.d.root_uuid + '/' + self.uuid,
                                       [S('reference'), ref], [S('unit'), unit]]]])
        self.items.append(node)
        # connections
        if pins:
            bynum = {}
            for p in allpins:
                bynum.setdefault(p['num'], []).append(p)
            for num, net in pins.items():
                if num not in bynum:
                    raise KeyError('%s (%s) has no pin %s' % (ref, lib_id, num))
                for p in bynum[num]:
                    ox, oy = rot_vec(p['x'], -p['y'], rot)
                    px, py = x + ox, y + oy
                    dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[int(p['rot']) % 360]
                    dx, dy = rot_vec(dx, dy, rot)
                    out = (-dx, -dy)
                    if net is None:
                        self.nc.append((px, py))
                    else:
                        self.pinpos.append((net, px, py, out))
                    break   # stacked pins share position: one label is enough
        return ref

    def text(self, s, at, size=2.0):
        self.texts.append((s, at, size))

    # ---------------- output
    def _label(self, net, x, y, out, is_global):
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[out]
        just = {0: 'left', 90: 'left', 180: 'right', 270: 'right'}[ang]
        eff = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('justify'), S(just)]]
        u = uid(self.name, 'lbl', net, x, y)
        if is_global:
            return [S('global_label'), net, [S('shape'), S('bidirectional')], [S('at'), x, y, ang],
                    [S('fields_autoplaced'), S('yes')], eff, [S('uuid'), u],
                    [S('property'), 'Intersheetrefs', '${INTERSHEET_REFS}', [S('at'), x, y, 0],
                     [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('hide'), S('yes')]]]]
        eff = [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('justify'), S(just), S('bottom')]]
        return [S('label'), net, [S('at'), x, y, ang], [S('fields_autoplaced'), S('yes')], eff, [S('uuid'), u]]

    def _power(self, net, x, y, out):
        lib_id = 'power:GND' if net == 'GND' else 'power:' + net
        self.lib_ids.add(lib_id)
        natural = (0, 1) if net == 'GND' else (0, -1)
        rot = 0
        for r in (0, 90, 180, 270):
            if rot_vec(natural[0], natural[1], r) == out:
                rot = r
                break
        ref = self.d.next_ref('#PWR')
        su = uid(self.name, ref)
        tx, ty = x + out[0] * 5, y + out[1] * 5
        return [S('symbol'), [S('lib_id'), lib_id], [S('at'), x, y, rot], [S('unit'), 1],
                [S('exclude_from_sim'), S('no')], [S('in_bom'), S('yes')], [S('on_board'), S('yes')],
                [S('dnp'), S('no')], [S('uuid'), su],
                [S('property'), 'Reference', ref, [S('at'), x, y, 0],
                 [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('hide'), S('yes')]]],
                [S('property'), 'Value', net, [S('at'), tx, ty, 0],
                 [S('effects'), [S('font'), [S('size'), 1.27, 1.27]]]],
                [S('property'), 'Footprint', '', [S('at'), x, y, 0],
                 [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('hide'), S('yes')]]],
                [S('property'), 'Datasheet', '', [S('at'), x, y, 0],
                 [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('hide'), S('yes')]]],
                [S('pin'), '1', [S('uuid'), uid(self.name, ref, 'p')]],
                [S('instances'), [S('project'), PROJECT,
                                  [S('path'), '/' + self.d.root_uuid + '/' + self.uuid,
                                   [S('reference'), ref], [S('unit'), 1]]]]]

    def render(self, global_nets):
        body = []
        for net, x, y, out in self.pinpos:
            if net in POWER_NETS:
                body.append(self._power(net, x, y, out))
            else:
                body.append(self._label(net, x, y, out, net in global_nets))
        for x, y in self.nc:
            body.append([S('no_connect'), [S('at'), x, y], [S('uuid'), uid(self.name, 'nc', x, y)]])
        for s, (x, y), size in self.texts:
            body.append([S('text'), s, [S('exclude_from_sim'), S('no')], [S('at'), x, y, 0],
                         [S('effects'), [S('font'), [S('size'), size, size]], [S('justify'), S('left'), S('bottom')]],
                         [S('uuid'), uid(self.name, 'txt', s)]])
        libs = [lib_symbol(l) for l in sorted(self.lib_ids)]
        head = [S('kicad_sch'), [S('version'), 20250114], [S('generator'), 'eeschema'],
                [S('generator_version'), '9.0'], [S('uuid'), self.uuid], [S('paper'), 'A3'],
                [S('title_block'), [S('title'), self.title], [S('rev'), self.d.rev],
                 [S('company'), self.d.company]],
                [S('lib_symbols')] + libs]
        return head + self.items + body + [[S('embedded_fonts'), S('no')]]


class Design:
    def __init__(self, rev='A', company=''):
        self.rev = rev
        self.company = company
        self.root_uuid = uid('root')
        self.sheets = []
        self._refs = {}

    def next_ref(self, prefix):
        self._refs[prefix] = self._refs.get(prefix, 0) + 1
        return '%s%d' % (prefix, self._refs[prefix])

    def sheet(self, name, fname, title):
        s = Sheet(self, name, fname, len(self.sheets) + 2, title)
        self.sheets.append(s)
        return s

    def write(self, outdir, root_title):
        # nets present on more than one sheet -> global
        where = {}
        for s in self.sheets:
            for net, *_ in s.pinpos:
                where.setdefault(net, set()).add(s.name)
        global_nets = {n for n, ss in where.items() if len(ss) > 1}
        for s in self.sheets:
            with open(os.path.join(outdir, s.fname), 'w') as f:
                f.write(dump(s.render(global_nets)) + '\n')
        # root
        items = []
        x0, y0 = 30.48, 40.64
        for i, s in enumerate(self.sheets):
            x = x0 + (i % 4) * 76.2
            y = y0 + (i // 4) * 50.8
            items.append([S('sheet'), [S('at'), x, y], [S('size'), 50.8, 25.4],
                          [S('exclude_from_sim'), S('no')], [S('in_bom'), S('yes')], [S('on_board'), S('yes')],
                          [S('dnp'), S('no')], [S('fields_autoplaced'), S('yes')],
                          [S('stroke'), [S('width'), 0.1524], [S('type'), S('solid')]],
                          [S('fill'), [S('color'), 0, 0, 0, 0.0]],
                          [S('uuid'), s.uuid],
                          [S('property'), 'Sheetname', s.name, [S('at'), x, y - 0.7116, 0],
                           [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('justify'), S('left'), S('bottom')]]],
                          [S('property'), 'Sheetfile', s.fname, [S('at'), x, y + 26.0, 0],
                           [S('effects'), [S('font'), [S('size'), 1.27, 1.27]], [S('justify'), S('left'), S('top')]]],
                          [S('instances'), [S('project'), PROJECT,
                                            [S('path'), '/' + self.root_uuid, [S('page'), str(s.page)]]]]])
        root = [S('kicad_sch'), [S('version'), 20250114], [S('generator'), 'eeschema'],
                [S('generator_version'), '9.0'], [S('uuid'), self.root_uuid], [S('paper'), 'A4'],
                [S('title_block'), [S('title'), root_title], [S('rev'), self.rev], [S('company'), self.company]],
                [S('lib_symbols')]] + items + [
            [S('sheet_instances'), [S('path'), '/', [S('page'), '1']]],
            [S('embedded_fonts'), S('no')]]
        with open(os.path.join(outdir, PROJECT + '.kicad_sch'), 'w') as f:
            f.write(dump(root) + '\n')
        return global_nets
