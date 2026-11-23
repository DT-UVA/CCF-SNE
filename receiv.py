#!/usr/bin/env python3
"""
pi_receiver.py - evidence collector, runs on the Raspberry Pi.
 
Listens on a TCP port (point it at the direct TV<->Pi Ethernet link). For each
connection from tv_sender.py it reads a JSON header, streams the raw image to
disk while hashing it (SHA-256 + MD5), reads the JSON trailer with the TV's
source-side hashes, and cross-checks them against what actually arrived. Writes
a per-image JSON log and appends to a session manifest.
 
Run the Pi's evidence disk wiped and dedicated. Keep this link off any other
network (direct cable, static IPs).
 
  python3 pi_receiver.py /mnt/evidence --case 42 --examiner "J. Doe"
  python3 pi_receiver.py /mnt/evidence --host 10.0.0.1 --port 9000
"""
import argparse, datetime, hashlib, json, os, socket, sys
 
CHUNK = 4 * 1024 * 1024
 
 
def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
 
 
def handle(conn, addr, args):
    f = conn.makefile("rb")
    header_line = f.readline()
    if not header_line:
        print(f"[{addr}] empty connection, ignoring", file=sys.stderr)
        return
    hdr = json.loads(header_line)
    size = hdr.get("size")
    src_name = os.path.basename(hdr.get("source", "image"))
    tag = (args.case + "_") if args.case else ""
    out_path = os.path.join(args.outdir, f"{tag}{src_name}.img")
    if os.path.exists(out_path):
        print(f"[{addr}] REFUSING to overwrite {out_path}; skipping", file=sys.stderr)
        return
 
    print(f"[{addr}] receiving {hdr.get('source')} -> {out_path} "
          f"({size if size else '?'} bytes)", file=sys.stderr)
    sha, md5, received = hashlib.sha256(), hashlib.md5(), 0
    recv_start = utc()
    with open(out_path, "xb") as dst:
        remaining = size if size else None
        while remaining is None or remaining > 0:
            want = CHUNK if remaining is None else min(CHUNK, remaining)
            buf = f.read(want)
            if not buf:
                break
            dst.write(buf); sha.update(buf); md5.update(buf); received += len(buf)
            if remaining is not None:
                remaining -= len(buf)
                print(f"\r  {received*100//size:3d}%  {received}/{size}", end="", file=sys.stderr)
            else:
                print(f"\r  {received} bytes", end="", file=sys.stderr)
        dst.flush(); os.fsync(dst.fileno())
    print(file=sys.stderr)
 
    trailer = {}
    tline = f.readline()
    if tline:
        try:
            trailer = json.loads(tline)
        except json.JSONDecodeError:
            trailer = {"parse_error": tline.decode(errors="replace")[:200]}
 
    recv_sha = sha.hexdigest()
    src_sha = trailer.get("source_sha256")
    log = {
        "case": args.case, "examiner": args.examiner, "peer": f"{addr[0]}:{addr[1]}",
        "recv_start_utc": recv_start, "recv_end_utc": utc(),
        "output": out_path, "expected_bytes": size, "received_bytes": received,
        "size_match": (size in (None, received)),
        "received_sha256": recv_sha, "received_md5": md5.hexdigest(),
        "tv_header": hdr, "tv_trailer": trailer,
        "source_hash_matches_received": (src_sha == recv_sha) if src_sha else None,
    }
    log_path = out_path + ".receive.json"
    with open(log_path, "w") as lf:
        json.dump(log, lf, indent=2)
    with open(os.path.join(args.outdir, f"{tag}session_manifest.jsonl"), "a") as mf:
        mf.write(json.dumps({k: log[k] for k in
                 ("output", "received_bytes", "size_match",
                  "received_sha256", "source_hash_matches_received")}) + "\n")
 
    ok = log["size_match"] and (log["source_hash_matches_received"] is not False)
    print(f"[{addr}] {'OK' if ok else 'CHECK FAILED'}  sha256={recv_sha}", file=sys.stderr)
    if log["source_hash_matches_received"] is None:
        print("  (no source hash from TV to cross-check)", file=sys.stderr)
    print(f"  log: {log_path}", file=sys.stderr)
 
 
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("outdir", help="evidence directory on the Pi")
    p.add_argument("--host", default="0.0.0.0", help="bind address (default all)")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--case", default="")
    p.add_argument("--examiner", default="")
    p.add_argument("--once", action="store_true", help="exit after one image")
    args = p.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
 
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(1)
    print(f"Listening on {args.host}:{args.port}  (Ctrl-C to stop)", file=sys.stderr)
    try:
        while True:
            conn, addr = srv.accept()
            try:
                handle(conn, addr, args)
            except Exception as e:  # keep the server alive for the next device
                print(f"[{addr}] error: {e}", file=sys.stderr)
            finally:
                conn.close()
            if args.once:
                break
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
    finally:
        srv.close()
 
 
if __name__ == "__main__":
    main()
 