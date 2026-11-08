#!/usr/bin/env python3
"""Autoroute hw/sbc-uart-hub.kicad_pcb with Freerouting (DSN -> SES round trip).

python3 gen/route.py [passes]
"""
import os
import subprocess
import sys

import pcbnew

GEN = os.path.dirname(os.path.abspath(__file__))
HW = os.path.normpath(os.path.join(GEN, '..', 'hw'))
PCB = os.path.join(HW, 'sbc-uart-hub.kicad_pcb')
BUILD = os.path.join(HW, 'build')
JAVA = os.environ.get('JAVA', '/usr/lib/jvm/java-25-openjdk-amd64/bin/java')
JAR = os.environ.get('FREEROUTING', os.path.expanduser('~/research/sbc-uart/tools/freerouting-2.5.0.jar'))


def main():
    passes = sys.argv[1] if len(sys.argv) > 1 else '100'
    os.makedirs(BUILD, exist_ok=True)
    dsn = os.path.join(BUILD, 'sbc-uart-hub.dsn')
    ses = os.path.join(BUILD, 'sbc-uart-hub.ses')
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ExportSpecctraDSN(board, dsn):
        sys.exit('DSN export failed')
    if os.path.exists(ses):
        os.unlink(ses)
    log = open(os.path.join(BUILD, 'freerouting.log'), 'w')
    subprocess.run([JAVA, '-jar', JAR, '-de', dsn, '-do', ses, '-mp', passes, '--gui.enabled=false'],
                   stdout=log, stderr=subprocess.STDOUT, check=True)
    if not os.path.exists(ses):
        sys.exit('no SES produced, see build/freerouting.log')
    board = pcbnew.LoadBoard(PCB)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit('SES import failed')
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    print('routed ->', PCB)


if __name__ == '__main__':
    main()
