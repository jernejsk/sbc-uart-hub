#!/bin/sh
# Program the four 93LC56B EEPROMs of a fresh SBC UART hub.
# Hub port -> FT mapping is fixed by the PCB: port1=FT3 port2=FT4 port3=FT2 port4=FT1.
# Usage: program-eeproms.sh <hub sysfs name, e.g. 1-2>   (see: lsusb -t, or dmesg)
set -eu
hub=${1:?usage: $0 <hub-sysfs-name e.g. 1-2>}
dir=$(dirname "$0")
for map in 1:3 2:4 3:2 4:1; do
	port=${map%%:*}; ft=${map##*:}
	dev=/sys/bus/usb/devices/$hub.$port
	[ -e "$dev/busnum" ] || { echo "no device on $hub.$port"; exit 1; }
	bus=$(printf %03d "$(cat "$dev/busnum")"); num=$(printf %03d "$(cat "$dev/devnum")")
	echo "hub port $port -> FT$ft (d:$bus/$num)"
	ftdi_eeprom --device "d:$bus/$num" --flash-eeprom "$dir/sbcu-$ft.conf"
done
echo "done; replug the hub"
