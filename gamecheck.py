#!/usr/bin/env python3
"""Free Minecraft Java / Rust server check (from emil.spawnrack.com).

Usage: gamecheck.py minecraft HOST[:PORT] [-n 20] [-o out.json]
       gamecheck.py rust HOST[:PORT]     (PORT = Steam query port, default 28015)

Public, read-only checks only: DNS (A/AAAA, SRV for Minecraft), TCP/UDP reachability,
the game's own status query, response time over N probes. Stdlib only.
"""
import argparse, json, socket, statistics, struct, subprocess, sys, time


def dns_a(host):
    out = {"A": [], "AAAA": [], "error": None}
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            key = "A" if fam == socket.AF_INET else "AAAA"
            if sa[0] not in out[key]:
                out[key].append(sa[0])
    except socket.gaierror as e:
        out["error"] = str(e)
    return out


def dig(name, rtype):
    try:
        r = subprocess.run(["dig", "+short", rtype, name], capture_output=True, text=True, timeout=10)
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception as e:  # dig missing
        return ["(dig unavailable: %s)" % e]


# ---------- Minecraft Java server list ping ----------
def _varint(n):
    b = b""
    while True:
        x = n & 0x7F
        n >>= 7
        b += bytes([x | (0x80 if n else 0)])
        if not n:
            return b


def _read_varint(s):
    n = shift = 0
    while True:
        c = s.recv(1)
        if not c:
            raise IOError("connection closed")
        n |= (c[0] & 0x7F) << shift
        shift += 7
        if not c[0] & 0x80:
            return n


def mc_status(host, port, timeout=5):
    t0 = time.perf_counter()
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        hb = host.encode()
        data = _varint(0) + _varint(767) + _varint(len(hb)) + hb + struct.pack(">H", port) + _varint(1)
        s.sendall(_varint(len(data)) + data + b"\x01\x00")
        _read_varint(s)  # packet length
        _read_varint(s)  # packet id
        ln = _read_varint(s)
        buf = b""
        while len(buf) < ln:
            chunk = s.recv(ln - len(buf))
            if not chunk:
                break
            buf += chunk
        ms = (time.perf_counter() - t0) * 1000
        return json.loads(buf.decode("utf-8", "replace")), ms
    finally:
        s.close()


def mc_motd(desc):
    if isinstance(desc, str):
        return desc
    if isinstance(desc, dict):
        return desc.get("text", "") + "".join(mc_motd(x) for x in desc.get("extra", []))
    return ""


# ---------- Steam A2S_INFO (Rust and other Source-query games) ----------
def a2s_info(host, port, timeout=5):
    req = b"\xFF\xFF\xFF\xFFTSource Engine Query\x00"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        t0 = time.perf_counter()
        s.sendto(req, (host, port))
        d, _ = s.recvfrom(1400)
        if d[4:5] == b"A":  # challenge
            s.sendto(req + d[5:9], (host, port))
            d, _ = s.recvfrom(1400)
        ms = (time.perf_counter() - t0) * 1000
    finally:
        s.close()
    if d[4:5] != b"I":
        raise IOError("unexpected reply type %r" % d[4:5])
    p = 6
    def cstr():
        nonlocal p
        e = d.index(b"\x00", p)
        v = d[p:e].decode("utf-8", "replace"); p = e + 1
        return v
    name, mapname, folder, game = cstr(), cstr(), cstr(), cstr()
    p += 2
    players, maxp, bots = d[p], d[p + 1], d[p + 2]
    p += 3
    stype, env, vis, vac = chr(d[p]), chr(d[p + 1]), d[p + 2], d[p + 3]
    p += 4
    version = cstr()
    keywords = ""
    if p < len(d):
        edf = d[p]; p += 1
        if edf & 0x80: p += 2
        if edf & 0x10: p += 8
        if edf & 0x40: p += 2; cstr()
        if edf & 0x20: keywords = cstr()
    return {"name": name, "map": mapname, "folder": folder, "game": game, "players": players,
            "max_players": maxp, "bots": bots, "type": stype, "os": env, "password": bool(vis),
            "vac": bool(vac), "version": version, "keywords": keywords}, ms


def probe(fn, n):
    times, errors, first = [], [], None
    for _ in range(n):
        try:
            info, ms = fn()
            first = first or info
            times.append(round(ms, 1))
        except Exception as e:
            errors.append(str(e))
        time.sleep(0.5)
    return first, times, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game", choices=["minecraft", "rust"])
    ap.add_argument("address")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("-o")
    a = ap.parse_args()
    host, _, port = a.address.partition(":")
    res = {"game": a.game, "address": a.address, "checked_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
           "dns": dns_a(host), "srv": None, "target": None, "query": None, "times_ms": [], "errors": []}
    if a.game == "minecraft":
        tgt_host, tgt_port = host, int(port or 25565)
        if not port:
            srv = dig("_minecraft._tcp." + host, "SRV")
            res["srv"] = srv
            if srv and not srv[0].startswith("("):
                parts = srv[0].split()
                tgt_port, tgt_host = int(parts[2]), parts[3].rstrip(".")
        res["target"] = "%s:%d" % (tgt_host, tgt_port)
        info, times, errs = probe(lambda: mc_status(tgt_host, tgt_port), a.n)
        if info:
            pl = info.get("players", {})
            res["query"] = {"version": info.get("version", {}).get("name"), "protocol": info.get("version", {}).get("protocol"),
                            "motd": mc_motd(info.get("description", "")).strip(), "players": pl.get("online"),
                            "max_players": pl.get("max"), "has_icon": "favicon" in info,
                            "enforces_secure_chat": info.get("enforcesSecureChat")}
    else:
        # Rust answers the Steam query on its query port, often game port +1 (28016); try +0..+2.
        base = int(port or 28015)
        tgt_port = base
        for cand in (base, base + 1, base + 2):
            try:
                a2s_info(host, cand, timeout=3)
                tgt_port = cand
                break
            except Exception:
                continue
        res["target"] = "%s:%d" % (host, tgt_port)
        res["query_port_note"] = "game port given %d, query answered on %d" % (base, tgt_port)
        info, times, errs = probe(lambda: a2s_info(host, tgt_port), a.n)
        res["query"] = info
    res["times_ms"], res["errors"] = times, errs
    if times:
        res["median_ms"] = statistics.median(times)
        res["worst_ms"] = max(times)
    res["answered"] = "%d of %d" % (len(times), a.n)
    out = json.dumps(res, indent=2, ensure_ascii=False)
    if a.o:
        open(a.o, "w").write(out)
    print(out)


if __name__ == "__main__":
    main()
