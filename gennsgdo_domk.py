#!/usr/bin/env python3
"""CR8S patient robot - wiring test only.

This script DOES NOT:
    - enable motor drivers
    - write to motor GPIOs
    - move motors or the stepper
    - operate servos
    - run the mission

It only reads the six selected IR inputs, scans I2C, checks likely MPU/ToF
addresses, and optionally checks whether the Pi UART device can be opened.

BCM GPIO numbering is used.
"""

from __future__ import annotations

import argparse
import sys
import time

# ----------------------------- wiring macros ------------------------------
# From the current proposed patient-robot wiring document.
# Only S2, S3, and S4 are used; S1, CLP, and NEAR are ignored.
IR_ARRAY_1 = {
    "S2": 27,
    "S3": 22,
    "S4": 23,
}
IR_ARRAY_2 = {
    "S2": 13,
    "S3": 19,
    "S4": 16,
}

# Change to False if the boards output HIGH when active.
IR_ACTIVE_LOW = True

I2C_BUS_NUMBER = 1
MPU6050_ADDRESS = 0x68             # AD0 tied to GND normally.
VL53L0X_DEFAULT_ADDRESS = 0x29     # Two identical devices may conflict.

# Set to None to skip UART open test. Examples: /dev/serial0, /dev/ttyUSB0.
UART_DEVICE = "/dev/serial0"
UART_BAUDRATE = 115200

SAMPLE_INTERVAL_SEC = 0.25


def read_ir_once():
    try:
        from gpiozero import Button
    except ImportError as exc:
        raise RuntimeError("Install gpiozero before running this test") from exc

    sensors = {}
    for array_name, pin_map in (
        ("array1", IR_ARRAY_1),
        ("array2", IR_ARRAY_2),
    ):
        sensors[array_name] = {
            name: Button(pin, pull_up=True)
            for name, pin in pin_map.items()
        }

    print("IR input test started. Press Ctrl-C to stop.")
    print("Values are logical active states: 1 means the sensor is active.")
    print("Place black/white material under each sensor and watch for changes.\n")

    try:
        while True:
            values = {}
            for array_name, sensor_map in sensors.items():
                values[array_name] = {}
                for name, sensor in sensor_map.items():
                    electrical_pressed = bool(sensor.is_pressed)
                    logical_active = (
                        electrical_pressed
                        if IR_ACTIVE_LOW
                        else not electrical_pressed
                    )
                    values[array_name][name] = int(logical_active)

            print(
                f"A1 S2={values['array1']['S2']} "
                f"S3={values['array1']['S3']} "
                f"S4={values['array1']['S4']} | "
                f"A2 S2={values['array2']['S2']} "
                f"S3={values['array2']['S3']} "
                f"S4={values['array2']['S4']}",
                flush=True,
            )
            time.sleep(SAMPLE_INTERVAL_SEC)
    finally:
        for sensor_map in sensors.values():
            for sensor in sensor_map.values():
                sensor.close()


def scan_i2c():
    """Scan I2C without initializing or changing any device."""
    try:
        from smbus2 import SMBus
    except ImportError:
        print("I2C scan skipped: install smbus2 with 'sudo apt install python3-smbus2'.")
        return

    print(f"Scanning I2C bus {I2C_BUS_NUMBER}...")
    found = []
    try:
        with SMBus(I2C_BUS_NUMBER) as bus:
            for address in range(0x03, 0x78):
                try:
                    bus.write_quick(address)
                    found.append(address)
                except OSError:
                    pass
    except Exception as exc:
        print(f"I2C scan failed: {exc}")
        return

    if not found:
        print("No I2C devices responded.")
        return

    print("I2C addresses found:", " ".join(f"0x{x:02X}" for x in found))
    print(
        f"MPU-6050 expected at 0x{MPU6050_ADDRESS:02X}: "
        f"{'FOUND' if MPU6050_ADDRESS in found else 'not found'}"
    )
    tof_count = found.count(VL53L0X_DEFAULT_ADDRESS)
    print(
        f"VL53L0X default address 0x{VL53L0X_DEFAULT_ADDRESS:02X}: "
        f"one bus address can represent at most one visible device"
    )
    if tof_count:
        print(
            "WARNING: two identical VL53L0X sensors cannot normally share the "
            "same address without XSHUT, address hardware, or an I2C multiplexer."
        )


def test_uart():
    if UART_DEVICE is None:
        print("UART test skipped: UART_DEVICE is None")
        return

    try:
        import serial
    except ImportError:
        print("UART test skipped: install pyserial with 'sudo apt install python3-serial'.")
        return

    try:
        with serial.Serial(UART_DEVICE, UART_BAUDRATE, timeout=0.2) as port:
            print(f"UART opened successfully: {UART_DEVICE} at {UART_BAUDRATE} baud")
            print("No bytes were transmitted by this wiring test.")
    except Exception as exc:
        print(f"UART could not be opened at {UART_DEVICE}: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Safe CR8S wiring test only")
    parser.add_argument("--ir", action="store_true", help="Continuously read six IR inputs")
    parser.add_argument("--i2c", action="store_true", help="Scan the I2C bus")
    parser.add_argument("--uart", action="store_true", help="Check whether UART can be opened")
    parser.add_argument("--all", action="store_true", help="Run I2C, UART, then IR test")
    args = parser.parse_args()

    if not (args.ir or args.i2c or args.uart or args.all):
        parser.print_help()
        print("\nNothing was run. Choose --ir, --i2c, --uart, or --all.")
        return 0

    if args.all or args.i2c:
        scan_i2c()
    if args.all or args.uart:
        test_uart()
    if args.all or args.ir:
        read_ir_once()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nWiring test stopped by user.")
        raise SystemExit(0)
