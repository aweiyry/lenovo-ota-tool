#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联想 OTA 查询 & 分区提取工具
支持机型：三代 TB321FU / 四代 TB322FC / 五代 TB323FU

功能：
  1. 查询：按 机型+序列号+当前版本 查询下一版本增量/全量包下载链接，支持自动走链
  2. 提取：从下载好的 OTA 包（zip）中提取指定分区镜像（内置 payload-dumper-go）
"""
import os
import re
import sys
import json
import time
import shutil
import zipfile
import tempfile
import threading
import subprocess
import urllib.parse
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

API_URL = "https://ota.lenovo.com/ota-server/firmware/query/for-text-desc"

DEVICES = [
    {"name": "三代 TB321FU (Y700 2025)", "model": "TB321FU_CN", "sn": "SN_请填你的序列号",
     "ver_hint": "TB321FU_CN_OPEN_USER_Q00002.0_W_DF_17.5.10.298_ST_260511"},
    {"name": "四代 TB322FC (Y700 2024)", "model": "TB322FC_CN", "sn": "SN_请填你的序列号",
     "ver_hint": "TB322FC_CN_OPEN_USER_Q00041.1_V_ZUXOS_1.1.11.120_ST_250727"},
    {"name": "五代 TB323FU (Y700 Gen5)", "model": "TB323FU_CN", "sn": "SN_请填你的序列号",
     "ver_hint": "TB323FU_CN_OPEN_USER_Q00020.0_A16_ZUXOS_2.0.12.199_ST_260812"},
]

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

PDG_CANDIDATES = [
    os.path.join(BUNDLE_DIR, "payload-dumper-go.exe"),
    os.path.join(BASE_DIR, "payload-dumper-go.exe"),
    r"D:\DSH\ota\_ota\pdg2\payload-dumper-go.exe",
]


def find_pdg():
    for p in PDG_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def http_post_form(url, params, timeout=25):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "User-Agent": "LenovoOtaTool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def query_next(model, sn, cur_ver, timeout=25):
    """查询下一版本，返回 dict 或 None"""
    params = {
        "action": "querynewfirmware",
        "devicemodel": model,
        "deviceid": sn,
        "curfirmwarever": cur_ver,
        "locale": "zh",
        "nationcode": "CN",
        "pid": "",
        "ChecksumType": "sha256",
    }
    xml = http_post_form(API_URL, params, timeout)
    name = re.search(r"<name>([^<]*)</name>", xml)
    if not name:
        return None
    url = re.search(r"downloadurl.*?<!\[CDATA\[([^\]]+)\]\]", xml, re.S)
    size = re.search(r"<size>([^<]*)</size>", xml)
    md5 = re.search(r"<md5>([^<]*)</md5>", xml)
    obj = re.search(r"<object_to_name>([^<]*)</object_to_name>", xml)
    to_ver = None
    if obj:
        to_ver = obj.group(1)
    elif "_to_" in name.group(1):
        to_ver = name.group(1).split("_to_")[-1]
    return {
        "name": name.group(1),
        "to_version": to_ver,
        "size": int(size.group(1)) if size and size.group(1).isdigit() else 0,
        "md5": md5.group(1) if md5 else "",
        "url": url.group(1) if url else "",
    }


def human_size(n):
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def download_file(url, out_path, progress_cb=None, chunk=1024 * 512):
    req = urllib.request.Request(url, headers={"User-Agent": "LenovoOtaTool/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(out_path, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if progress_cb:
                    progress_cb(done, total)
    return out_path


def extract_payload_from_zip(zip_path, out_dir, log=None):
    """从 OTA zip 中取出 payload.bin（通常是 stored 未压缩）"""
    os.makedirs(out_dir, exist_ok=True)
    out_payload = os.path.join(out_dir, "payload.bin")
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if "payload.bin" not in names:
            raise RuntimeError("该 zip 内没有 payload.bin（可能不是 A/B OTA 包）")
        info = z.getinfo("payload.bin")
        if log:
            log(f"payload.bin 大小 {human_size(info.file_size)}（压缩方式 {'STORED' if info.compress_type == 0 else 'DEFLATED'}）")
        with z.open("payload.bin") as src, open(out_payload, "wb") as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
    return out_payload


def pdg_list(payload_path):
    pdg = find_pdg()
    if not pdg:
        raise RuntimeError("未找到 payload-dumper-go.exe")
    r = subprocess.run([pdg, "-list", payload_path], capture_output=True, timeout=120)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    parts = []
    for line in out.splitlines():
        m = re.match(r"^\s*([a-z0-9_]+)\s*\(([^)]*)\)", line)
        if m and m.group(1) not in ("Found",):
            parts.append(m.group(1))
    is_delta = "Delta payload" in out
    return parts, is_delta, out


def pdg_extract(payload_path, out_dir, partitions=None, old_dir=None, log=None):
    pdg = find_pdg()
    if not pdg:
        raise RuntimeError("未找到 payload-dumper-go.exe")
    cmd = [pdg]
    if old_dir:
        cmd += ["-old", old_dir]
    if partitions:
        cmd += ["-partitions", ",".join(partitions)]
    cmd += ["-o", out_dir, payload_path]
    if log:
        log("执行: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    r = subprocess.run(cmd, capture_output=True, timeout=7200)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, out


# ------------------------- GUI -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("联想 OTA 查询 & 分区提取工具  v1.0")
        self.geometry("1000x720")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.query_tab = ttk.Frame(nb)
        self.extract_tab = ttk.Frame(nb)
        self.auto_tab = ttk.Frame(nb)
        nb.add(self.query_tab, text="  ① 查询 OTA 包  ")
        nb.add(self.auto_tab, text="  ② 自动走链提取（推荐）  ")
        nb.add(self.extract_tab, text="  ③ 手动提取分区  ")
        self._build_query()
        self._build_auto()
        self._build_extract()

    # ----- 查询页 -----
    def _build_query(self):
        f = self.query_tab
        top = ttk.LabelFrame(f, text="查询参数")
        top.pack(fill="x", padx=10, pady=8)

        ttk.Label(top, text="机型：").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        self.dev_combo = ttk.Combobox(top, width=32, state="readonly",
                                      values=[d["name"] for d in DEVICES])
        self.dev_combo.current(2)
        self.dev_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.dev_combo.bind("<<ComboboxSelected>>", self._on_dev)

        ttk.Label(top, text="序列号(SN)：").grid(row=0, column=2, sticky="w", padx=6)
        self.sn_var = tk.StringVar(value=DEVICES[2]["sn"])
        ttk.Entry(top, textvariable=self.sn_var, width=22).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(top, text="当前版本(curfirmwarever)：").grid(row=1, column=0, sticky="w", padx=6, pady=5)
        self.ver_var = tk.StringVar(value=DEVICES[2]["ver_hint"])
        ttk.Entry(top, textvariable=self.ver_var, width=88).grid(row=1, column=1, columnspan=4,
                                                                 sticky="we", padx=6)
        ttk.Label(top, text="（获取方法：adb shell getprop ro.build.version.incremental）",
                  foreground="#666").grid(row=2, column=1, sticky="w", padx=6)

        btns = ttk.Frame(f)
        btns.pack(fill="x", padx=10, pady=4)
        ttk.Button(btns, text="查询下一版本", command=lambda: self.do_query(False)).pack(side="left", padx=4)
        ttk.Button(btns, text="自动走链（一直查到没有下一版）", command=lambda: self.do_query(True)).pack(side="left", padx=4)
        ttk.Button(btns, text="复制选中链接", command=self.copy_link).pack(side="left", padx=4)
        ttk.Button(btns, text="打开链接", command=self.open_link).pack(side="left", padx=4)
        ttk.Button(btns, text="下载选中包", command=self.download_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="清空", command=lambda: self.tree.delete(*self.tree.get_children())).pack(side="left", padx=4)

        cols = ("no", "to_ver", "size", "md5", "url")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=14)
        for c, t, w in (("no", "#", 40), ("to_ver", "目标版本", 330), ("size", "大小", 90),
                        ("md5", "MD5", 200), ("url", "下载链接", 380)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<Double-1>", self._on_double_click)

        self.qlog = scrolledtext.ScrolledText(f, height=8, font=("Consolas", 9))
        self.qlog.pack(fill="both", expand=False, padx=10, pady=(0, 8))

    def _on_dev(self, *_):
        d = DEVICES[self.dev_combo.current()]
        self.sn_var.set(d["sn"])
        self.ver_var.set(d["ver_hint"])

    def qlog_write(self, s):
        self.qlog.insert("end", s + "\n")
        self.qlog.see("end")

    def do_query(self, walk):
        model = DEVICES[self.dev_combo.current()]["model"]
        sn = self.sn_var.get().strip()
        ver = self.ver_var.get().strip()
        if not ver:
            messagebox.showwarning("提示", "请填写当前版本号")
            return
        self.tree.delete(*self.tree.get_children())
        threading.Thread(target=self._query_worker, args=(model, sn, ver, walk), daemon=True).start()

    def _query_worker(self, model, sn, ver, walk):
        self.qlog_write(f"[查询] model={model} sn={sn}\n        cur={ver}")
        idx = 0
        seen = set()
        while True:
            try:
                r = query_next(model, sn, ver)
            except Exception as e:
                self.qlog_write(f"[错误] {e}")
                break
            if not r:
                self.qlog_write("[结果] 服务器无下一版本（可能版本号不对，或该链路需白名单 SN）")
                break
            idx += 1
            self.qlog_write(f"[命中] {idx}. {r['to_version']}  {human_size(r['size'])}")
            self.tree.insert("", "end", values=(idx, r["to_version"], human_size(r["size"]),
                                                r["md5"], r["url"]))
            if not walk:
                break
            nxt = r["to_version"]
            if not nxt or nxt in seen:
                self.qlog_write("[走链] 结束")
                break
            seen.add(nxt)
            ver = nxt
            time.sleep(0.3)

    def _sel_url(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表里选中一行")
            return None, None
        vals = self.tree.item(sel[0], "values")
        # 列顺序: 0=#, 1=目标版本, 2=大小, 3=MD5, 4=下载链接
        return vals[4], vals[1]

    def _on_double_click(self, _evt=None):
        self.copy_link()

    def open_link(self):
        url, _ = self._sel_url()
        if url:
            import webbrowser
            webbrowser.open(url)
            self.qlog_write("[打开] " + url)

    def copy_link(self):
        url, _ = self._sel_url()
        if url:
            self.clipboard_clear()
            self.clipboard_append(url)
            self.qlog_write("[复制] " + url)

    def download_selected(self):
        url, ver = self._sel_url()
        if not url:
            return
        out = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=f"ota_{ver or 'pkg'}.zip",
                                           filetypes=[("OTA zip", "*.zip")])
        if not out:
            return
        self.qlog_write(f"[下载] {url}\n    -> {out}")
        threading.Thread(target=self._dl_worker, args=(url, out), daemon=True).start()

    def _dl_worker(self, url, out):
        last = [0]

        def cb(done, total):
            if total and done - last[0] > 20 * 1024 * 1024:
                last[0] = done
                self.qlog_write(f"    进度 {human_size(done)} / {human_size(total)}")

        try:
            download_file(url, out, cb)
            self.qlog_write("[下载完成] " + out)
        except Exception as e:
            self.qlog_write(f"[下载失败] {e}")

    # ----- 自动走链提取页 -----
    def _build_auto(self):
        f = self.auto_tab
        top = ttk.LabelFrame(f, text="参数（自动下载增量包 → 逐跳应用 → 输出目标版本分区）")
        top.pack(fill="x", padx=10, pady=8)

        ttk.Label(top, text="机型：").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        self.a_combo = ttk.Combobox(top, width=30, state="readonly", values=[d["name"] for d in DEVICES])
        self.a_combo.current(2)
        self.a_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.a_combo.bind("<<ComboboxSelected>>", self._on_adev)

        ttk.Label(top, text="序列号(SN)：").grid(row=0, column=2, sticky="w", padx=6)
        self.a_sn = tk.StringVar(value=DEVICES[2]["sn"])
        ttk.Entry(top, textvariable=self.a_sn, width=20).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(top, text="起始版本（链的源，= 设备当前版本）：").grid(row=1, column=0, sticky="w", padx=6, pady=5)
        self.a_start = tk.StringVar(value=DEVICES[2]["ver_hint"])
        ttk.Entry(top, textvariable=self.a_start, width=80).grid(row=1, column=1, columnspan=3, sticky="we", padx=6)

        ttk.Label(top, text="目标版本（想提取哪个版本，留空=一路走到最新）：").grid(row=2, column=0, sticky="w", padx=6, pady=5)
        self.a_target = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.a_target, width=80).grid(row=2, column=1, columnspan=3, sticky="we", padx=6)

        ttk.Label(top, text="基础源镜像目录：").grid(row=3, column=0, sticky="w", padx=6, pady=5)
        self.a_base = tk.StringVar(value="")
        ttk.Entry(top, textvariable=self.a_base, width=62).grid(row=3, column=1, columnspan=2, sticky="we", padx=6)
        ttk.Button(top, text="浏览…", command=lambda: self.a_base.set(
            filedialog.askdirectory() or self.a_base.get())).grid(row=3, column=3, sticky="w", padx=6)
        ttk.Label(top, text="↑ 起始版本这些分区的镜像（可选：点下面按钮直接从设备读取，需 root）",
                  foreground="#666").grid(row=4, column=1, sticky="w", padx=6)

        ttk.Label(top, text="缓存目录（下载的包存这里，可复用）：").grid(row=5, column=0, sticky="w", padx=6, pady=5)
        self.a_cache = tk.StringVar(value=os.path.join(BASE_DIR, "cache"))
        ttk.Entry(top, textvariable=self.a_cache, width=62).grid(row=5, column=1, columnspan=2, sticky="we", padx=6)
        ttk.Button(top, text="浏览…", command=lambda: self.a_cache.set(
            filedialog.askdirectory() or self.a_cache.get())).grid(row=5, column=3, sticky="w", padx=6)

        ttk.Label(top, text="输出目录：").grid(row=6, column=0, sticky="w", padx=6, pady=5)
        self.a_out = tk.StringVar(value=os.path.join(BASE_DIR, "auto_out"))
        ttk.Entry(top, textvariable=self.a_out, width=62).grid(row=6, column=1, columnspan=2, sticky="we", padx=6)
        ttk.Button(top, text="浏览…", command=lambda: self.a_out.set(
            filedialog.askdirectory() or self.a_out.get())).grid(row=6, column=3, sticky="w", padx=6)

        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=10, pady=4)
        lf = ttk.LabelFrame(mid, text="要提取的分区（可多选）")
        lf.pack(side="left", fill="both", expand=False)
        self.a_parts = tk.Listbox(lf, selectmode="extended", height=12, width=22, font=("Consolas", 10))
        for p in ["init_boot", "boot", "vendor_boot", "dtbo", "vbmeta", "vbmeta_system",
                  "abl", "xbl", "tz", "hyp", "uefi", "keymaster", "modem", "dsp",
                  "system", "vendor", "product", "odm", "system_ext", "recovery", "dataext"]:
            self.a_parts.insert("end", p)
        self.a_parts.pack(fill="both", expand=True, padx=6, pady=6)
        for i in (0, 1, 2, 3, 4):
            self.a_parts.select_set(i)
        bb = ttk.Frame(lf)
        bb.pack(fill="x", padx=6, pady=4)
        ttk.Button(bb, text="全选", command=lambda: self.a_parts.select_set(0, "end")).pack(side="left")
        ttk.Button(bb, text="只选 init_boot", command=self._sel_only_init).pack(side="left", padx=4)

        rf = ttk.LabelFrame(mid, text="操作 / 日志")
        rf.pack(side="left", fill="both", expand=True, padx=(8, 0))
        bar = ttk.Frame(rf)
        bar.pack(fill="x", padx=6, pady=6)
        ttk.Button(bar, text="▶ 自动走链并提取", command=self.auto_run).pack(side="left", padx=3)
        ttk.Button(bar, text="从设备读取基础镜像(需root)", command=self.adb_base_run).pack(side="left", padx=3)
        ttk.Button(bar, text="清空日志", command=lambda: self.alog.delete("1.0", "end")).pack(side="left", padx=3)
        self.alog = scrolledtext.ScrolledText(rf, font=("Consolas", 9))
        self.alog.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.alog_write("自动模式说明：\n"
                        "1) 填「起始版本」（链的源版本，一般填设备当前版本）和「基础源镜像目录」\n"
                        "   （该目录里要有起始版本的 <分区名>.img；没有可用下面的按钮从设备 dd）\n"
                        "2) 选好要提取的分区 → 点「自动走链并提取」\n"
                        "3) 工具会自动：查链路 → 下载每一跳增量包（缓存复用）→ 逐跳应用 → 输出目标版本分区\n"
                        "4) 目标版本留空则一路走到服务器没有下一版为止\n"
                        "5) 结果在「输出目录」里，每个分区一个 <分区名>.img，并自动做哈希校验")

    def _on_adev(self, *_):
        d = DEVICES[self.a_combo.current()]
        self.a_sn.set(d["sn"])
        self.a_start.set(d["ver_hint"])

    def _sel_only_init(self):
        self.a_parts.select_clear(0, "end")
        for i in range(self.a_parts.size()):
            if self.a_parts.get(i) == "init_boot":
                self.a_parts.select_set(i)

    def alog_write(self, s):
        self.alog.insert("end", s + "\n")
        self.alog.see("end")

    def auto_run(self):
        model = DEVICES[self.a_combo.current()]["model"]
        sn = self.a_sn.get().strip()
        start = self.a_start.get().strip()
        target = self.a_target.get().strip() or None
        base = self.a_base.get().strip()
        cache = self.a_cache.get().strip() or os.path.join(BASE_DIR, "cache")
        out = self.a_out.get().strip() or os.path.join(BASE_DIR, "auto_out")
        parts = [self.a_parts.get(i) for i in self.a_parts.curselection()]
        if not start:
            messagebox.showwarning("提示", "请填起始版本"); return
        if not parts:
            messagebox.showwarning("提示", "请选择要提取的分区"); return
        if base and not os.path.isdir(base):
            messagebox.showwarning("提示", "基础源镜像目录不存在"); return
        threading.Thread(target=self._auto_worker,
                         args=(model, sn, start, target, base, parts, cache, out), daemon=True).start()

    def _auto_worker(self, model, sn, start, target, base, parts, cache, out):
        os.makedirs(cache, exist_ok=True)
        os.makedirs(out, exist_ok=True)
        # 1) 走链
        self.alog_write(f"[1] 查询链路：{start}".split("：")[0] + "：")
        hops, ver, seen = [], start, set()
        while True:
            try:
                r = query_next(model, sn, ver)
            except Exception as e:
                self.alog_write(f"[错误] 查询失败: {e}"); return
            if not r:
                self.alog_write("    服务器无下一版本，链路结束")
                break
            hops.append(r)
            self.alog_write(f"    第{len(hops)}跳 → {r['to_version']}  {human_size(r['size'])}")
            if target and r["to_version"] == target:
                break
            nv = r["to_version"]
            if not nv or nv in seen:
                break
            seen.add(nv); ver = nv
        if not hops:
            self.alog_write("[结束] 没有可用的链路（检查起始版本号/SN）"); return
        if target and hops[-1]["to_version"] != target:
            self.alog_write(f"[提示] 未能走到目标版本 {target}，将输出 {hops[-1]['to_version']}")

        # 2) 逐跳下载并应用
        cur = base
        for i, h in enumerate(hops, 1):
            pkg = os.path.join(cache, os.path.basename(h["url"]))
            if os.path.isfile(pkg) and os.path.getsize(pkg) == h["size"]:
                self.alog_write(f"[{i+1}] 复用缓存 {os.path.basename(pkg)}")
            else:
                self.alog_write(f"[{i+1}] 下载 {h['url']}")
                last = [0]

                def cb(done, total, _i=i):
                    if total and done - last[0] > 30 * 1024 * 1024:
                        last[0] = done
                        self.alog_write(f"      {human_size(done)} / {human_size(total)}")

                try:
                    download_file(h["url"], pkg, cb)
                    self.alog_write(f"      完成 {human_size(os.path.getsize(pkg))}")
                except Exception as e:
                    self.alog_write(f"      [下载失败] {e}"); return
            try:
                work = os.path.join(cache, f"_payload{i}")
                payload = extract_payload_from_zip(pkg, work, self.alog_write)
                plist, is_delta, _ = pdg_list(payload)
                hop_out = os.path.join(cache, f"_hop{i}")
                rc, log = pdg_extract(payload, hop_out, parts, cur if is_delta else None, self.alog_write)
                ok = [p for p in parts if os.path.isfile(os.path.join(hop_out, p + ".img"))]
                self.alog_write(f"      应用完成（{'增量包' if is_delta else '全量包'}），产出: {', '.join(ok) if ok else '无'}")
                if not ok:
                    self.alog_write("      [失败] 本跳没有产出，停止。常见原因：源镜像缺失/版本不匹配/分区含不支持的操作类型")
                    return
                cur = hop_out
            except Exception as e:
                self.alog_write(f"      [异常] {e}"); return

        # 3) 输出
        final = os.path.join(cache, f"_hop{len(hops)}")
        for p in parts:
            src_f = os.path.join(final, p + ".img")
            if os.path.isfile(src_f):
                shutil.copy2(src_f, os.path.join(out, p + ".img"))
                self.alog_write(f"  ✓ {p}.img  {human_size(os.path.getsize(src_f))}")
        self.alog_write(f"\n[完成] 目标版本：{hops[-1]['to_version']}\n        输出目录：{out}")

    # ----- 从设备读取基础镜像 -----
    def adb_base_run(self):
        parts = [self.a_parts.get(i) for i in self.a_parts.curselection()]
        if not parts:
            messagebox.showwarning("提示", "请选择要读取的分区"); return
        out = self.a_base.get().strip()
        if not out:
            out = filedialog.askdirectory()
            if not out:
                return
            self.a_base.set(out)
        threading.Thread(target=self._adb_worker, args=(parts, out), daemon=True).start()

    def _adb_worker(self, parts, out):
        os.makedirs(out, exist_ok=True)

        def adb(args, timeout=120):
            r = subprocess.run(["adb"] + args, capture_output=True, timeout=timeout)
            return (r.stdout or b"").decode("utf-8", "replace")

        self.alog_write("[adb] 读取设备信息…")
        slot = adb(["shell", "getprop ro.boot.slot_suffix"]).strip() or "_a"
        self.alog_write(f"      当前槽位: {slot}")
        ok = 0
        for p in parts:
            dev = f"/dev/block/bootdevice/by-name/{p}{slot}"
            try:
                adb(["shell", f"su -c 'dd if={dev} of=/data/local/tmp/{p}.img 2>/dev/null'"])
                r = subprocess.run(["adb", "pull", f"/data/local/tmp/{p}.img", os.path.join(out, p + ".img")],
                                   capture_output=True, timeout=600)
                if r.returncode == 0:
                    fp = os.path.join(out, p + ".img")
                    if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                        self.alog_write(f"      ✓ {p}.img  {human_size(os.path.getsize(fp))}")
                        ok += 1
                        continue
                self.alog_write(f"      ✗ {p} 读取失败")
            except Exception as e:
                self.alog_write(f"      ✗ {p}: {e}")
        adb(["shell", "su -c 'rm -f /data/local/tmp/*.img'"])
        self.alog_write(f"[adb] 完成 {ok}/{len(parts)} 个分区 → {out}")

    # ----- 提取页（手动） -----
    def _build_extract(self):
        f = self.extract_tab
        top = ttk.LabelFrame(f, text="OTA 包与输出")
        top.pack(fill="x", padx=10, pady=8)

        self.zip_var = tk.StringVar()
        self.out_var = tk.StringVar(value=os.path.join(BASE_DIR, "extracted"))
        self.old_var = tk.StringVar()

        ttk.Label(top, text="OTA 包(zip)：").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(top, textvariable=self.zip_var, width=70).grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(top, text="浏览…", command=self.pick_zip).grid(row=0, column=2, padx=6)

        ttk.Label(top, text="输出目录：").grid(row=1, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(top, textvariable=self.out_var, width=70).grid(row=1, column=1, sticky="we", padx=6)
        ttk.Button(top, text="浏览…", command=lambda: self.out_var.set(
            filedialog.askdirectory() or self.out_var.get())).grid(row=1, column=2, padx=6)

        ttk.Label(top, text="源镜像目录：").grid(row=2, column=0, sticky="w", padx=6, pady=5)
        ttk.Entry(top, textvariable=self.old_var, width=70).grid(row=2, column=1, sticky="we", padx=6)
        ttk.Button(top, text="浏览…", command=lambda: self.old_var.set(
            filedialog.askdirectory() or self.old_var.get())).grid(row=2, column=2, padx=6)
        ttk.Label(top, text="（仅增量包需要：放上一版本同名分区镜像 <分区名>.img，如 init_boot.img）",
                  foreground="#a00").grid(row=3, column=1, sticky="w", padx=6)

        mid = ttk.Frame(f)
        mid.pack(fill="both", expand=True, padx=10)
        left = ttk.LabelFrame(mid, text="分区列表（可多选）")
        left.pack(side="left", fill="both", expand=True)
        self.plist = tk.Listbox(left, selectmode="extended", height=16, font=("Consolas", 10))
        self.plist.pack(fill="both", expand=True, padx=6, pady=6)
        ttk.Button(left, text="① 载入 OTA 包 / 列出分区", command=self.load_pkg).pack(fill="x", padx=6, pady=4)
        ttk.Button(left, text="全选", command=lambda: self.plist.select_set(0, "end")).pack(fill="x", padx=6, pady=2)
        ttk.Button(left, text="② 提取选中分区", command=self.do_extract).pack(fill="x", padx=6, pady=6)

        right = ttk.LabelFrame(mid, text="说明 / 日志")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.elog = scrolledtext.ScrolledText(right, font=("Consolas", 9))
        self.elog.pack(fill="both", expand=True, padx=6, pady=6)
        self.elog_write("使用说明：\n"
                        "1) 全量包：直接列出分区并提取，无需源镜像。\n"
                        "2) 增量包：需要「源镜像目录」——里面的 <分区名>.img 必须是上一版本（即包内 pre-build）\n"
                        "   的该分区镜像，否则提取会失败或哈希不符。\n"
                        "3) 提取结果会在输出目录生成 <分区名>.img。\n"
                        "4) 工具会自动校验输出哈希（payload-dumper-go 内置校验）。")

    def elog_write(self, s):
        self.elog.insert("end", s + "\n")
        self.elog.see("end")

    def pick_zip(self):
        p = filedialog.askopenfilename(filetypes=[("OTA zip", "*.zip"), ("All", "*.*")])
        if p:
            self.zip_var.set(p)

    def load_pkg(self):
        zp = self.zip_var.get().strip()
        if not os.path.isfile(zp):
            messagebox.showwarning("提示", "请先选择 OTA zip 文件")
            return
        threading.Thread(target=self._load_worker, args=(zp,), daemon=True).start()

    def _load_worker(self, zp):
        try:
            work = os.path.join(tempfile.gettempdir(), "lenovo_ota_tool")
            self.elog_write("[1/2] 从 zip 中提取 payload.bin …")
            payload = extract_payload_from_zip(zp, work, self.elog_write)
            self.elog_write("[2/2] 解析 payload 分区列表 …")
            parts, is_delta, raw = pdg_list(payload)
            self._payload_path = payload
            self.plist.delete(0, "end")
            for p in parts:
                self.plist.insert("end", p)
            self.elog_write(f"检测到 {len(parts)} 个分区，类型：{'增量包(delta)' if is_delta else '全量包(full)'}")
            if is_delta:
                self.elog_write("→ 这是增量包：提取前请在「源镜像目录」放入上一版本的分区镜像")
            self._is_delta = is_delta
        except Exception as e:
            self.elog_write(f"[失败] {e}")

    def do_extract(self):
        payload = getattr(self, "_payload_path", None)
        if not payload or not os.path.isfile(payload):
            messagebox.showwarning("提示", "请先点「① 载入 OTA 包 / 列出分区」")
            return
        sels = [self.plist.get(i) for i in self.plist.curselection()]
        if not sels:
            messagebox.showwarning("提示", "请选择至少一个分区")
            return
        out = self.out_var.get().strip() or os.path.join(BASE_DIR, "extracted")
        old = self.old_var.get().strip() or None
        if getattr(self, "_is_delta", False) and not old:
            if not messagebox.askyesno("注意",
                                       "这是增量包但没填「源镜像目录」。\n"
                                       "没有源镜像，含差异操作的分区会提取失败/哈希不符。\n\n"
                                       "仍要继续吗？"):
                return
        threading.Thread(target=self._extract_worker, args=(payload, out, sels, old), daemon=True).start()

    def _extract_worker(self, payload, out, sels, old):
        os.makedirs(out, exist_ok=True)
        self.elog_write(f"[提取] 分区: {', '.join(sels)}")
        rc, log = pdg_extract(payload, out, sels, old, self.elog_write)
        tail = "\n".join([l for l in log.splitlines() if l.strip()][-12:])
        self.elog_write(tail)
        self.elog_write(f"[完成] 返回码={rc}，输出目录：{out}")
        for s in sels:
            fp = os.path.join(out, s + ".img")
            if os.path.isfile(fp):
                self.elog_write(f"  ✓ {s}.img  {human_size(os.path.getsize(fp))}")
            else:
                self.elog_write(f"  ✗ {s}.img 未生成（可能操作类型不支持或源镜像不对）")


def cli():
    """命令行模式：
       LenovoOtaTool.exe query --model TB323FU_CN --sn SN_请填你的序列号 --version <ver> [--walk]
       LenovoOtaTool.exe list  --zip xxx.zip
       LenovoOtaTool.exe extract --zip xxx.zip --out DIR [--parts init_boot,boot] [--old SRCDIR]
    """
    import argparse
    ap = argparse.ArgumentParser(prog="LenovoOtaTool")
    sub = ap.add_subparsers(dest="cmd")

    q = sub.add_parser("query")
    q.add_argument("--model", required=True)
    q.add_argument("--sn", required=True)
    q.add_argument("--version", required=True)
    q.add_argument("--walk", action="store_true")

    l = sub.add_parser("list")
    l.add_argument("--zip", required=True)

    e = sub.add_parser("extract")
    e.add_argument("--zip", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--parts", default="")
    e.add_argument("--old", default=None)

    au = sub.add_parser("auto")
    au.add_argument("--model", required=True)
    au.add_argument("--sn", required=True)
    au.add_argument("--start", required=True)
    au.add_argument("--target", default=None)
    au.add_argument("--base", default=None)
    au.add_argument("--parts", required=True)
    au.add_argument("--cache", default=os.path.join(BASE_DIR, "cache"))
    au.add_argument("--out", required=True)

    a = ap.parse_args()
    if a.cmd == "query":
        ver = a.version
        seen = set()
        while True:
            r = query_next(a.model, a.sn, ver)
            if not r:
                print("(无下一版本)")
                break
            print(f"{r['to_version']}\t{human_size(r['size'])}\t{r['md5']}\t{r['url']}")
            if not a.walk or not r["to_version"] or r["to_version"] in seen:
                break
            seen.add(r["to_version"])
            ver = r["to_version"]
        return
    if a.cmd == "auto":
        os.makedirs(a.cache, exist_ok=True)
        os.makedirs(a.out, exist_ok=True)
        hops, ver, seen = [], a.start, set()
        while True:
            r = query_next(a.model, a.sn, ver)
            if not r:
                print("(链路结束)")
                break
            hops.append(r)
            print(f"[{len(hops)}] → {r['to_version']}  {human_size(r['size'])}  {r['url']}")
            if a.target and r["to_version"] == a.target:
                break
            nv = r["to_version"]
            if not nv or nv in seen:
                break
            seen.add(nv); ver = nv
        if not hops:
            print("没有可用链路"); return
        parts = [p for p in a.parts.split(",") if p]
        cur = a.base
        for i, h in enumerate(hops, 1):
            pkg = os.path.join(a.cache, os.path.basename(h["url"]))
            if not (os.path.isfile(pkg) and os.path.getsize(pkg) == h["size"]):
                print(f"[下载] {h['url']}")
                download_file(h["url"], pkg, lambda d, t: None)
            payload = extract_payload_from_zip(pkg, os.path.join(a.cache, f"_payload{i}"), print)
            plist, is_delta, _ = pdg_list(payload)
            hop_out = os.path.join(a.cache, f"_hop{i}")
            rc, log = pdg_extract(payload, hop_out, parts, cur if is_delta else None, print)
            ok = [p for p in parts if os.path.isfile(os.path.join(hop_out, p + ".img"))]
            print(f"[应用] {'增量' if is_delta else '全量'} → 产出 {ok}")
            if not ok:
                print("提取失败，停止"); return
            cur = hop_out
        final = os.path.join(a.cache, f"_hop{len(hops)}")
        for p in parts:
            f = os.path.join(final, p + ".img")
            if os.path.isfile(f):
                shutil.copy2(f, os.path.join(a.out, p + ".img"))
                print(f"OK {p}.img -> {a.out}")
        print("完成，目标版本:", hops[-1]["to_version"])
        return
    if a.cmd in ("list", "extract"):
        work = os.path.join(tempfile.gettempdir(), "lenovo_ota_tool")
        payload = extract_payload_from_zip(a.zip, work, print)
        parts, is_delta, raw = pdg_list(payload)
        if a.cmd == "list":
            print(f"类型: {'增量包' if is_delta else '全量包'}")
            for p in parts:
                print(p)
            return
        sels = [s for s in a.parts.split(",") if s] or None
        rc, log = pdg_extract(payload, a.out, sels, a.old, print)
        print(log[-2000:])
        print("返回码:", rc)
        return
    ap.print_help()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        App().mainloop()
