#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验「增量包源镜像」是否正确 —— 排错用

增量包（delta payload）里每个分区的 manifest 都记录了该分区在 pre-build 版本中的
SHA256（old_partition_info.hash）。把手里准备的源镜像算一遍哈希比对即可确认能不能用；
SOUTCE_COPY 类操作还会逐块记录 src_sha256_hash，可精确定位是哪些块对不上
（设备 dd 出来、被 root / 换内核改过的分区就是在这里露馅的）。

用法:
    python verify_delta_source.py <payload.bin> <分区名> <源镜像.img>

例:
    python verify_delta_source.py payload.bin init_boot 222_init_boot.img
"""
import sys
import struct
import hashlib

TYPES = {0: "REPLACE", 1: "REPLACE_BZ", 2: "MOVE", 3: "BSDIFF", 4: "SOURCE_COPY",
         5: "SOURCE_BSDIFF", 6: "ZERO", 7: "DISCARD", 8: "REPLACE_XZ",
         9: "PUFFDIFF", 10: "BROTLI_BSDIFF", 11: "ZUCCHINI"}


def rd_varint(buf, pos):
    r = 0
    sh = 0
    while True:
        b = buf[pos]
        pos += 1
        r |= (b & 0x7F) << sh
        if not (b & 0x80):
            return r, pos
        sh += 7


def fields(buf, start, end):
    i = start
    out = []
    while i < end:
        key, i = rd_varint(buf, i)
        fno, wt = key >> 3, key & 7
        if wt == 0:
            v, i = rd_varint(buf, i)
        elif wt == 2:
            ln, i = rd_varint(buf, i)
            v = (i, i + ln)
            i += ln
        elif wt == 5:
            v = buf[i:i + 4]
            i += 4
        elif wt == 1:
            v = buf[i:i + 8]
            i += 8
        else:
            raise ValueError(f"wire type {wt}")
        out.append((fno, wt, v))
    return out


def extent(buf, s, e):
    st = nb = None
    for f, w, v in fields(buf, s, e):
        if w == 0:
            if f == 1:
                st = v
            elif f == 2:
                nb = v
    return st, nb


def load_manifest(payload):
    with open(payload, "rb") as f:
        head = f.read(24)
        if head[:4] != b"CrAU":
            raise SystemExit("不是 Android/ChromeOS OTA payload 文件")
        msize = struct.unpack(">Q", head[12:20])[0]
        man = f.read(msize)
    bs = 4096
    for f, w, v in fields(man, 0, len(man)):
        if f == 3 and w == 0:
            bs = v
    return man, bs


def find_partition(man, name):
    for f, w, v in fields(man, 0, len(man)):
        if f != 13 or w != 2:
            continue
        nm = None
        old = new = None
        ops = []
        for g, w2, v2 in fields(man, v[0], v[1]):
            if g == 1 and w2 == 2:
                nm = man[v2[0]:v2[1]].decode("utf-8", "replace")
            elif g in (6, 7) and w2 == 2:
                h = None
                for h3, w3, v3 in fields(man, v2[0], v2[1]):
                    if h3 == 2 and w3 == 2:
                        h = man[v3[0]:v3[1]].hex()
                if g == 6:
                    old = h
                else:
                    new = h
            elif g == 8 and w2 == 2:
                op = {"type": None, "src": [], "dst": [], "ssha": None, "dsha": None}
                for h3, w3, v3 in fields(man, v2[0], v2[1]):
                    if h3 == 1 and w3 == 0:
                        op["type"] = v3
                    elif h3 == 4 and w3 == 2:
                        op["src"].append(extent(man, v3[0], v3[1]))
                    elif h3 == 6 and w3 == 2:
                        op["dst"].append(extent(man, v3[0], v3[1]))
                    elif h3 == 9 and w3 == 2:
                        op["ssha"] = man[v3[0]:v3[1]].hex()
                    elif h3 == 8 and w3 == 2:
                        op["dsha"] = man[v3[0]:v3[1]].hex()
                ops.append(op)
        if nm == name:
            return old, new, ops
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    payload, part_name, img = sys.argv[1], sys.argv[2], sys.argv[3]
    man, bs = load_manifest(payload)
    got = find_partition(man, part_name)
    if not got:
        print(f"[错误] 该 payload 里没有分区 {part_name}（两版之间未变化的分区不会出现在增量包中）")
        return 1
    old, new, ops = got
    print(f"payload      : {payload}")
    print(f"分区         : {part_name}   (block = {bs} B)")
    print(f"pre-build 哈希: {old}")
    print(f"target   哈希: {new}")
    data = open(img, "rb").read()
    act = hashlib.sha256(data).hexdigest()
    print(f"源镜像       : {img}  ({len(data)} B)")
    print(f"源镜像 sha256 : {act}")
    if old and act == old:
        print("=> 结论: 源镜像与官方 pre-build 版本一致，可用 ✅")
    elif old:
        print("=> 结论: 源镜像与官方不一致 ❌（换版本或换未修改过的官方镜像）")
    else:
        print("=> 提示: 该包未记录 pre-build 哈希（可能是全量包），逐块核对如下")

    bad = 0
    for i, op in enumerate(ops):
        if op["type"] != 4 or not op["src"]:
            continue
        st, nb = op["src"][0]
        chunk = data[st * bs:(st + nb) * bs]
        h = hashlib.sha256(chunk).hexdigest()
        ok = (h == op["ssha"])
        bad += 0 if ok else 1
        print(f"   op{i:<3} SOURCE_COPY 块 {st}..{st + nb} ({nb * bs // 1024} KB) "
              f"{'OK' if ok else '不一致'}  官方 {str(op['ssha'])[:16]}… 实际 {h[:16]}…")
    if bad:
        print(f"=> {bad} 个 SOURCE_COPY 块对不上：源镜像不是官方 pre-build 版本"
              f"（root/改内核的 init_boot、boot、vbmeta 最典型）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
