import re, os

xml_path = r"D:\DSH\ota\_ota\TB323_ZUXOS_2.0.12.088_Tool\TB323_ZUXOS_2.0.12.088_Tool\image\rawprogram_save_persist_unsparse0.xml"
img_dir = r"D:\DSH\ota\_ota\TB323_ZUXOS_2.0.12.088_Tool\TB323_ZUXOS_2.0.12.088_Tool\image"
out = r"D:\build211\super\super_raw.img"

entries = []
for m in re.finditer(r'<program\s+([^>]+?)/>', open(xml_path, encoding="utf-8").read()):
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
    if attrs.get("label", "").startswith("super"):
        entries.append((int(attrs["start_sector"]), int(attrs.get("num_partition_sectors", 0)), attrs.get("filename", "")))
entries.sort()
base = entries[0][0]  # super partition start (device sector)
print("super start (device sector):", base)
total_sectors = max(s + n for s, n, f in entries) - base
total = total_sectors * 4096
print(f"super size: {total_sectors} sectors = {total/2**30:.2f} GiB")

if not os.path.exists(out) or os.path.getsize(out) != total:
    with open(out, "wb") as fh:
        fh.seek(total - 1)
        fh.write(b"\0")

with open(out, "r+b") as fh:
    for s, n, f in entries:
        if not f:
            continue
        src = os.path.join(img_dir, f)
        data = open(src, "rb").read()
        off = (s - base) * 4096
        assert off + len(data) <= total, f"{f} overflow"
        fh.seek(off)
        fh.write(data)
        print(f"wrote {f} ({len(data)} bytes) at super offset {off}")

print("done:", out, os.path.getsize(out))
