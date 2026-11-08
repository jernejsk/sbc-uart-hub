# SBC UART hub (rev A)

A 16-channel 3.3 V debug-UART adapter for the SBC farm, connected over one USB cable.

```
USB-C ── USBLC6 ── USB2514B hub ──┬── FT4232HL #1  CH01-04 (top row, left)
                                  ├── FT4232HL #2  CH05-08 (top row, right)
                                  ├── FT4232HL #3  CH09-12 (bottom row, left)
                                  └── FT4232HL #4  CH13-16 (bottom row, right)
```

The datasheet with 3D renders, for design review, is at `docs/datasheet.html` (images in `docs/img/`).

Each channel works as follows:

- The FT TXD goes through a 74LVC125 buffer, then 220R, to the header. The buffer's /OE is that channel's DTR#.
- The connector RX comes in through 220R and the 74LVC125 (always enabled) to the FT RXD.
- The ESDA6V1-5SC6 clamps the connector pins to GND only. It has no VCC rail.
- A green LED lights while DTR is asserted, which means the port is open and TX is driven.

TX is Hi-Z whenever the port is closed. LVC parts have Ioff, so both TX and RX are also Hi-Z when the board is unpowered. As a result the DUT is never back-powered, and the cable carries no VCC.

## Connector (1x3 2.54 mm right-angle header, LCSC C492411)

| pin | signal | direction |
|-----|--------|-----------|
| 1 (square) | GND | |
| 2 | TX | adapter → DUT RX |
| 3 | RX | DUT TX → adapter |

Each header's plastic body is flush with the board edge, and its pins stick out about 6 mm past it. Pin 1 (GND, square pad) is on the right in the top row (CH01-08) and on the left in the bottom row (CH09-16). GND, TX and RX are printed next to every pin.

The project footprint (`gen/mkfp.py`, `hw/lib/sbcu.pretty`) numbers its pads the mirror of KiCad's stock right-angle header. That puts each signal where it was on the earlier JST-XH layout (commit 3d51c3360c3e), so that routing was kept; the header itself is symmetric. `gen/rework_headers.py` did the migration: it swapped the footprints, ripped only the connector stubs and locked the rest. It then had Freerouting finish the stubs. A fresh `build_pcb.py` + `route.py` run gives the same placement but a different autorouted result.

Cables are plain female-female Dupont jumper wires, one per signal, so any DUT header order works. Plugging one onto the wrong pin is harmless: there is no VCC pin, and both lines have 220R in series behind an LVC buffer.

The back silkscreen has a write-on box for each channel where you note the labgrid place name.

## Channel map

| CH | FT / EEPROM serial | interface | hub port (`uhubctl -p`) |
|----|-----|-----|-----|
| 01-04 | FT1 / SBCU-1 | 00-03 | 4 |
| 05-08 | FT2 / SBCU-2 | 00-03 | 3 |
| 09-12 | FT3 / SBCU-3 | 00-03 | 1 |
| 13-16 | FT4 / SBCU-4 | 00-03 | 2 |

The hub-port-to-FT order comes from the PCB layout: it keeps the four USB lanes from crossing.

## Design notes

- **Power:** USB bus powered. A TLV62569 buck makes 3.3 V. From the datasheets: each FT4232H draws 70 mA core (through its 1.8 V regulator) plus 30 mA typ / 60 mA max for the PHY, the hub about 100 mA, the LEDs about 1 mA each. That is about 0.55 A typical and 0.66 A worst case at 3.3 V, or 0.40 A typical and 0.49 A worst case from 5 V at 90 % buck efficiency. That sits just inside the 500 mA that a bus-powered hub may declare (hub 100 mA + 4 × 100 mA), so each FT's EEPROM must declare `max_power=100`. The hub straps are CFG_SEL=10 (default configuration, bus-powered override: individual port power switching, strap options enabled) and NON_REM=00 (all ports removable; the straps cannot mark all four ports non-removable, and it changes nothing for Linux).
- **Crystals:** 12 MHz (C9002, 20 pF CL) with 27 pF as FTDI recommends; 24 MHz (C15643, 20 pF CL) with 33 pF, per Microchip's C = 2·CL − C_stray. The previous 24 MHz part (C70590) was a 12 pF CL crystal, which would have wanted 18 pF.
- **Hard reset per FT (optional):** fit R14–R17 (0R, PRTPWRn → RESET#) and remove the matching RESET# 10k pull-ups. Then `uhubctl -a cycle -p N` resets that FT4232H. While a chip is held in reset its pins float high, so TX stays Hi-Z. As shipped these are DNP. The hub only samples BC_EN (on the PRTPWR pins) at reset, which is why they are not pulled up.
- **USB pairs:** 0.22 mm track / 0.15 mm gap on L1 over the In1 GND plane, on JLC04161H-7628 (7628 PP 0.2104 mm, Dk 4.4). JLC's own impedance solver (queried 2026-11-08) gives 93.0 Ω for a coated edge-coupled microstrip and 92.1 Ω for coplanar with the 0.3 mm GND pour. Both are inside USB 2.0's 90 Ω ±15 %. A 0.24/0.15 pair would land at 89–90 Ω. Both the hub and the FT number DM before DP counter-clockwise, so every pair needs a polarity swap. DP drops to B.Cu next to the FT for this (two vias).
- **Stackup:** 4 layers: F.Cu signal, In1 GND plane, In2 3V3 plane, B.Cu signal. Every GND/3V3 SMD pad gets its own via. All parts are on the top side. The headers are THT.

## Regenerating

Everything is scripted. You need KiCad 9 (PPA), Java 25 and Freerouting 2.5.0 (`~/research/sbc-uart/tools/`).

```
python3 gen/mkfp.py          # project footprint hw/lib/sbcu.pretty (edge-mounted right-angle header)
python3 gen/design.py        # schematic  (hw/*.kicad_sch), then: kicad-cli sch erc
python3 gen/build_pcb.py     # netlist -> placement, USB pairs, planes, GND/3V3 fan-out
python3 gen/route.py 100     # Freerouting (~11 min) -> routed board; may leave a few open, check DRC
python3 gen/finish.py        # silkscreen, outer GND pours, cleanup, zone fill
python3 gen/fab.py --boards 5  # gerbers zip, BOM/CPL, PDF, renders, JLC stock check
```

The KiCad library has no 3D models for J1 (HRO TYPE-C-31-M-12) and L1. Models from LCSC/EasyEDA are in `hw/lib/3d/`, and `finish.py` assigns them.

`hw/build/` (not committed) holds the netlist, the DSN/SES files and `routed-1.kicad_pcb` (the raw autorouter output). You can re-run `finish.py` on a copy of it.

## Ordering (JLCPCB)

- PCB: 4 layers, 1.6 mm, impedance control with stackup **JLC04161H-7628**. Upload `fab/sbc-uart-hub-gerbers.zip`.
- PCBA: top side, with `fab/bom_jlc.csv` and `fab/cpl_jlc.csv`. The headers are through-hole and need THT assembly.
- CPL rotations and offsets are measured, not guessed. `gen/jlc_rot.py` fits each KiCad footprint onto JLC's own EasyEDA footprint for that LCSC part. It matches pads by number, LEDs by the cathode pin name, and rejects any rotation that puts the part body on the wrong side (needed for the headers, whose pad numbering is mirrored against JLC's, and in general for anything with a symmetric pad row). The result goes to `gen/jlc_rot.json`, which `fab.py` applies. Checked on 2026-11-08: every pad lands within 0.21 mm of JLC's pad, pin 1 or the cathode is in place on all 286 placements, and the header bodies and the USB-C point off the board edge.
  - The same KiCad footprint can need different rotations: the three SOT-23-6 parts need 270, 270 and 180.
  - JLC centres the headers on the middle pin, and the USB-C 1.6 mm off the KiCad origin.
  - It still assumes JLC places parts at the EasyEDA footprint origin. Glance at the USB-C and the headers in the PCBA preview.
- To refetch the footprints: `easyeda2kicad --footprint --symbol --lcsc_id=C.. --output <dir>/C../lib` per part (the API rate-limits, so pace the requests). Then run `python3 gen/jlc_rot.py <dir>`.
- Cost (5 boards, Nov 2026): about $59 of parts per board. The four FT4232HL are $50 of that.

## Bring-up

1. `lsusb` shows the hub and 4× `0403:6011`.
2. Run `host/program-eeproms.sh <hub-sysfs-name>`, then replug. Check the serials `SBCU-1..4`.
3. Install `host/70-sbc-uart-hub.rules`. You get `/dev/sbcu/ch01..16`.
4. Loopback test: wire CH01 TX to CH02 RX.
   - With the port closed, TX must read Hi-Z (100k to GND gives 0 V).
   - With the port open, data must pass at 115200 and 1.5 Mbaud.
5. Back-power test: with the DUT off and the port closed, the DUT 3.3 V rail stays at 0 V. Repeat with the USB cable unplugged.
6. Labgrid: see `host/labgrid-exporter.yaml`. TX is only gated while nobody holds the port open. Check that your ser2net setup opens the tty only while a client is connected, so DTR drops in between.
