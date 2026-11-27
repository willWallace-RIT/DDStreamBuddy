#!/usr/bin/env python3
# sequential_dd_stream.py — Sequential chunked sender for an MCU block bridge

import os
import serial

SECTOR_SIZE = 512
CHUNK_BYTES = 512 * 1024  # 512 KiB sequential batch (multiple of 512)

def stream_image(port: str, baud: int, image_path: str, start_lba: int = 0):
    file_size = os.path.getsize(image_path)
    sent_sectors = 0

    with serial.Serial(port, baud, timeout=10.0) as ser, open(image_path, "rb") as f:
        ser.write(f"SEEK {start_lba}\n".encode("utf-8"))
        seek_ack = ser.readline().decode("utf-8", "replace").strip()
        if not seek_ack.startswith("OK"):
            raise RuntimeError(f"SEEK failed: {seek_ack}")

        while True:
            buf = f.read(CHUNK_BYTES)
            if not buf:
                break

            if len(buf) % SECTOR_SIZE != 0:
                pad = SECTOR_SIZE - (len(buf) % SECTOR_SIZE)
                buf += b"\x00" * pad

            blocks = len(buf) // SECTOR_SIZE
            ser.write(f"WRITE_BLOCKS {blocks}\n".encode("utf-8"))
            ready = ser.readline().decode("utf-8", "replace").strip()
            if ready != "READY":
                raise RuntimeError(f"Bridge not ready: {ready}")

            ser.write(buf)
            ser.flush()

            ack = ser.readline().decode("utf-8", "replace").strip()
            if not ack.startswith("OK"):
                raise RuntimeError(f"Write failed at LBA {start_lba + sent_sectors}: {ack}")

            sent_sectors += blocks
            pct = min(100.0, ((sent_sectors * SECTOR_SIZE) / file_size) * 100.0)
            print(f"LBA {start_lba + sent_sectors} ({pct:.1f}%)", end="\r")

        ser.write(b"FLUSH\n")
        flush_ack = ser.readline().decode("utf-8", "replace").strip()
        print(f"\nComplete: {sent_sectors} sectors written ({flush_ack})")
