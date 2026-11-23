#!/usr/bin/env python3
"""
tv_sender.py - runs ON the rooted TV. Reads a block device, hashes it during the
single read pass (SHA-256 + MD5), and streams the raw bytes to pi_receiver.py
over the direct Ethernet link. Writes NOTHING to the TV's flash.

Run as root (needed to read /dev/mmcblk0). Requires a working python3 on the TV
(check `which python3` first - webOS often has none; see fallbacks in the notes).

  python3 tv_sender.py 10.0.0.1 --source /dev/mmcblk0 --case 42 --examiner "J. Doe"
  # whole eMMC is the default; run once per device/partition you want:
  python3 tv_sender.py 10.0.0.1 --source /dev/mmcblk0boot0
"""
import argparse, datetime, hashlib, json, os, socket, sys

CHUNK = 4 * 1024 * 1024


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def device_size(path):
    with open(path, "rb", buffering=0) as f:
        size = f.seek(0, os.SEEK_END)
    if size:
        return size
    # fallback: /proc/partitions (1 KiB blocks)
    name = os.path.basename(path)
    for line in (read_text("/proc/partitions") or "").splitlines()[2:]:
        fld = line.split()
        if len(fld) == 4 and fld[3] == name:
            return int(fld[2]) * 1024
    return None


def collect_metadata():
    u = os.uname()
    meta = {
        "uname": f"{u.sysname} {u.nodename} {u.release} {u.version} {u.machine}",
        "partitions": read_text("/proc/partitions"),
        "mounts": read_text("/proc/mounts"),
        "meminfo": "\n".join((read_text("/proc/meminfo") or "").splitlines()[:3]),
        "cpu": next((l for l in (read_text("/proc/cpuinfo") or "").splitlines()
                     if l.lower().startswith(("hardware", "model"))), None),
    }
    for label, path in (("os_release", "/etc/os-release"),
                        ("starfish_release", "/etc/starfish-release"),
                        ("webos_os_info", "/var/run/nyx/os_info.json"),
                        ("webos_device_info", "/var/run/nyx/device_info.json")):
        val = read_text(path)
        if val:
            meta[label] = val
    return {k: v for k, v in meta.items() if v}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pi_host", help="Pi's address on the direct link, e.g. 10.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--source", default="/dev/mmcblk0", help="block device to image")
    p.add_argument("--case", default="")
    p.add_argument("--examiner", default="")
    args = p.parse_args()

    size = device_size(args.source)
    header = {
        "source": args.source, "size": size, "case": args.case,
        "examiner": args.examiner, "start_utc": utc(),
        "chunk": CHUNK, "tv_metadata": collect_metadata(),
    }

    sha, md5, sent = hashlib.sha256(), hashlib.md5(), 0
    s = socket.create_connection((args.pi_host, args.port))
    s.sendall((json.dumps(header) + "\n").encode())
    with open(args.source, "rb", buffering=0) as dev:
        while True:
            buf = dev.read(CHUNK)
            if not buf:
                break
            s.sendall(buf); sha.update(buf); md5.update(buf); sent += len(buf)
            if size:
                print(f"\r{args.source}: {sent*100//size:3d}%  {sent}/{size}",
                      end="", file=sys.stderr)
            else:
                print(f"\r{args.source}: {sent} bytes", end="", file=sys.stderr)
    print(file=sys.stderr)

    trailer = {"source_sha256": sha.hexdigest(), "source_md5": md5.hexdigest(),
               "bytes_sent": sent, "end_utc": utc()}
    s.sendall((json.dumps(trailer) + "\n").encode())
    s.shutdown(socket.SHUT_WR)
    s.close()
    print(json.dumps(trailer, indent=2), file=sys.stderr)
    if size and sent != size:
        print(f"WARNING: sent {sent} != device size {size}", file=sys.stderr)


if __name__ == "__main__":
    main()