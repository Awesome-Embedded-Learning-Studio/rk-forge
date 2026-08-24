# user — per-developer drop-in config

个人凭据与偏好,**永不提交**:整目录 gitignore,只有 `*.example` 模板和本 README 进 git。
`forge.yaml` 是提交态的项目通用配置(教学默认值,如账户 `rk-forge`/`rk-forge`);
凡是「因人而异」的东西都放这里。

用法:复制对应 `.example`、去掉后缀、填值。**每个文件一个域,存在即启用,不存在即跳过**。

| 文件 | 域 | 生效位置 | 改动成本 |
|---|---|---|---|
| `wifi.yaml` | WiFi 开机自动关联(SSID/PSK/改名) | stage-rootfs 烤入镜像 | 秒级重跑 `forge all` |
| `ssh.yaml` | 开发公钥 → `/root/.ssh/authorized_keys` | stage-rootfs 烤入镜像 | 秒级 |
| `network.yaml` | DNS(`/etc/resolv.conf`) | stage-rootfs 烤入镜像 | 秒级 |
| `account.yaml` | 覆盖 `forge.yaml` 的 `ubuntu.account` | ubuntu-rootfs chroot 构建 | 30 分钟级(sudo 岛全量重建) |

语义与纪律:

- **合并**:文件按名排序依次 deep-merge,后者覆盖前者;要按板/按环境再拆文件,直接加就是。
- **环境变量覆盖**:`FORGE_WIFI_SSID` / `FORGE_WIFI_PASS` / `FORGE_DNS` 优先级最高,脚本一次性覆盖用。
- **权限**:这里放的是明文凭据,目录 `chmod 700`、文件 `chmod 600`;加载器对过松权限会告警。
- 经验背景见 `document/notes/58`(WiFi 板上连接五坑、root 免密、DNS)。
