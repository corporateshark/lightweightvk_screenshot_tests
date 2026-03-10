#!/usr/bin/env python3
#
# Compare rendered screenshots against reference images.
#
# Usage:
#   python3 compare_screenshots.py <rendered_dir> <reference_dir> [--threshold 1.0] [--diff-dir diffs]
#
# Exit code 0 = all tests passed, 1 = one or more tests failed, 2 = error.

import argparse
import math
import os
import struct
import sys
import zlib


def read_png(path):
    """Read a PNG file and return (width, height, pixels) where pixels is a list of (R, G, B) tuples."""
    with open(path, "rb") as f:
        data = f.read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a valid PNG file: {path}")

    chunks = []
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        chunks.append((chunk_type, chunk_data))
        pos += 12 + length

    # Parse IHDR
    ihdr = [c for c in chunks if c[0] == b"IHDR"][0][1]
    width, height, bit_depth, color_type = struct.unpack(">IIBB", ihdr[:10])

    if bit_depth != 8:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")
    if color_type not in (2, 6):  # RGB or RGBA
        raise ValueError(f"Unsupported color type: {color_type}")

    channels = 3 if color_type == 2 else 4

    # Decompress IDAT
    idat_data = b"".join(c[1] for c in chunks if c[0] == b"IDAT")
    raw = zlib.decompress(idat_data)

    stride = 1 + width * channels  # 1 byte filter per row
    pixels = []

    prev_row = [0] * (width * channels)

    for y in range(height):
        row_start = y * stride
        filter_type = raw[row_start]
        row_data = list(raw[row_start + 1 : row_start + stride])

        # Reconstruct filtered row
        recon = []
        for x in range(width * channels):
            filt = row_data[x]
            a = recon[x - channels] if x >= channels else 0
            b = prev_row[x]
            c = prev_row[x - channels] if x >= channels else 0

            if filter_type == 0:
                recon.append(filt)
            elif filter_type == 1:
                recon.append((filt + a) & 0xFF)
            elif filter_type == 2:
                recon.append((filt + b) & 0xFF)
            elif filter_type == 3:
                recon.append((filt + (a + b) // 2) & 0xFF)
            elif filter_type == 4:
                # Paeth predictor
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                recon.append((filt + pr) & 0xFF)

        prev_row = recon

        for x in range(width):
            idx = x * channels
            pixels.append((recon[idx], recon[idx + 1], recon[idx + 2]))

    return width, height, pixels


def write_png(path, width, height, pixels):
    """Write an RGB PNG file. pixels is a list of (R, G, B) tuples."""

    def make_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk + crc

    # IHDR
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB

    # Raw image data with no filter
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # no filter
        for x in range(width):
            r, g, b = pixels[y * width + x]
            raw.extend([r, g, b])

    compressed = zlib.compress(bytes(raw))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(make_chunk(b"IHDR", ihdr))
        f.write(make_chunk(b"IDAT", compressed))
        f.write(make_chunk(b"IEND", b""))


def compare_images(rendered_path, reference_path, diff_path=None, threshold=1.0):
    """
    Compare two images pixel by pixel.

    Returns (passed, rmse, diff_percentage) where:
    - passed: True if diff_percentage <= threshold
    - rmse: root mean square error across all pixels (0-255 scale)
    - diff_percentage: percentage of pixels that differ by more than a small tolerance
    """
    w1, h1, pixels1 = read_png(rendered_path)
    w2, h2, pixels2 = read_png(reference_path)

    if w1 != w2 or h1 != h2:
        print(f"  Size mismatch: rendered={w1}x{h1}, reference={w2}x{h2}")
        return False, 999.0, 100.0

    total_pixels = w1 * h1
    sum_sq = 0.0
    diff_count = 0
    per_pixel_tolerance = 2  # allow up to 2/255 difference per channel

    diff_pixels = []

    for i in range(total_pixels):
        r1, g1, b1 = pixels1[i]
        r2, g2, b2 = pixels2[i]

        dr = abs(r1 - r2)
        dg = abs(g1 - g2)
        db = abs(b1 - b2)

        sum_sq += dr * dr + dg * dg + db * db

        if dr > per_pixel_tolerance or dg > per_pixel_tolerance or db > per_pixel_tolerance:
            diff_count += 1

        if diff_path:
            # Amplify differences for visibility in diff image
            diff_pixels.append((min(dr * 10, 255), min(dg * 10, 255), min(db * 10, 255)))

    rmse = math.sqrt(sum_sq / (total_pixels * 3))
    diff_percentage = (diff_count / total_pixels) * 100.0
    passed = diff_percentage <= threshold

    if diff_path and diff_count > 0:
        os.makedirs(os.path.dirname(diff_path), exist_ok=True)
        write_png(diff_path, w1, h1, diff_pixels)

    return passed, rmse, diff_percentage


def main():
    parser = argparse.ArgumentParser(description="Compare rendered screenshots against reference images")
    parser.add_argument("rendered_dir", help="Directory containing rendered screenshots")
    parser.add_argument("reference_dir", help="Directory containing reference images")
    parser.add_argument("--threshold", type=float, default=1.0, help="Maximum allowed percentage of differing pixels (default: 1.0)")
    parser.add_argument("--diff-dir", default=None, help="Directory to save diff images (optional)")
    parser.add_argument("--update", action="store_true", help="Copy rendered images to reference directory (to create/update references)")
    args = parser.parse_args()

    if not os.path.isdir(args.rendered_dir):
        print(f"Error: rendered directory not found: {args.rendered_dir}")
        return 2

    if not os.path.isdir(args.reference_dir):
        if args.update:
            os.makedirs(args.reference_dir, exist_ok=True)
        else:
            print(f"Error: reference directory not found: {args.reference_dir}")
            return 2

    if args.update:
        import shutil

        rendered_files = sorted(f for f in os.listdir(args.rendered_dir) if f.lower().endswith(".png"))
        for filename in rendered_files:
            src = os.path.join(args.rendered_dir, filename)
            dst = os.path.join(args.reference_dir, filename)
            shutil.copy2(src, dst)
            print(f"Updated reference: {dst}")
        print(f"\n{len(rendered_files)} reference(s) updated")
        return 0

    # Find all PNG files in rendered directory
    rendered_files = sorted(f for f in os.listdir(args.rendered_dir) if f.lower().endswith(".png"))

    if not rendered_files:
        print("Error: no rendered screenshots found")
        return 2

    all_passed = True
    results = []

    max_name_len = max(len(f) for f in rendered_files)

    for filename in rendered_files:
        rendered_path = os.path.join(args.rendered_dir, filename)
        reference_path = os.path.join(args.reference_dir, filename)

        if not os.path.exists(reference_path):
            print(f"MISSING  {filename:{max_name_len}s}  no reference image found")
            all_passed = False
            results.append((filename, False, None, None))
            continue

        diff_path = os.path.join(args.diff_dir, filename) if args.diff_dir else None

        passed, rmse, diff_pct = compare_images(rendered_path, reference_path, diff_path, args.threshold)

        status = "PASS  " if passed else "FAIL  "
        print(f"{status}  {filename:{max_name_len}s}  RMSE={rmse:5.2f}  diff={diff_pct:5.2f}%  (threshold={args.threshold}%)")

        if not passed:
            all_passed = False

        results.append((filename, passed, rmse, diff_pct))

    print()
    total = len(results)
    passed_count = sum(1 for r in results if r[1])
    print(f"Results: {passed_count}/{total} passed")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
