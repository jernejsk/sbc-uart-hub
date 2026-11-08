#!/usr/bin/env python3
"""SBC farm UART hub: schematic description.

USB-C -> USB2514B hub -> 4x FT4232HL -> 16 gated UART channels on JST-XH.
Run: python3 gen/design.py  (writes hw/*.kicad_sch)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schgen import Design  # noqa: E402

HW = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hw')

# kind: (lib_id, footprint, lcsc, mpn)
PARTS = {
    'R0402': ('Device:R_Small', 'Resistor_SMD:R_0402_1005Metric'),
    'C0402': ('Device:C_Small', 'Capacitor_SMD:C_0402_1005Metric'),
    'C0805': ('Device:C_Small', 'Capacitor_SMD:C_0805_2012Metric'),
    'LED': ('Device:LED_Small', 'LED_SMD:LED_0603_1608Metric'),
    'FB': ('Device:FerriteBead_Small', 'Inductor_SMD:L_0603_1608Metric'),
    'L4020': ('Device:L_Small', 'Inductor_SMD:L_Taiyo-Yuden_NR-40xx'),
    'PTC': ('Device:Polyfuse_Small', 'Fuse:Fuse_1206_3216Metric'),
    'XTAL': ('Device:Crystal_GND24', 'Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm'),
}

# value -> (kind, lcsc, mpn)
VALUES = {
    ('R0402', '0R'): ('C17168', '0402WGF0000TCE'),
    ('R0402', '220R'): ('C25091', '0402WGF2200TCE'),
    ('R0402', '1k'): ('C11702', '0402WGF1001TCE'),
    ('R0402', '2k2'): ('C25879', '0402WGF2201TCE'),
    ('R0402', '5k1'): ('C25905', '0402WGF5101TCE'),
    ('R0402', '10k'): ('C25744', '0402WGF1002TCE'),
    ('R0402', '12k 1%'): ('C25752', '0402WGF1202TCE'),
    ('R0402', '22k'): ('C25768', '0402WGF2202TCE'),
    ('R0402', '100k'): ('C25741', '0402WGF1003TCE'),
    ('C0402', '100n'): ('C1525', 'CL05B104KO5NNNC'),
    ('C0402', '1u'): ('C52923', 'CL05A105KA5NQNC'),
    ('C0402', '27p'): ('C1557', '0402CG270J500NT'),
    ('C0402', '33p'): ('C1562', '0402CG330J500NT'),
    ('C0805', '4u7'): ('C1779', 'CL21A475KAQNNNE'),
    ('C0805', '10u'): ('C15850', 'CL21A106KAYNNNE'),
    ('LED', 'green'): ('C12624', 'KT-0603G'),
    ('LED', 'red'): ('C2286', 'KT-0603R'),
    ('FB', '600R@100MHz'): ('C1002', 'GZ1608D601TF'),
    ('L4020', '2u2'): ('C83423', 'SWPA4020S2R2MT'),
    ('PTC', '1.1A'): ('C20801', 'SMD1206P110TF'),
    ('XTAL', '12MHz'): ('C9002', 'X322512MSB4SI'),
    ('XTAL', '24MHz'): ('C70590', 'X322524MOB4SI'),
}

REFPFX = {'R0402': 'R', 'C0402': 'C', 'C0805': 'C', 'LED': 'D', 'FB': 'FB', 'L4020': 'L', 'PTC': 'F',
          'XTAL': 'Y'}

d = Design(rev='A', company='SBC farm')


def fields(lcsc, mpn):
    return {'LCSC': lcsc, 'MPN': mpn}


class Table:
    """Column-wise placement of two-terminal passives."""

    def __init__(self, sheet, x, y, rows=20, colw=60.96, rowh=7.62):
        self.s, self.x, self.y, self.rows, self.colw, self.rowh = sheet, x, y, rows, colw, rowh
        self.n = 0

    def add(self, kind, value, n1, n2, dnp=False):
        lib_id, fp = PARTS[kind]
        lcsc, mpn = VALUES[(kind, value)]
        col, row = divmod(self.n, self.rows)
        self.n += 1
        at = (self.x + col * self.colw, self.y + row * self.rowh)
        ref = d.next_ref(REFPFX[kind])
        rot = 0 if kind in ('LED', 'XTAL') else 90
        f = fields(lcsc, mpn)
        if dnp:
            f['DNP'] = 'DNP'
        self.s.place(lib_id, ref, value, at, rot=rot, fields=f, pins={'1': n1, '2': n2}, dnp=dnp,
                     in_bom=not dnp, fp=fp)
        return ref


def xtal(sheet, at, value, n1, n3):
    lib_id, fp = PARTS['XTAL']
    lcsc, mpn = VALUES[('XTAL', value)]
    ref = d.next_ref('Y')
    sheet.place(lib_id, ref, value, at, fields=fields(lcsc, mpn), pins={'1': n1, '3': n3, '2': 'GND', '4': 'GND'},
                fp=fp)


# =====================================================================
# Power / USB input
# =====================================================================
pw = d.sheet('Power', 'power.kicad_sch', 'USB-C input, 3.3 V buck')
pw.text('USB-C (USB 2.0 only). Bus powered, budget ~0.45 A @5 V via buck.', (25.4, 22.86))
pw.place('Connector:USB_C_Receptacle_USB2.0_16P', 'J1', 'USB-C', (50.8, 76.2),
         fields=fields('C165948', 'TYPE-C-31-M-12'), fp='Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
         pins={'A1': 'GND', 'A4': 'VBUS', 'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_UP_DP', 'B6': 'USB_UP_DP',
               'A7': 'USB_UP_DM', 'B7': 'USB_UP_DM', 'A8': None, 'B8': None, 'S1': 'GND'})
pw.place('Power_Protection:USBLC6-2SC6', d.next_ref('U'), 'USBLC6-2SC6', (127, 63.5),
         fields=fields('C7519', 'USBLC6-2SC6'), fp='Package_TO_SOT_SMD:SOT-23-6',
         pins={'1': 'USB_UP_DP', '6': 'USB_UP_DP', '3': 'USB_UP_DM', '4': 'USB_UP_DM', '2': 'GND', '5': '+5V'})
pw.place('Regulator_Switching:TLV62569DBV', d.next_ref('U'), 'TLV62569DBV', (127, 127),
         fields=fields('C141836', 'TLV62569DBVR'), fp='Package_TO_SOT_SMD:SOT-23-5',
         pins={'1': '+5V', '4': '+5V', '2': 'GND', '3': 'BUCK_SW', '5': 'BUCK_FB'})
t = Table(pw, 190.5, 50.8, rows=14)
t.add('R0402', '5k1', 'CC1', 'GND')
t.add('R0402', '5k1', 'CC2', 'GND')
t.add('PTC', '1.1A', 'VBUS', '+5V')
t.add('C0805', '10u', '+5V', 'GND')
t.add('C0402', '100n', '+5V', 'GND')
t.add('L4020', '2u2', 'BUCK_SW', '+3V3')
t.add('R0402', '100k', '+3V3', 'BUCK_FB')
t.add('R0402', '22k', 'BUCK_FB', 'GND')
t.add('C0805', '10u', '+3V3', 'GND')
t.add('C0805', '10u', '+3V3', 'GND')
t.add('C0402', '100n', '+3V3', 'GND')
t.add('R0402', '1k', '+3V3', 'PWR_LED_A')
t.add('LED', 'red', 'GND', 'PWR_LED_A')
# power flags
for i, net in enumerate(['VBUS', '+5V', '+3V3', 'GND']):
    pw.place('power:PWR_FLAG', d.next_ref('#FLG'), 'PWR_FLAG', (50.8 + i * 15.24, 160.02), pins={'1': net},
             in_bom=False, on_board=False)
for i in range(4):
    pw.place('Mechanical:MountingHole', 'H%d' % (i + 1), 'M3', (50.8 + i * 15.24, 190.5),
             fp='MountingHole:MountingHole_3.2mm_M3', in_bom=False)

# =====================================================================
# Hub
# =====================================================================
hb = d.sheet('Hub', 'hub.kicad_sch', 'USB2514B 4-port hub')
hb.text('CFG_SEL[1:0]=10: default config, bus powered. NON_REM=00. BC_EN=0 (PRTPWR not pulled up).', (25.4, 22.86))
hb.text('Hub port 1..4 -> FT3, FT4, FT2, FT1 (uhubctl -p N).', (25.4, 27.94))
hb.text('PRTPWR -> FT RESET# 0R links are DNP: fit them and remove the FT RESET# pull-up for hard reset.',
        (25.4, 33.02))
hpins = {'5': '+3V3', '10': '+3V3', '29': '+3V3', '36': '+3V3', '15': '+3V3', '23': '+3V3', '37': 'GND',
         '11': 'GND', '14': 'HUB_CRFILT', '34': 'HUB_PLLFILT', '35': 'HUB_RBIAS', '33': 'HUB_XI', '32': 'HUB_XO',
         '26': 'HUB_RESET_N', '27': 'HUB_VBUS_DET', '22': 'HUB_NON_REM1', '24': 'HUB_CFG_SEL0',
         '25': 'HUB_CFG_SEL1', '28': 'HUB_NON_REM0', '30': 'USB_UP_DM', '31': 'USB_UP_DP'}
# hub port -> pins; port->FT mapping chosen so the four USB lanes leave the hub
# without crossing (top pins go to the top-row FTs).  uhubctl port = hub port.
dn = {1: ('1', '2', '12', '13'), 2: ('3', '4', '16', '17'), 3: ('6', '7', '18', '19'), 4: ('8', '9', '20', '21')}
HUBPORT_FT = {1: 3, 2: 4, 3: 2, 4: 1}
for hp, (dm, dp, pwr, ocs) in dn.items():
    n = HUBPORT_FT[hp]
    hpins[dm] = 'FT%d_DM' % n
    hpins[dp] = 'FT%d_DP' % n
    hpins[pwr] = 'FT%d_PRTPWR' % n
    hpins[ocs] = None
hb.place('Interface_USB:USB2514B_Bi', d.next_ref('U'), 'USB2514B', (127, 101.6), fields=fields('C16251', 'USB2514B-AEZC-TR'),
         fp='Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP3.7x3.7mm', pins=hpins)
xtal(hb, (63.5, 162.56), '24MHz', 'HUB_XI', 'HUB_XO')
t = Table(hb, 215.9, 50.8, rows=16)
for _ in range(6):
    t.add('C0402', '100n', '+3V3', 'GND')
t.add('C0805', '4u7', '+3V3', 'GND')
t.add('C0402', '100n', 'HUB_CRFILT', 'GND')
t.add('C0402', '100n', 'HUB_PLLFILT', 'GND')
t.add('R0402', '12k 1%', 'HUB_RBIAS', 'GND')
t.add('C0402', '33p', 'HUB_XI', 'GND')
t.add('C0402', '33p', 'HUB_XO', 'GND')
t.add('R0402', '10k', '+3V3', 'HUB_RESET_N')
t.add('C0402', '1u', 'HUB_RESET_N', 'GND')
t.add('R0402', '100k', '+5V', 'HUB_VBUS_DET')
t.add('R0402', '100k', 'HUB_VBUS_DET', 'GND')
t.add('R0402', '100k', 'HUB_NON_REM1', 'GND')
t.add('R0402', '100k', 'HUB_CFG_SEL0', 'GND')
t.add('R0402', '100k', '+3V3', 'HUB_CFG_SEL1')
t.add('R0402', '100k', 'HUB_NON_REM0', 'GND')
for n in range(1, 5):
    t.add('R0402', '0R', 'FT%d_PRTPWR' % n, 'FT%d_RESET_N' % n, dnp=True)

# =====================================================================
# FT4232H x4 with gated UART channels
# =====================================================================
PORTS = 'ABCD'
# (DBUS0=TXD, DBUS1=RXD, DBUS4=DTR#, unused 2,3,5,6,7)
PORTPINS = {
    'A': ('16', '17', '21', ('18', '19', '22', '23', '24')),
    'B': ('26', '27', '30', ('28', '29', '32', '33', '34')),
    'C': ('38', '39', '43', ('40', '41', '44', '45', '46')),
    'D': ('48', '52', '55', ('53', '54', '57', '58', '59')),
}

for n in range(1, 5):
    s = d.sheet('FT%d' % n, 'ft%d.kicad_sch' % n, 'FT4232H #%d: channels %02d-%02d' % (n, 4 * n - 3, 4 * n))
    s.text('FT4232H #%d  ->  CH%02d..CH%02d.  EEPROM serial: SBCU-%d (program with ftdi_eeprom).'
           % (n, 4 * n - 3, 4 * n, n), (25.4, 22.86))
    s.text('TX is driven only while DTR# is asserted (port open). LVC Ioff => Hi-Z when unpowered.',
           (25.4, 27.94))
    p = 'FT%d_' % n
    pins = {'50': '+3V3', '49': p + '1V8', '12': p + '1V8', '37': p + '1V8', '64': p + '1V8',
            '20': '+3V3', '31': '+3V3', '42': '+3V3', '56': '+3V3', '4': p + 'VPHY', '9': p + 'VPLL',
            '10': 'GND', '1': 'GND', '5': 'GND', '11': 'GND', '15': 'GND', '25': 'GND', '35': 'GND',
            '47': 'GND', '51': 'GND', '6': p + 'REF', '7': p + 'DM', '8': p + 'DP', '13': 'GND',
            '14': p + 'RESET_N', '2': p + 'OSCI', '3': p + 'OSCO', '63': p + 'EECS', '62': p + 'EECLK',
            '61': p + 'EEDATA', '60': None, '36': None}
    for port, (tx, rx, dtr, unused) in PORTPINS.items():
        pins[tx] = p + port + '_TXD'
        pins[rx] = p + port + '_RXD'
        pins[dtr] = p + port + '_DTR_N'
        for u in unused:
            pins[u] = None
    s.place('Interface_USB:FT4232H', d.next_ref('U'), 'FT4232HL', (88.9, 114.3),
            fields=fields('C56742', 'FT4232HL-REEL'), fp='Package_QFP:LQFP-64_10x10mm_P0.5mm', pins=pins)
    xtal(s, (40.64, 185.42), '12MHz', p + 'OSCI', p + 'OSCO')
    s.place('Memory_EEPROM:93LCxxBxxOT', d.next_ref('U'), '93LC56B', (101.6, 187.96),
            fields=fields('C190271', '93LC56BT-I/OT'), fp='Package_TO_SOT_SMD:SOT-23-6',
            pins={'5': p + 'EECS', '4': p + 'EECLK', '3': p + 'EEDATA', '1': p + 'EE_DO', '6': '+3V3',
                  '2': 'GND'})
    t = Table(s, 25.4, 205.74, rows=9, colw=55.88)
    t.add('R0402', '10k', '+3V3', p + 'EECS')
    t.add('R0402', '10k', '+3V3', p + 'EECLK')
    t.add('R0402', '10k', '+3V3', p + 'EE_DO')
    t.add('R0402', '2k2', p + 'EE_DO', p + 'EEDATA')
    t.add('C0402', '100n', '+3V3', 'GND')
    t.add('C0402', '27p', p + 'OSCI', 'GND')
    t.add('C0402', '27p', p + 'OSCO', 'GND')
    t.add('R0402', '12k 1%', p + 'REF', 'GND')
    t.add('R0402', '10k', '+3V3', p + 'RESET_N')
    # supplies
    t.add('C0805', '4u7', '+3V3', 'GND')            # VREGIN
    t.add('C0402', '100n', '+3V3', 'GND')
    t.add('C0805', '4u7', p + '1V8', 'GND')         # VREGOUT >= 3.3u
    for _ in range(3):
        t.add('C0402', '100n', p + '1V8', 'GND')    # VCORE pins
    for _ in range(4):
        t.add('C0402', '100n', '+3V3', 'GND')       # VCCIO pins
    t.add('FB', '600R@100MHz', '+3V3', p + 'VPHY')
    t.add('C0402', '1u', p + 'VPHY', 'GND')
    t.add('C0402', '100n', p + 'VPHY', 'GND')
    t.add('FB', '600R@100MHz', '+3V3', p + 'VPLL')
    t.add('C0402', '1u', p + 'VPLL', 'GND')
    t.add('C0402', '100n', p + 'VPLL', 'GND')
    s.place('power:PWR_FLAG', d.next_ref('#FLG'), 'PWR_FLAG', (205.74, 279.4), pins={'1': p + 'VPHY'},
            in_bom=False, on_board=False)
    s.place('power:PWR_FLAG', d.next_ref('#FLG'), 'PWR_FLAG', (226.06, 279.4), pins={'1': p + 'VPLL'},
            in_bom=False, on_board=False)

    # two channel pairs per FT: (A,B) and (C,D)
    for pi, pair in enumerate(('AB', 'CD')):
        y0 = 50.8 + pi * 116.84
        bref = d.next_ref('U')
        # buffer: unit1/2 = TX gates, unit3/4 = RX buffers (always on)
        q0, q1 = pair
        units = {1: {'1': p + q0 + '_DTR_N', '2': p + q0 + '_TXD', '3': p + q0 + '_TXO'},
                 2: {'4': p + q1 + '_DTR_N', '5': p + q1 + '_TXD', '6': p + q1 + '_TXO'},
                 3: {'10': 'GND', '9': p + q0 + '_RXI', '8': p + q0 + '_RXD'},
                 4: {'13': 'GND', '12': p + q1 + '_RXI', '11': p + q1 + '_RXD'},
                 5: {'14': '+3V3', '7': 'GND'}}
        for u, up in units.items():
            s.place('74xx:74LVC125', bref, '74LVC125APW', (195.58, y0 + (u - 1) * 17.78), unit=u,
                    fields=fields('C6059', '74LVC125APW,118'), fp='Package_SO:TSSOP-14_4.4x5mm_P0.65mm', pins=up)
        eref = d.next_ref('D')
        chs = []
        for q in pair:
            ch = 4 * (n - 1) + PORTS.index(q) + 1
            chs.append((q, ch))
        s.place('Power_Protection:ESDA6V1-5SC6', eref, 'ESDA6V1-5SC6', (350.52, y0 + 76.2),
                fields=fields('C2827672', 'ESDA6V1-5SC6'), fp='Package_TO_SOT_SMD:SOT-23-6',
                pins={'1': 'CH%02d_TX' % chs[0][1], '3': 'CH%02d_RX' % chs[0][1],
                      '4': 'CH%02d_TX' % chs[1][1], '5': 'CH%02d_RX' % chs[1][1], '6': None, '2': 'GND'})
        t = Table(s, 233.68, y0, rows=6, colw=55.88)
        for qi, (q, ch) in enumerate(chs):
            t.add('R0402', '220R', p + q + '_TXO', 'CH%02d_TX' % ch)
            t.add('R0402', '220R', 'CH%02d_RX' % ch, p + q + '_RXI')
            t.add('R0402', '100k', '+3V3', p + q + '_RXI')
            t.add('R0402', '10k', '+3V3', p + q + '_DTR_N')
            t.add('R0402', '1k', '+3V3', p + q + '_LED_A')
            t.add('LED', 'green', p + q + '_DTR_N', p + q + '_LED_A')
            jref = 'J%d' % (100 + ch)
            s.place('Connector_Generic:Conn_01x03', jref, 'B3B-XH-A', (370.84, y0 + qi * 20.32 + 10.16),
                    fields=dict(fields('C144394', 'B3B-XH-A(LF)(SN)'), Channel='CH%02d' % ch),
                    fp='Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical',
                    pins={'1': 'GND', '2': 'CH%02d_TX' % ch, '3': 'CH%02d_RX' % ch})
        t.add('C0402', '100n', '+3V3', 'GND')

if __name__ == '__main__':
    os.makedirs(HW, exist_ok=True)
    g = d.write(HW, 'SBC farm 16-ch UART hub')
    print('sheets:', len(d.sheets), 'global nets:', len(g))
