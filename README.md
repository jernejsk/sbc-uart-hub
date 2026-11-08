# SBC UART hub (rev A)

A 16-channel 3.3 V debug-UART adapter for the SBC farm, connected over one USB cable.

```
USB-C ── USBLC6 ── USB2514B hub ──┬── FT4232HL #1  CH01-04 (top row, left)
                                  ├── FT4232HL #2  CH05-08 (top row, right)
                                  ├── FT4232HL #3  CH09-12 (bottom row, left)
                                  └── FT4232HL #4  CH13-16 (bottom row, right)
```

Each channel works as follows:

- The FT TXD goes through a 74LVC125 buffer, then 220R, to the JST-XH connector. The buffer's /OE is that channel's DTR#.
- The connector RX comes in through 220R and the 74LVC125 (always enabled) to the FT RXD.
- The ESDA6V1-5SC6 clamps the connector pins to GND only. It has no VCC rail.
- A green LED lights while DTR is asserted, which means the port is open and TX is driven.

TX is Hi-Z whenever the port is closed. LVC parts have Ioff, so both TX and RX are also Hi-Z when the board is unpowered. As a result the DUT is never back-powered, and the cable carries no VCC.

## Connector (JST-XH 3-pin, B3B-XH-A)

| pin | signal | direction |
|-----|--------|-----------|
| 1 (square) | GND | |
| 2 | TX | adapter → DUT RX |
| 3 | RX | DUT TX → adapter |

The top-row connectors are rotated 180°, so pin 1 is on the right. The back silkscreen has a write-on box for each channel where you note the labgrid place name.

## Channel map

| CH | FT / EEPROM serial | interface | hub port (`uhubctl -p`) |
|----|-----|-----|-----|
| 01-04 | FT1 / SBCU-1 | 00-03 | 4 |
| 05-08 | FT2 / SBCU-2 | 00-03 | 3 |
| 09-12 | FT3 / SBCU-3 | 00-03 | 1 |
| 13-16 | FT4 / SBCU-4 | 00-03 | 2 |

The hub-port-to-FT order comes from the PCB layout: it keeps the four USB lanes from crossing.

## Design notes

- **Power:** USB bus powered. A TLV62569 buck makes 3.3 V. Expect about 0.5 A at 3.3 V worst case, which is about 0.4 A from 5 V. The hub is strapped for bus power (CFG_SEL=10), so each FT's EEPROM must declare `max_power=100`.
- **Hard reset per FT (optional):** fit R14–R17 (0R, PRTPWRn → RESET#) and remove the matching RESET# 10k pull-ups. Then `uhubctl -a cycle -p N` resets that FT4232H. While a chip is held in reset its pins float high, so TX stays Hi-Z. As shipped these are DNP. The hub only samples BC_EN (on the PRTPWR pins) at reset, which is why they are not pulled up.
- **USB pairs:** 0.22 mm track / 0.15 mm gap on L1 over the In1 GND plane, for 90 Ω on JLC04161H-7628. **Check this in the JLC impedance calculator before ordering.** It was taken from one forum data point (≈85 Ω at 0.205/0.10) with the gap widened. Both the hub and the FT number DM before DP counter-clockwise, so every pair needs a polarity swap. DP drops to B.Cu next to the FT for this (two vias).
- **Stackup:** 4 layers: F.Cu signal, In1 GND plane, In2 3V3 plane, B.Cu signal. Every GND/3V3 SMD pad gets its own via. All parts are on the top side. The JST connectors are THT.

## Regenerating

Everything is scripted. You need KiCad 9 (PPA), Java 25 and Freerouting 2.5.0 (`~/research/sbc-uart/tools/`).

```
python3 gen/design.py        # schematic  (hw/*.kicad_sch), then: kicad-cli sch erc
python3 gen/build_pcb.py     # netlist -> placement, USB pairs, planes, GND/3V3 fan-out
python3 gen/route.py 100     # Freerouting (~11 min) -> routed board
python3 gen/finish.py        # silkscreen, outer GND pours, cleanup, zone fill
python3 gen/fab.py --boards 5  # gerbers zip, BOM/CPL, PDF, renders, JLC stock check
```

`hw/build/` (not committed) holds the netlist, the DSN/SES files and `routed-1.kicad_pcb` (the raw autorouter output). You can re-run `finish.py` on a copy of it.

## Ordering (JLCPCB)

- PCB: 4 layers, 1.6 mm, impedance control with stackup **JLC04161H-7628**. Upload `fab/sbc-uart-hub-gerbers.zip`.
- PCBA: top side, with `fab/bom_jlc.csv` and `fab/cpl_jlc.csv`. The JST connectors are through-hole and need THT assembly.
- **In the PCBA preview, check the rotation and pin 1 of every part.** The CPL applies the usual offsets: SOT-23 at 180°, and TSSOP/LQFP/QFN at 270°. The USB-C, the JST-XH, the LEDs (cathode = pin 1) and the crystals are not corrected, so check them by eye.
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
