# stock_img —— 五代 TB323FU 官方 init_boot 镜像（未 root、未打补丁）

每个版本一个子目录，目录内文件名固定为 `init_boot.img`，
可以直接把对应版本的子目录路径填到工具的「基础源镜像目录」。

| 版本 | 目录 | SHA256 |
|---|---|---|
| 2.0.12.199 (ST_260812) | `stock_img\199\init_boot.img` | `576EC1AF296613F750289F53BB14E097863749275858CBB51276A885221C2519` |
| 2.0.12.211 (ST_260821) | `stock_img\211\init_boot.img` | `2A7C0DB0E498A4E413FBB8872916700A4AB531247D56B2284506D3ACE0C7ADD3` |
| 2.0.12.222 (ST_260831) | `stock_img\222\init_boot.img` | `B8266EC42026220819B3B2B940DF775003965E7D837CC75B6DD753D5AFD97598` |
| 2.0.12.236 (ST_260911) | `stock_img\236\init_boot.img` | `E8F94F7DA2436B92759172D6C30CCDE03BC72F1E8456650D6E44553FE8E2F94D` |

以上哈希均已与联想增量包 manifest 中的 `old_partition_info.hash` / `new_partition_info.hash` 逐字节核对一致。

来源链：

```
199(官方初始镜像)
 └─ ota_211_delta.zip       (199→211 增量包) → 211
     └─ ota_211_to_222.zip  (211→222 增量包) → 222
         └─ 202691510264732-5014.zip (222→236 增量包) → 236
```

说明：

- 设备 root / 换过内核后，`dd` 出来的 `init_boot` 已非官方镜像，不能作为增量包的源；
  请用这里的官方镜像。
- 打 KernelSU 补丁请基于这里的官方镜像生成，补丁后的镜像哈希会变，属正常。
- 本目录被 `.gitignore` 的 `*.img` 规则排除，不会进入 Git 仓库。
