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
        f, pos = rd_varint(sub, pos)
        fn, wt = f >> 3, f & 7
        if wt == 0:
            v, pos = rd_varint(sub, pos)
            if fn == 1: start = v
            elif fn == 2: num = v
        elif wt == 2:
            ln, pos = rd_varint(sub, pos); pos += ln
        else:
            pos += 8 if wt == 1 else 4
    return (start, num)

def dump_merge_op(sub, indent="      "):
    """Dump ALL fields of one CowMergeOperation with wire types."""
    pos = 0
    fields = []
    while pos < len(sub):
        f, pos = rd_varint(sub, pos)
        fn, wt = f >> 3, f & 7
        if wt == 0:
            v, pos = rd_varint(sub, pos)
            fields.append(f"{indent}f{fn} varint = {v}")
        elif wt == 1:
            v = sub[pos:pos+8]; pos += 8
            fields.append(f"{indent}f{fn} fixed64 = {v.hex()}")
        elif wt == 2:
            ln, pos = rd_varint(sub, pos)
            payload = sub[pos:pos+ln]; pos += ln
            if fn in (4, 6) and len(payload) <= 16:
                ext = parse_extent(payload)
                fields.append(f"{indent}f{fn} LEN({ln}) Extent{{start={ext[0]}, num={ext[1]}}}")
            elif len(payload) == 32:
                fields.append(f"{indent}f{fn} LEN(32) hash={payload.hex()[:24]}...")
            elif len(payload) <= 20:
                fields.append(f"{indent}f{fn} LEN({ln}) raw={payload.hex()}")
            else:
                fields.append(f"{indent}f{fn} LEN({ln}) ...")
        elif wt == 5:
            v = sub[pos:pos+4]; pos += 4
            fields.append(f"{indent}f{fn} fixed32 = {v.hex()}")
        else:
            fields.append(f"{indent}f{fn} wire{wt} (group)")
            break
    return "\n".join(fields)

def main(path):
    d = open(path, "rb").read()
    ms = struct.unpack(">Q", d[12:20])[0]
    man = d[32:32+ms]
    # find partition "system"
    pos = 0
    while pos < len(man):
        f, pos = rd_varint(man, pos)
        fn, wt = f >> 3, f & 7
        if wt == 2:
            ln, pos = rd_varint(man, pos)
            sub = man[pos:pos+ln]; pos += ln
            if fn != 13:
                continue
            # partition name?
            q = 0; name = None
            while q < len(sub):
                g, q = rd_varint(sub, q)
                gn, gwt = g >> 3, g & 7
                if gwt == 2:
                    l2, q = rd_varint(sub, q)
                    payload = sub[q:q+l2]; q += l2
                    if gn == 1:
                        name = payload.decode("utf-8", "replace")
                elif gwt == 0:
                    v, q = rd_varint(sub, q)
                else:
                    break
            if name == "system":
                print("found partition: system")
                # walk merge ops (f8), collect first op of each type 8,9,10
                q = 0; ops_by_type = {}
                while q < len(sub):
                    g, q = rd_varint(sub, q)
                    gn, gwt = g >> 3, g & 7
                    if gwt == 2:
                        l2, q = rd_varint(sub, q)
                        payload = sub[q:q+l2]; q += l2
                        if gn == 8:  # merge op
                            t = None
                            r = 0
                            while r < len(payload):
                                h, r = rd_varint(payload, r)
                                if (h >> 3) == 1 and (h & 7) == 0:
                                    t, r = rd_varint(payload, r)
                                    break
                                elif h & 7 == 0:
                                    v, r = rd_varint(payload, r)
                                elif h & 7 == 2:
                                    ll, r = rd_varint(payload, r); r += ll
                                else:
                                    break
                            if t in (8, 9, 10) and t not in ops_by_type:
                                ops_by_type[t] = payload
                    elif gwt == 0:
                        v, q = rd_varint(sub, q)
                    else:
                        break
                for t in sorted(ops_by_type):
                    print(f"\n===== type {t} 的第一个操作 =====")
                    print(dump_merge_op(ops_by_type[t]))
                return

main(sys.argv[1])
