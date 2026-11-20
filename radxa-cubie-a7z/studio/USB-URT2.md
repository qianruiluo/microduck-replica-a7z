# A7Z 使用 USB URT-2 的配置与会话迁移

## 适用范围与验证记录

2026-11-20，用户使用 Cubie A7Z、URT-2（CH343）和一颗 ID 11 的 HD-1910。USB 设备已确认为 `/dev/ttyACM0`。

已验证的问题链路：

1. `robotd` 读取 `/etc/robot/feetech-ft5/robotd.toml`。用户将串口改为 `/dev/ttyACM0`。
2. Studio 独立使用 `--servo-port` 参数。即使启动参数已指定 `/dev/ttyACM0`，重启日志仍显示 `打开舵机总线：/dev/ttyS2 @ 1000000`、`0/15 颗有应答`。
3. Studio 正在恢复上次会话；`servo_restore()` 从 `servo-session.json` 读取 `port`，再传给 `servo.open()`，覆盖启动时的串口。
4. 停止 Studio、备份会话文件，仅把 `port` 改成 `/dev/ttyACM0`，再启动 Studio 后，用户确认能够读到舵机。

这是单颗舵机读取的现场反馈，不代表 15 颗整机通信、IMU、标定、站立或行走通过。成功后的完整日志尚未回收。日志中缺失列表不包含 11，仅证明对应那次读取收到 ID 11 的回复，不能当作持续在线证据。

本次未修改板端 Studio Python 源码。这份文档保存可复现的配置步骤；没有把正在运行的会话标记、个人标定或整机运动授权放入 Git，也没有重建已经发布的镜像。随后本地镜像构建已新增 `--servo-port` 参数，默认 USB `/dev/ttyACM0`，HAT 可显式选择 `/dev/ttyS2`；见 [构建与更新指南](../BUILD-AND-UPDATE.md)。历史镜像和现有设备不自动改变。

## 三处串口需要一致

| 位置 | USB URT-2 接法的值 | 说明 |
| --- | --- | --- |
| robotd 实际加载的配置文件中 `[bus] port` | `/dev/ttyACM0` | 如果有效启动命令还有 `--port`，也要核对，避免命令行覆盖文件 |
| Studio 有效启动命令 `--servo-port` | `/dev/ttyACM0` | 不会自动跟随 robotd 的配置 |
| 既有 `servo-session.json` 的 `port` | `/dev/ttyACM0` | 同一次开机恢复会话时可能覆盖 Studio 启动参数；不存在则无需创建 |

`/dev/ttyS2 -> /dev/ttyAS0` 是 A7Z 板载串口的别名，与 USB 无关。不要把这个别名改指向 USB 来绕过配置。`/dev/ttyACM0` 是该用户当时的设备名，其他设备或重新枚举后应以实际结果为准。

## 1. 确认设备与当前配置

以下命令在 A7Z 上执行：

```sh
udevadm info -q property -n /dev/ttyACM0
sudo systemctl cat robotd --no-pager
sudo systemctl cat microduck-studio --no-pager
sudo fuser -v /dev/ttyACM0 /dev/ttyAS0
```

检查 USB 设备确实为 URT-2，以及有效的 `ExecStart`、`--params`、`--port`、`--servo-port` 和 `--state-dir`。多个 systemd 覆盖文件可能重置 `ExecStart`；不能仅凭某一份文件判断生效配置。

## 2. 配置 robotd

本次日志确认实际读取的是 `/etc/robot/feetech-ft5/robotd.toml`。先备份，在已有 `[bus]`（也可能写作 `["bus"]`）段中只修改 `port`：

```toml
port = "/dev/ttyACM0"
```

不要重复创建 `[bus]`，也不要把配置片段覆盖成完整文件。舵机通信保持 1000000、8N1、无流控；这些是通信参数，不要求在 TOML 中添加程序不支持的字段。

配置在下次 robotd 启动时读取。Studio 正在接管舵机时，不要手动启动 robotd 与它争用总线；使用页面的交还流程。整机程序仍可能因其余舵机或 IMU 缺失而无法完成初始化。

## 3. 配置 Studio

在上一步查到的 Studio 有效 `ExecStart` 中，保留原解释器、入口及所有参数，将已有 `--servo-port` 的值改为 USB 路径，或者在没有这个参数时追加：

```text
--servo-port /dev/ttyACM0
```

本仓库 A7Z 安装器生成的服务文件为 `/etc/systemd/system/microduck-studio.service`，应用目录为 `/opt/microduck-studio/app`。以设备实际输出为准；不要用本仓库其他历史开发服务的整条 `ExecStart` 覆盖现有命令。

修改服务文件后执行 `sudo systemctl daemon-reload`。若存在旧会话，应先按下一节迁移，再启动 Studio，避免它再次使用旧串口。

## 4. 迁移保存的旧会话

这一步只适用于已明确把同一组舵机从板载 UART 切换到 URT-2 的设备，不要在不同机器人或不同总线之间盲目迁移会话。

先支撑机构并确认当前无运动。停止 Studio 本身不会保证卸力，也不要通过删除会话或助手保护标记来强行启动 robotd。Studio 停止后再修改文件，避免运行中的进程写回旧值。

本次 `--state-dir` 为 `/var/lib/microduck-studio`，文件名由代码确认是 `servo-session.json`。以下为本次使用的修正方式；如果设备的状态目录不同，先替换为实际路径。

```sh
sudo systemctl stop microduck-studio
```

确认服务已停止，再执行：

```sh
sudo /opt/microduck-studio/python/bin/python3.13 - <<'PY'
import json
import shutil
import time
from pathlib import Path

p = Path('/var/lib/microduck-studio/servo-session.json')
if not p.exists():
    raise SystemExit('没有旧会话文件，无需迁移；确认启动参数即可。')
d = json.loads(p.read_text(encoding='utf-8'))
assert isinstance(d, dict) and d.get('sim') is False, '会话格式异常，未修改'
assert d.get('port') in ('/dev/ttyS2', '/dev/ttyAS0', '/dev/ttyACM0'), '原串口不在本次迁移范围，未修改'
backup = p.with_name(p.name + f'.bak-{time.time_ns()}')
shutil.copy2(p, backup)
old = d['port']
d['port'] = '/dev/ttyACM0'
p.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
print(f"串口：{old} -> {d['port']}")
print(f'备份：{backup}')
PY
```

只改 `port`，保留 `v`、`sim`、`at`、`by`、`boot_id` 等字段以及助手的总线接管保护。不要复制其他设备的会话文件；新装机不预置会话文件。

修正成功后：

```sh
sudo systemctl start microduck-studio
sudo journalctl -b -u microduck-studio --since '2 minutes ago' --no-pager -n 60
sudo fuser -v /dev/ttyACM0
```

启动可能需数秒；日志暂未出现时稍后再查看。应确认实际日志是 `打开舵机总线：/dev/ttyACM0 @ 1000000`，再看应答数量及 ID，而不是只看命令行已带参数。只接 ID 11 时预期是该 ID 可读，不要求 15/15。

## 回退与后续更新

- 配置回退时先确认设备已经恢复原物理接法，停止占用总线的程序，再恢复对应配置和会话备份；不要在 Studio 运行时替换会话文件。
- 原有会话恢复逻辑用于保留总线所有权，本次没有改成无条件优先使用启动参数。若以后开发正式切换入口，应同时处理互斥、旧会话和启动配置，并单独验证。
- 当前部分通用主程序升级脚本可能把 `--port /dev/ttyS2` 写回服务（例如 `software/studio/deploy/native_update.py` 中的 ARGS）。新镜像构建会移除此脚本的固定串口参数，让它读取设备 CONFIG；现有设备中的脚本未因此改变。USB 接法的完整升级流程仍未实机验证，升级前后需核对有效启动参数。
- 这些板端变更不会通过 `git pull` 自动回到电脑。仓库保存配置方法与验证范围，设备状态留在板上。新镜像的 USB 默认配置已纳入构建代码；完整打包依赖仍需准备齐全，构建后还需实机验收。
