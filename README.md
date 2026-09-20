# Lenovo OTA Tool

联想平板 OTA 增量包查询 & 分区提取工具（GUI + CLI）

支持机型：**三代 TB321FU** / **四代 TB322FC** / **五代 TB323FU**（联想拯救者 Y700 系列）

---

## 功能

### ① 查询 OTA 包
- 按 `机型 + 序列号(SN) + 当前版本` 查询联想 OTA 服务器，返回**下一版本增量包**的下载直链
- **自动走链**：一次查询，把整条版本链路上每一跳（版本号 / 大小 / MD5 / 下载链接）全部列出
- 支持直接下载选中包、复制链接、浏览器打开

### ② 自动走链提取（推荐）
选好 `起始版本 → 目标版本` 后，工具自动完成：

```
查询链路 → 逐跳下载增量包（本地缓存复用）→ 逐跳应用补丁 → 输出目标版本的分区镜像（含哈希校验）
```

**无需手动下载，也无需手动逐跳喂源镜像** —— 每一跳的产出自动成为下一跳的源。

### ③ 手动提取分区
已自行下载好 OTA 包时：选 zip → 列出分区 → 勾选 →（增量包填源镜像目录）→ 提取指定分区（如 `init_boot`、`boot`）。

---

## 快速开始

### 方式一：直接使用打包好的 EXE

```bash
# 查询下一版本
LenovoOtaTool.exe query --model TB323FU_CN --sn SN_请填你的序列号 \
    --version TB323FU_CN_OPEN_USER_Q00020.0_A16_ZUXOS_2.0.12.199_ST_260812

# 自动走完整条链
LenovoOtaTool.exe query --model TB323FU_CN --sn SN_请填你的序列号 --version <版本串> --walk
```

双击 EXE 打开图形界面（三个标签页：查询 / 自动走链提取 / 手动提取）。

### 方式二：从源码构建

```bash
pip install pyinstaller
# 把 payload-dumper-go.exe 放到 tools/ 目录（见 tools/README.md）
build.bat
# 产物：dist/LenovoOtaTool.exe
```

运行环境：Windows + Python 3.10+（源码模式无需第三方依赖，仅标准库；打包需要 pyinstaller）

---

## 命令行参考

```bash
# 查询下一版本（--walk 自动走链）
LenovoOtaTool.exe query --model <机型> --sn <SN> --version <当前版本串> [--walk]

# 列出 OTA 包内的分区
LenovoOtaTool.exe list --zip <ota.zip>

# 手动提取分区
LenovoOtaTool.exe extract --zip <ota.zip> --out <输出目录> \
    [--parts init_boot,boot] [--old <源镜像目录>]

# 自动走链提取
LenovoOtaTool.exe auto --model <机型> --sn <SN> \
    --start <起始版本串> [--target <目标版本串>] \
    [--base <起始版本镜像目录>] --parts init_boot,boot \
    [--cache <缓存目录>] --out <输出目录>
```

机型代号（`devicemodel`）：

| 机型 | devicemodel | 默认示例 SN |
|---|---|---|
| 三代 TB321FU (Y700 2025) | `TB321FU_CN` | SN_请填你的序列号 |
| 四代 TB322FC (Y700 2024) | `TB322FC_CN` | SN_请填你的序列号 |
| 五代 TB323FU (Y700 Gen5) | `TB323FU_CN` | SN_请填你的序列号 |

---

## 实测样例（真实命中，哈希已与官方 manifest 比对）

| 机型 | 链路 |
|---|---|
| 五代 TB323FU | `199 → 211(174.9MB) → 222(147.1MB) → 236(263.4MB)` |
| 四代 TB322FC | `1.1.11.120 → 1.5.10.229(9.8GB) → 1.5.10.259(181.8MB)` |

提取结果验证（与包内官方 manifest 期望哈希逐字节一致）：

```
222 init_boot = B8266EC42026220819B3B2B940DF775003965E7D837CC75B6DD753D5AFD97598
236 init_boot = E8F94F7DA2436B92759172D6C30CCDE03BC72F1E8456650D6E44553FE8E2F94D
```

---

## 工作原理

### OTA 查询接口

```
POST https://ota.lenovo.com/ota-server/firmware/query/for-text-desc
Content-Type: application/x-www-form-urlencoded

action=querynewfirmware
devicemodel=<机型>          # 如 TB323FU_CN
deviceid=<序列号 SN>
curfirmwarever=<当前版本串>  # 必须精确，含日期后缀
locale=zh
nationcode=CN
pid=
ChecksumType=sha256
```

返回 XML，含下一版本名称、增量包 CDN 直链（`otanew-cdn.lenovo.com` / `ota-cdn.lenovo.com`）、大小、MD5。
服务器**逐级下发**：查询 N 返回 N→N+1 的增量包，因此沿链查询即可还原完整升级路径。

### 为什么增量包需要"源镜像"

增量包 payload 内是「上一版本 → 目标版本」的**补丁**，而非完整镜像：

| 操作类型 | 含义 | 数据是否在包里 |
|---|---|---|
| `REPLACE` / `REPLACE_XZ` / `REPLACE_BZ` | 目标分区变化部分的新数据 | ✅ 在 |
| `SOURCE_COPY` | 从旧分区直接复制 | ❌ 不在 |
| `PUFFDIFF` / `BROTLI_BSDIFF` | 基于旧分区内容的差分补丁 | ❌ 不在（需旧数据）|
| `ZERO` | 写零 | — |

因此提取目标版本分区时**必须提供上一版本的同名分区镜像作为源**。
本工具的「自动走链提取」就是自动完成这条链：从起始版本的基础镜像出发，逐跳应用，最终得到目标版本镜像。

另外两种不需要源的情况：
- **全量包**（full payload）：自带完整数据，直接提取；
- **该分区在两版之间未变化**：增量包里不包含该分区，目标版本 = 源版本。

---

## 版本串格式参考

```
五代 TB323FU：TB323FU_CN_OPEN_USER_Q00020.0_A16_ZUXOS_2.0.12.<num>_ST_<YYMMDD>
四代 TB322FC：TB322FC_CN_OPEN_USER_Q00041.1_V_ZUXOS_<x>.<x>.<num>_ST_<YYMMDD>
三代 TB321FU：TB321FU_CN_OPEN_USER_Q00002.0_W_DF_17.5.10.<num>_ST_<YYMMDD>
```

获取设备当前版本：`adb shell getprop ro.build.version.incremental`
从已有包获取精确版本串：`payload_properties.txt` 的 `pre-build` / `post-build` 字段。

---

## 已知限制

1. **内测(beta/DF)链路需要该机型内测白名单 SN**；普通 SN 查询返回空属正常现象。
2. 版本号必须精确（含日期后缀），格式错误会查询不到。
3. 含 `PUFFDIFF` 等特殊操作的分区，内置引擎（payload-dumper-go）会拒绝提取；仅影响 `system` / `vendor` / `system_ext` 等少数大分区。
4. 跨大版本包体积较大（如四代 9.8GB），建议用缓存目录复用避免重复下载。

---

## 仓库结构

```
.
├── lenovo_ota_tool.py            # 主程序（GUI + CLI，仅标准库）
├── build.bat                     # PyInstaller 打包脚本
├── requirements.txt
├── docs/
│   ├── 使用说明.md
│   └── 原理说明.md               # OTA 接口 / payload 结构 / 增量语义
├── scripts/                      # 逆向分析辅助脚本
│   ├── analyze_ops.py            # 统计各分区的操作类型分布与源引用区块
│   ├── dump_partition_hashes.py  # 解析 payload manifest，导出分区 old/new 哈希
│   ├── dump_op_fields.py         # 逐字段打印 install operation（排错用）
│   ├── assemble_super_from_qfil.py # 按 rawprogram 偏移拼装 super.img
│   └── parse_gpt.py              # 解析 GPT，取得 super 等分区真实大小
└── tools/
    └── README.md                 # payload-dumper-go 获取说明（第三方组件）
```

---

## 免责声明

本工具仅用于**查询公开的 OTA 更新信息**与**从官方 OTA 包中提取分区镜像**，适用于：

- 备份/恢复自己设备的官方固件
- 刷机、救砖、降级等自用场景

使用者应确保操作对象为**自有设备**，并遵守当地法律法规及厂商条款。
作者不对任何因使用本工具造成的设备损坏、数据丢失或法律风险负责。

---

## 依赖与致谢

- [payload-dumper-go](https://github.com/ssut/payload-dumper-go) — OTA payload 解析与分区提取（Apache-2.0，见 `THIRD_PARTY_NOTICES.md`）
- [avbroot](https://github.com/chenxiaolong/avbroot) — super 分区（LP）解析/重打包（分析脚本相关）

## License

MIT — 见 `LICENSE`
