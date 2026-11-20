# A7Z 更新包与镜像构建

在电脑的 **Linux / WSL** 中构建，建议使用 Python 3.13。以下路径按当前仓库填写，版本号每次发布时更换。

## 1. 构建 Studio 网页更新包

```bash
cd /mnt/d/ws/microduck/microduck-replica/radxa-cubie-a7z/studio/console-integration
python3.13 package_console.py --release 20261120 --artifacts artifacts/20261120
```

默认打包本目录已保存的 `web/`。如果改的是 `workspace/studio/web/`，先测试，再加 `--export` 导出并打包；该选项会重建仓库中的前端差异文件，完成后检查 Git diff。

输出目录 `artifacts/20261120/` 中有四个发布文件：

- `console-web-20261120.tar.gz`
- `console-web-20261120.tar.gz.sha256`
- `install_console.py`
- `install_console.py.sha256`

**此包只更新网页，不包含 Studio 后端、robotd 或串口配置。** 后端更新需另行制作对应更新包。

### 安装到 A7Z

用 SCP / SFTP 将四个文件传到板端 `/tmp/`，然后在 Termius 执行：

```bash
cd /tmp
sha256sum -c console-web-20261120.tar.gz.sha256
sha256sum -c install_console.py.sha256
mkdir console-web-20261120
tar -xzf console-web-20261120.tar.gz -C console-web-20261120
/opt/microduck-studio/python/bin/python3.13 install_console.py \
  /tmp/console-web-20261120/bundle --base /opt/microduck-studio/app
```

校验失败就停止，解包请使用新目录。最后一条仅预览；确认版本匹配、在 Studio 中卸力并交还控制后，再安装：

```bash
sudo /opt/microduck-studio/python/bin/python3.13 install_console.py \
  /tmp/console-web-20261120/bundle --base /opt/microduck-studio/app --apply
```

安装器会备份并输出回滚命令。若因舵机不齐或设备状态不满足而拒绝安装，不要绕过检查。

## 2. 构建默认使用 ACM0 的完整镜像

先准备 **Python 3.13、xz、debugfs、e2fsck**，以及 [镜像构建说明](image/README.md) 要求的基础系统镜像、固定 Studio 归档、robotd 产物、外部源码和 R17 运行时包。

```bash
cd /mnt/d/ws/microduck/microduck-replica/radxa-cubie-a7z/image
python3.13 create_image.py \
  --base ../os/radxa-a733_bullseye_kde_r6.output_512.img.xz \
  --output artifacts/cubie-a7z-duck-20261120-usb.img.xz \
  --release a7z-duck-20261120-usb \
  --servo-port /dev/ttyACM0
```

- **URT-2 USB：** `/dev/ttyACM0`，已是默认值，同步设置 robotd、Studio 和总线助手。
- **HAT / 板载 UART：** 将参数改成 `--servo-port /dev/ttyS2`。
- 新镜像不包含旧设备的舵机会话文件；仍需完成本机标定。

产物为指定的 `.img.xz` 镜像。构建不会修改 A7Z；**烧录会替换系统卡内容**，先备份配置、标定和网络设置。

## 3. 常见区别

- `git commit / push`：保存和推送代码，不会更新设备。
- 网页更新包：仅替换前端，保留设备串口配置和标定。
- 完整镜像：按仓库中的默认配置生成系统，不会自动保留板端手工改动。
- 已有设备改用 ACM0：按 [URT-2 配置说明](studio/USB-URT2.md) 操作，无需为此安装网页包。

截至 2026-11-20：前端包已成功构建；ACM0 镜像配置已通过离线测试，但本机缺少完整构建输入，尚未生成新镜像。
