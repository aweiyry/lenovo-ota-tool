# 第三方组件声明

本项目的发布包（EXE）内嵌了以下第三方组件，其版权归原作者所有。

## payload-dumper-go

- 项目：https://github.com/ssut/payload-dumper-go
- 作者：ssut 及贡献者
- 许可：Apache License 2.0
- 用途：解析 Android OTA `payload.bin`（含增量 payload）、按分区提取镜像并校验哈希
- 说明：本工具将 `payload-dumper-go.exe` 作为外部可执行文件调用（源码模式下需置于
  `tools/` 目录；打包模式下随 EXE 一同分发）

```
Copyright 2020 ssut

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## avbroot（仅分析脚本参考）

- 项目：https://github.com/chenxiaolong/avbroot
- 许可：GPL-3.0
- 用途：动态分区（super/LP 镜像）的解析与重打包。本项目**不包含**其代码，
  仅在文档中作为工具链参考提及。

## 其他

- 本项目与联想（Lenovo）公司无任何关联，未使用或分发任何联想私有代码或密钥。
- 所有 OTA 包均由联想官方 CDN 提供，本项目仅做查询与解析。
