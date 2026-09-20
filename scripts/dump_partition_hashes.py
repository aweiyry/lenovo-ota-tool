import struct, sys

def rd_varint(buf, pos):
    r = 0; sh = 0
    while True:
        b = buf[pos]; pos += 1
        r |= (b & 0x7F) << sh
        if not (b & 0x80): break
        sh += 7
    return r, pos

def parse_extent(sub):
    pos = 0; start = num = None
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wt = field >> 3, field & 7
        if wt == 0:
            v, pos = rd_varint(sub, pos)
            if fnum == 1: start = v
            elif fnum == 2: num = v
        elif wt == 2:
            ln, pos = rd_varint(sub, pos); pos += ln
        else:
            pos += 8 if wt == 1 else 4
    return (start, num)

def parse_merge_ops(sub):
    pos = 0; op = {}
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wt = field >> 3, field & 7
        if wt == 0:
            v, pos = rd_varint(sub, pos)
            if fnum == 1: op["type"] = v
        elif wt == 2:
            ln, pos = rd_varint(sub, pos)
            payload = sub[pos:pos+ln]
            if fnum == 4: op["src"] = parse_extent(payload)
            elif fnum == 6: op["dst"] = parse_extent(payload)
            elif fnum == 8: op["h8"] = payload.hex()
            elif fnum == 9: op["h9"] = payload.hex()
            elif fnum == 5: op["dlen"] = len(payload)
            pos += ln
        else:
            pos += 8 if wt == 1 else 4
    return op

def parse_partition(sub):
    part = {"name": None, "ops": []}
    pos = 0
    while pos < len(sub):
        field, pos = rd_varint(sub, pos)
        fnum, wt = field >> 3, field & 7
        if wt == 2:
            ln, pos = rd_varint(sub, pos)
            payload = sub[pos:pos+ln]
            if fnum == 1: part["name"] = payload.decode("utf-8", "replace")
            elif fnum == 8: part["ops"].append(parse_merge_ops(payload))
            pos += ln
        elif wt == 0:
            _, pos = rd_varint(sub, pos)
        else:
            pos += 8 if wt == 1 else 4
    return part

d = open(sys.argv[1], "rb").read()
ms = struct.unpack(">Q", d[12:20])[0]
man = d[32:32+ms]
parts = []
pos = 0
while pos < len(man):
    field, pos = rd_varint(man, pos)
    fnum, wt = field >> 3, field & 7
    if wt == 2:
        ln, pos = rd_varint(man, pos)
        if fnum == 13:
            parts.append(parse_partition(man[pos:pos+ln]))
        pos += ln
    elif wt == 0:
        _, pos = rd_varint(man, pos)
    else:
        pos += 8 if wt == 1 else 4

# output: for each partition with src extents, print extents + hashes (JSON-ish)
import json
out = {}
for p in parts:
    srcs = []
    for o in p["ops"]:
        if o.get("src"):
            srcs.append({"t": o.get("type"), "s": o["src"][0], "n": o["src"][1],
                         "h8": o.get("h8"), "h9": o.get("h9"), "dl": o.get("dlen")})
    if srcs:
        out[p["name"]] = srcs
print(json.dumps(out))
