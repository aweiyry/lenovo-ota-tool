# 第三方工具：payload-dumper-go

本工具依赖 `payload-dumper-go.exe` 完成「OTA 包分区列表读取」与「分区提取（含增量应用）」。

## 获取方式

从官方 Release 下载 Windows 版：

```
https://github.com/ssut/payload-dumper-go/releases
```

推荐选择：`payload-dumper-go_<版本>_windows_amd64_avx2.tar.gz`（解压后得到 exe）

## 放置位置

```
tools/payload-dumper-go.exe
```

放置后运行 `build.bat`，会自动打入 EXE（打包模式下随 EXE 分发，无需外部文件）。

## 若未放置

- 源码模式运行 `lenovo_ota_tool.py`：程序会依次在以下位置查找
  `payload-dumper-go.exe`：
  1. EXE/脚本同目录
  2. `tools/` 目录
  3. `D:\DSH\ota\_ota\pdg2\`（开发机路径，可自行修改源码 `PDG_CANDIDATES`）
- 打包模式：EXE 会在运行时于自身同目录与本工具目录查找。

## 注意

- payload-dumper-go 对增量包（delta payload）需要 `-old <源镜像目录>`，这是
  Android OTA 增量语义决定的（详见 README「为什么增量包需要源镜像」）。
- 该工具**不支持** `PUFFDIFF` 操作类型，因此含该操作的分区（通常是
  `system` / `vendor` / `system_ext`）无法直接提取。
