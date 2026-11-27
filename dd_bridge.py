#!/usr/bin/env python3
# dd_bridge.py — User-mode CLI client that streams an image to an MCU USB-MSC bridge

import argparse
import os
import serial

DEFAULT_BS = 4096  # Multiple of 512-byte SCSI LBA size

def send_cmd(ser, line, timeout=5.0):
    ser.timeout = timeout
    ser.write((line.strip() + "\n").encode("utf-8"))
    resp = ser.readline().decode("utf-8", "replace").strip()
    return resp

def read_exact(ser, n, timeout=10.0):
    ser.timeout = timeout
    buf = bytearray()
    while len(buf) < n:
        chunk = ser.read(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)

def main():
    ap = argparse.ArgumentParser(description="Stream raw image to MCU USB Mass Storage bridge")
    ap.add_argument("--port", required=True, help="Serial/CDC port (e.g. /dev/ttyACM0 or COM5)")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--if", dest="infile", required=True, help="Input ISO/IMG file")
    ap.add_argument("--bs", type=int, default=DEFAULT_BS, help="Block size (multiple of 512)")
    ap.add_argument("--seek", type=int, default=0, help="Destination LBA block offset")
    ap.add_argument("--skip", type=int, default=0, help="Input blocks to skip")
    args = ap.parse_args()

    if args.bs % 512 != 0 or args.bs <= 0:
        raise SystemExit("Block size (--bs) must be a positive multiple of 512.")

    file_size = os.path.getsize(args.infile)
    start_byte = args.skip * args.bs
    if start_byte >= file_size:
        raise SystemExit("--skip exceeds input file size.")

    ser = serial.Serial(args.port, args.baud, timeout=5.0)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    info = send_cmd(ser, "INFO")
    print("Bridge INFO:", info)
    if not info.startswith("OK"):
        raise SystemExit(f"Device not ready: {info}")

    seek_resp = send_cmd(ser, f"SEEK {args.seek}")
    if not seek_resp.startswith("OK"):
        raise SystemExit(f"SEEK failed: {seek_resp}")

    total_written = 0
    with open(args.infile, "rb") as f:
        f.seek(start_byte)
        while True:
            chunk = f.read(args.bs)
            if not chunk:
                break
            # Pad final partial block to 512-byte boundary for raw sector writes
            if len(chunk) % 512 != 0:
                pad_len = 512 - (len(chunk) % 512)
                chunk = chunk + (b"\x00" * pad_len)

            n_blocks = len(chunk) // 512
            hdr = send_cmd(ser, f"WRITE_BLOCKS {n_blocks}")
            if hdr != "READY":
                raise SystemExit(f"Bridge rejected WRITE_BLOCKS: {hdr}")

            ser.write(chunk)
            ser.flush()

            ack = read_exact(ser, 16, timeout=15.0)
            status = ser.readline().decode("utf-8", "replace").strip()
            combined = (ack.decode("utf-8", "replace") + status).strip()
            if not combined.startswith("OK"):
                raise SystemExit(f"Sector write error at byte {total_written}: {combined}")

            total_written += len(chunk)
            if total_written % (1024 * 1024) < args.bs:
                print(f"Written: {total_written / (1024 * 1024):.1f} MiB", end="\r")

    flush_resp = send_cmd(ser, "FLUSH")
    print(f"\nDone. Total sector bytes sent: {total_written} | FLUSH: {flush_resp}")

if __name__ == "__main__":
    main()
