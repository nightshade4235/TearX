#!/usr/bin/env python3
"""CR8S patient robot - final read-only sensor tester.

Tests only sensors and camera. It never:
    - enables motors
    - writes motor-driver GPIOs
    - moves the stepper
    - moves servos
    - sends UART motor commands

Current wiring:
    IR S2/S3/S4       -> BCM 27/22/23
    hardware I2C     -> one VL53L0X + MPU-6050 on bus 1
    software I2C bus3-> TCS34725 on GPIO17/GPIO26
    camera           -> Pi CSI camera

Examples:
    python3 patient_sensor_test.py --i2c
    python3 patient_sensor_test.py --ir
    python3 patient_sensor_test.py --color
    python3 patient_sensor_test.py --tof
    python3 patient_sensor_test.py --imu
    python3 patient_sensor_test.py --camera
    python3 patient_sensor_test.py --all
"""

from __future__ import annotations

import argparse
import struct
import time

# ------------------------------ wiring macros -----------------------------
IR_PINS = {"S2": 27, "S3": 22, "S4": 23}
IR_ACTIVE_LOW = True
I2C_BUS = 1
COLOR_BUS = 3
MPU_ADDRESS = 0x68
TOF_ADDRESS = 0x29
COLOR_ADDRESS = 0x29
SAMPLE_PERIOD = 0.5

# Starting colour thresholds; calibrate using real samples.
COLOR_MIN_CLEAR = 80
COLOR_WHITE_CLEAR = 1200
COLOR_MARGIN = 0.08
YELLOW_MIN_R = 0.35
YELLOW_MIN_G = 0.30
YELLOW_MAX_B = 0.22


def classify_color(red: int, green: int, blue: int, clear: int) -> str:
    if clear < COLOR_MIN_CLEAR:
        return "too_dark"
    if clear >= COLOR_WHITE_CLEAR:
        return "white"
    total = red + green + blue
    if total <= 0:
        return "unknown"
    r, g, b = red / total, green / total, blue / total
    if r >= YELLOW_MIN_R and g >= YELLOW_MIN_G and b <= YELLOW_MAX_B:
        return "yellow"
    if r >= g + COLOR_MARGIN and r >= b + COLOR_MARGIN:
        return "red"
    if g >= r + COLOR_MARGIN and g >= b + COLOR_MARGIN:
        return "green"
    if b >= r + COLOR_MARGIN and b >= g + COLOR_MARGIN:
        return "blue"
    return "unknown"


def read_ir():
    from gpiozero import Button
    sensors = {name: Button(pin, pull_up=True) for name, pin in IR_PINS.items()}
    try:
        values = {}
        for name, sensor in sensors.items():
            electrical_active = bool(sensor.is_pressed)
            values[name] = int(
                electrical_active if IR_ACTIVE_LOW else not electrical_active
            )
        return values
    finally:
        for sensor in sensors.values():
            sensor.close()


def print_ir_once():
    try:
        values = read_ir()
        print(
            f"IR S2={values['S2']} S3={values['S3']} S4={values['S4']} "
            f"all_black={int(all(values.values()))}"
        )
    except Exception as exc:
        print(f"IR ERROR: {exc}")


def scan_i2c():
    try:
        from smbus2 import SMBus
    except ImportError:
        print("I2C ERROR: install with sudo apt install python3-smbus2 i2c-tools")
        return []
    found = []
    try:
        with SMBus(I2C_BUS) as bus:
            for address in range(0x03, 0x78):
                try:
                    bus.write_quick(address)
                    found.append(address)
                except OSError:
                    pass
    except Exception as exc:
        print(f"I2C bus {I2C_BUS} ERROR: {exc}")
        return []
    print("I2C bus 1:", " ".join(f"0x{x:02X}" for x in found) or "no devices")
    print(f"  MPU-6050 0x{MPU_ADDRESS:02X}: "
          f"{'FOUND' if MPU_ADDRESS in found else 'not found'}")
    print(f"  VL53L0X  0x{TOF_ADDRESS:02X}: "
          f"{'FOUND' if TOF_ADDRESS in found else 'not found'}")
    return found


def read_imu_once():
    """Read MPU-6050 identity and raw accel/gyro registers."""
    try:
        from smbus2 import SMBus
    except ImportError:
        print("IMU ERROR: install python3-smbus2")
        return
    try:
        with SMBus(I2C_BUS) as bus:
            who = bus.read_byte_data(MPU_ADDRESS, 0x75)
            raw = bus.read_i2c_block_data(MPU_ADDRESS, 0x3B, 14)
        values = struct.unpack(">hhhhhhh", bytes(raw))
        ax, ay, az, temp, gx, gy, gz = values
        print(
            f"IMU WHO_AM_I=0x{who:02X} "
            f"accel=({ax},{ay},{az}) temp_raw={temp} gyro=({gx},{gy},{gz})"
        )
    except Exception as exc:
        print(f"IMU ERROR: {exc}")


def read_tof_once():
    try:
        import board
        import busio
        import adafruit_vl53l0x
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l0x.VL53L0X(i2c, address=TOF_ADDRESS)
        print(f"ToF distance={sensor.range} mm")
    except Exception as exc:
        print(f"TOF ERROR: {exc}")


def read_color_once():
    try:
        from adafruit_extended_bus import ExtendedI2C
        import adafruit_tcs34725
        i2c = ExtendedI2C(COLOR_BUS)
        sensor = adafruit_tcs34725.TCS34725(i2c, address=COLOR_ADDRESS)
        red, green, blue, clear = sensor.color_raw
        total = red + green + blue
        if total:
            norm = f"R={red/total:.3f} G={green/total:.3f} B={blue/total:.3f}"
        else:
            norm = "normalised=unavailable"
        print(
            f"COLOR={classify_color(red, green, blue, clear)} "
            f"raw=R:{red} G:{green} B:{blue} C:{clear} {norm}"
        )
    except Exception as exc:
        print(f"COLOR ERROR: {exc}")
        print("Check that /dev/i2c-3 exists and the TCS is wired to GPIO17/26.")


def camera_once():
    try:
        from picamera2 import Picamera2
        camera = Picamera2()
        config = camera.create_still_configuration(main={"size": (640, 480)})
        camera.configure(config)
        camera.start()
        time.sleep(0.5)
        frame = camera.capture_array()
        camera.stop()
        camera.close()
        print(f"CAMERA OK: captured frame shape={getattr(frame, 'shape', None)}")
    except Exception as exc:
        print(f"CAMERA ERROR: {exc}")


def all_once():
    scan_i2c()
    read_imu_once()
    read_tof_once()
    read_color_once()
    print_ir_once()


def wizard():
    """Run one compact test at a time; Enter advances, q stops."""
    tests = (
        ("I2C scan", scan_i2c),
        ("MPU-6050", read_imu_once),
        ("VL53L0X", read_tof_once),
        ("TCS34725 colour sensor", read_color_once),
        ("IR array S2/S3/S4", print_ir_once),
        ("Pi camera", camera_once),
    )
    print("Patient robot sensor wizard")
    print("Each test takes one reading. Press Enter for the next test; type q to stop.")
    for number, (name, test) in enumerate(tests, start=1):
        print(f"\n[{number}/{len(tests)}] {name}")
        test()
        try:
            answer = input("Press Enter to continue, or q then Enter to stop: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nWizard stopped.")
            return
        if answer == "q":
            print("Wizard stopped.")
            return
    print("\nAll sensor tests completed.")


def main():
    parser = argparse.ArgumentParser(description="Read-only patient robot sensor test")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--i2c", action="store_true", help="scan hardware I2C bus 1")
    group.add_argument("--ir", action="store_true", help="continuously read one IR array")
    group.add_argument("--color", action="store_true", help="continuously read TCS34725 bus 3")
    group.add_argument("--tof", action="store_true", help="continuously read one VL53L0X")
    group.add_argument("--imu", action="store_true", help="continuously read MPU-6050")
    group.add_argument("--camera", action="store_true", help="capture one Pi camera frame")
    group.add_argument("--all", action="store_true", help="interactive one-by-one wizard")
    group.add_argument("--wizard", action="store_true", help="interactive one-by-one wizard")
    args = parser.parse_args()

    if args.i2c:
        scan_i2c()
    elif args.camera:
        camera_once()
    elif args.all or args.wizard:
        wizard()
    else:
        print("Read-only sensor test. Press Ctrl+C to stop.")
        try:
            while True:
                if args.ir:
                    print_ir_once()
                elif args.color:
                    read_color_once()
                elif args.tof:
                    read_tof_once()
                elif args.imu:
                    read_imu_once()
                time.sleep(SAMPLE_PERIOD)
        except KeyboardInterrupt:
            print("Stopped.")


if __name__ == "__main__":
    main()
      
