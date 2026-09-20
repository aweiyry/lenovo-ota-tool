import struct, sys

payload_path = sys.argv[1] if len(sys.argv) > 1 else r"D:\DSH\ota\_ota\payload.bin"

def rd_varint(buf, pos):
    result = 0
    shift = 0
    while True:
        b = buf[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos

def parse_extent(sub):
    pos = 0
    start = num = None
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wtype = field >> 3, field & 7
        if wtype == 0:
            v, pos = rd_varint(sub, pos)
            if fnum == 1: start = v
            elif fnum == 2: num = v
        elif wtype == 2:
            ln, pos = rd_varint(sub, pos)
            pos += ln
        else:
            pos += 8 if wtype == 1 else 4
    return (start, num)

def parse_info(sub):
    info = {}
    pos = 0
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wtype = field >> 3, field & 7
        if wtype == 0:
            v, pos = rd_varint(sub, pos)
            if fnum == 1: info["size"] = v
        elif wtype == 2:
            ln, pos = rd_varint(sub, pos)
            if fnum == 2: info["hash"] = sub[pos:pos+ln].hex()
            pos += ln
        else:
            pos += 8 if wtype == 1 else 4
    return info

def parse_merge_ops(sub):
    """CowMergeOperation: type=f1, src_extent=f4, dst_extent=f6, data=f5, hashes=f8/f9"""
    pos = 0
    op = {}
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wtype = field >> 3, field & 7
        if wtype == 0:
            v, pos = rd_varint(sub, pos)
            if fnum == 1: op["type"] = v
            elif fnum == 2: op["f2"] = v
            elif fnum == 3: op["f3"] = v
        elif wtype == 2:
            ln, pos = rd_varint(sub, pos)
            payload = sub[pos:pos+ln]
            if fnum == 4: op["src"] = parse_extent(payload)
            elif fnum == 6: op["dst"] = parse_extent(payload)
            elif fnum == 8: op["h8"] = payload.hex()
            elif fnum == 9: op["h9"] = payload.hex()
            elif fnum == 5: op["data_len"] = len(payload)
            elif fnum == 7: op["data_len"] = len(payload)
            pos += ln
        else:
            pos += 8 if wtype == 1 else 4
    return op

def parse_partition(sub):
    part = {"name": None, "old": None, "new": None, "merge_ops": [], "install_ops": []}
    pos = 0
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wtype = field >> 3, field & 7
        if wtype == 2:
            ln, pos = rd_varint(sub, pos)
            payload = sub[pos:pos+ln]
            if fnum == 1: part["name"] = payload.decode("utf-8", "replace")
            elif fnum == 6: part["old"] = parse_info(payload)
            elif fnum == 7: part["new"] = parse_info(payload)
            elif fnum == 8: part["merge_ops"].append(parse_merge_ops(payload))
            elif fnum == 15: part["install_ops"].append(payload)
            pos += ln
        elif wtype == 0:
            _, pos = rd_varint(sub, pos)
        else:
            pos += 8 if wtype == 1 else 4
    return part

d = open(payload_path, "rb").read()
manifest_size = struct.unpack(">Q", d[12:20])[0]
manifest = d[32:32 + manifest_size]

# top-level: partitions = f13
parts = []
pos = 0
while pos < len(manifest):
    field, pos = rd_varint(manifest, pos)
    fnum, wtype = field >> 3, field & 7
    if wtype == 2:
        ln, pos = rd_varint(manifest, pos)
        if fnum == 13:
            parts.append(parse_partition(manifest[pos:pos+ln]))
        pos += ln
    elif wtype == 0:
        _, pos = rd_varint(manifest, pos)
    else:
        pos += 8 if wtype == 1 else 4

COW_TYPES = {0: "COPY", 1: "XOR", 2: "REPLACE", 3: "ZERO", 4: "XZ", 5: "BROTLI",
             6: "PUFFDIFF", 7: "ZSTD", 8: "LZ4DIFF", 9: "?", 10: "?", 11: "?"}

print(f"{'partition':<20}{'old_size':>12}{'new_size':>12}  merge_ops  src_blocks  src%  detail")
for p in parts:
    ops = p["merge_ops"]
    src_blocks = 0
    by_type = {}
    for o in ops:
        t = o.get("type")
        by_type[t] = by_type.get(t, 0) + 1
        if o.get("src"):
            src_blocks += o["src"][1]
    old = p["old"]["size"] if p["old"] else 0
    pct = (src_blocks * 4096 * 100.0 / old) if old else 0
    dt = ", ".join(f"{COW_TYPES.get(k,k)}:{v}" for k, v in sorted(by_type.items()))
    print(f"{p['name']:<20}{old:>12}{str(p['new']['size']) if p['new'] else '?':>12}  {len(ops):>9}  {src_blocks:>9}  {pct:>5.1f}%  {dt}")

print("\n===== source-referenced extents (must match stock) — first 8 per partition =====")
for p in parts:
    ops = p["merge_ops"]
    srcs = [o["src"] for o in ops if o.get("src")]
    if not srcs:
        continue
    print(f"\n[{p['name']}] {len(srcs)} src extents, {sum(e[1] for e in srcs)} blocks total")
    for e in srcs[:8]:
        print(f"    blocks {e[0]}-{e[0]+e[1]}  (bytes {e[0]*4096}-{(e[0]+e[1])*4096})")
    if len(srcs) > 8:
        print(f"    ... +{len(srcs)-8} more")
