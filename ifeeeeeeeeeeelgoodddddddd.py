#!/usr/bin/env python3
"""Standalone, read-only VL53L0X minimum-distance test.

This file never starts motors, servos, the stepper, or UART motor commands.
It only reads the VL53L0X on hardware I2C bus 1 at address 0x29.
"""

from __future__ import annotations

import argparse
import time

TOF_ADDRESS = 0x29
DEFAULT_SAMPLES = 100
DEFAULT_INTERVAL = 0.1
TOF_ZER = 58

def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only VL53L0X minimum-distance test")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES,
                        help="number of readings, default: 100")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help="seconds between readings, default: 0.1")
    args = parser.parse_args()

    if args.samples < 1:
        parser.error("--samples must be at least 1")
    if args.interval < 0:
        parser.error("--interval cannot be negative")

    try:
        import board
        import busio
        import adafruit_vl53l0x
    except ImportError as exc:
        print(f"TOF IMPORT ERROR: {exc}")
        print("Install the VL53L0X library on the Pi before running this test.")
        return 2

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l0x.VL53L0X(i2c, address=TOF_ADDRESS)
        readings: list[float] = []
        print(f"VL53L0X minimum-distance test: {args.samples} samples")
        print("Move a flat target closer slowly. Stop before contact.")
        atred = 0
        nodec = 0
        for number in range(1, args.samples + 1):
            value = sensor.range
            if value is None:
                print(f"{number:03d}/{args.samples}: unavailable")
            else:
                distance = float(value)
                readings.append(distance)
                print(f"{number:03d}/{args.samples}: {distance:.0f} mm")
                if distance <= TOF_ZER:
                    nodec += 1
                    print("This thing is practically enough, TURN!")
                    if nodec == 1:
                        atred = distance
            time.sleep(args.interval)

        if not readings:
            print("No valid ToF readings were received.")
            return 1

        print()
        print(f"TOF_MIN_MM={min(readings):.0f}")
        print(f"TOF_MAX_MM={max(readings):.0f}")
        print(f"TOF_LAST_MM={readings[-1]:.0f}")
        print(f"TOF_ZER={TOF_ZER:.0f} ATTAINED_READING={atred:.0f}")
        print("Use the closest stable reading as a reference; it is not automatically TOF_CLOSE_MM.")
        return 0
    except KeyboardInterrupt:
        print("\nTest stopped.")
        return 130
    except Exception as exc:
        print(f"TOF ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
