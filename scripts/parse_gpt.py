import struct

def parse_gpt(path):
    with open(path, "rb") as f:
        d = f.read()
    hdr = d.find(b"EFI PART")
    entry_lba = struct.unpack("<Q", d[hdr+72:hdr+80])[0]
    nentries = struct.unpack("<I", d[hdr+80:hdr+84])[0]
    esize = struct.unpack("<I", d[hdr+84:hdr+88])[0]
    base = hdr + entry_lba * 512
    print(f"{path}: entries@{base}, n={nentries}")
    for i in range(nentries):
        e = d[base + i*esize : base + (i+1)*esize]
        if len(e) < 128 or e[0:16] == b"\x00"*16:
            continue
        first = struct.unpack("<Q", e[32:40])[0]
        last = struct.unpack("<Q", e[40:48])[0]
        name = e[56:128].decode("utf-16-le", "replace").rstrip("\x00")
        size_gb = (last - first + 1) * 512 / 2**30
        print(f"  {name:<16} LBA {first}..{last}  size={size_gb:.2f} GiB")
    return

img = r"D:\DSH\ota\_ota\TB323_ZUXOS_2.0.12.088_Tool\TB323_ZUXOS_2.0.12.088_Tool\image"
parse_gpt(f"{img}\\gpt_main0.bin")
