---
name: bt-spa3609-autoconnect
description: "Use ONLY for this machine (linuxmint, user cerfly) when user mentions Philips SPA3609 / 蓝牙音箱不自动连接 / speaker won't auto-connect / 要插拔USB才能连 / replug USB to connect / bluetoothctl connect / bt-spa3609.service / Host is down / Intel AX201 suspend / XX:XX:XX:XX:XX:XX. Diagnose and fix Bluetooth audio speaker auto-connect issues: the PC side is usually already correct, root causes are the speaker's standby/last-device memory or the Intel AX201 suspend bug, and the installed watchdog service makes the PC actively reconnect. NOT for WH-1000XM3 / vivo TWS Air Pro / 其他蓝牙设备."
---

# Philips SPA3609 蓝牙音箱自动连接 (本机专用)

> 仓库内此文件夹为 `fix-issue`(从仓库加载时 ID 按目录名取),源头技能在同一台机器的
> `~/.config/opencode/skills/bt-spa3609-autoconnect/`。完整排查记录见同目录
> [`issue-report.md`](issue-report.md)。

## 背景与根因（先说结论）

- PC 侧配置**几乎永远是正确的**：设备已 Pair+Trust、适配器 Powered、A2DP profile 正常。音箱不自动连接，问题在**音箱侧**，不是电脑。
- 用户口中"要插拔 USB 才能连上" = **给音箱断电重启**（SPA3609 是 USB 供电的音箱）。重插后音箱从休眠中醒来、重新拨打"上次设备"（本机）→ 自动连上。
- 三个真实根因，按概率排序：
  1. **音箱处于待机/断电**，蓝牙射频没在听 → 电脑拨打返回 `Host is down (112)`。
  2. **音箱的"上次设备"记忆被抢**：手机/TV 最后用过它时，开机后它只拨打那个设备，不找 PC。
  3. **Intel AX201 休眠挂死**（本机日志 `hci0: Timed out waiting for suspend events` / `Suspend notifier action (3) failed: -110`）：笔记本睡眠唤醒后射频静默，之后一概连不上。

## 已安装的修复（不要再装一套）

```bash
systemctl --user status bt-spa3609   # active = 看门狗在跑
systemctl --user restart bt-spa3609  # 重启看门狗
systemctl --user stop bt-spa3609     # 临时停（比如你在练别的蓝牙设备）
```

- 看门狗服务 = `~/.config/systemd/user/bt-spa3609.service`（Restart=always，登录自启），脚本 = `~/.local/bin/bt-spa3609-reconnect.sh`。
- 逻辑 = 每 15s 检查 `bluetoothctl info XX:XX:XX:XX:XX:XX`，未连接就 `bluetoothctl connect`；已连接则每 30s 复查。**让 PC 主动拨打音箱**，覆盖根因 2 和"射频活着但没拨打"的情形。
- **已验证**：强制 `bluetoothctl disconnect` 后，≤10s 内自动重连，全程不碰 USB。
- 若两个文件丢失 → 重建：脚本死循环上述逻辑；service 用 `ExecStart=~/.local/bin/bt-spa3609-reconnect.sh`、`WantedBy=default.target`，然后 `systemctl --user daemon-reload && enable --now`。

## 诊断手法（实测顺序）

1. `bluetoothctl info XX:XX:XX:XX:XX:XX` → `Paired: yes` + `Trusted: yes` + `Blocked: no` 就不许动配对；`Connected:` 看当前状态。
2. `journalctl -u bluetooth | grep XX:XX:XX:XX:XX:XX` → 出现 `Host is down (112)` = 那次尝试时音箱没开机/在待机，**不是电脑故障**。
3. `dmesg | grep -iE "suspend|hci0"` → `Timed out waiting for suspend events` = AX201 休眠 bug（补充手段，非主因）。
4. 实机 30s 测试：让用户把音箱开成蓝牙模式，轮询 `bluetoothctl info` 30s——若自动 `Connected: yes`，PC 侧 100% 没问题，别再去动电脑配置。
5. 音频链路：`pactl list sinks short` → `bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink ... RUNNING` = A2DP 48kHz 高质量已生效。

## 硬性警告（踩过的坑，不要再犯）

1. **不要取消配对/去掉 Trusted**。Trusted=yes 是 BlueZ 允许自动连接的开关，删了配对 = 永远手动。
2. **音箱彻底断电时没有任何软件能唤醒它**，看门狗也不行（射频死了）。唯一唤醒 = 按音箱电源/BT 键。想要全自动就保持音箱通电。
3. **别边用手机/电视连这个音箱**：它的"上次设备"记忆只指向最后一个设备。如果拿手机试过，回来时要按一下音箱 BT 键让它重拨，或等 15s 让看门狗抢连。
4. `Host is down` 出现时**先查音箱再查电脑**，别误导用户去换驱动/重装 bluez。
5. AX201 休眠挂死 ≠ 网卡坏了，不要建议换硬件；先试 `systemctl restart bluetooth` 或 `rfkill block/unblock bluetooth`。
6. 本机 SPA3609 是 **A2DP sink**（非 HSP），别去改 profile 或加 AAC 插件，默认 sbc 与此音箱兼容良好。

## 环境事实（实测记录，别乱改）

- 音箱 MAC：`XX:XX:XX:XX:XX:XX`（public），Class 0x00240418，A2DP 48kHz。
- 适配器：**Intel AX201**（内置，经 USB 总线 btusb，`8087:0026` @ usb 3-10），控制器 `YY:YY:YY:YY:YY:YY`，固件 `intel/ibt-19-0-4.sfi`；HCI 5.2。
- 本机音频：PulseAudio（非 PipeWire 主音），音箱连上后成为 RUNNING sink，HDMI sink 转 SUSPENDED。
- 最近一次失败：Sep 24 23:32 `Host is down`（音箱未开）；随后实机 30s 测试自动连上，看门狗断开重连 ≤10s。

## 分支场景

### A. 音箱开着但就是不自动连
1. 先看 `Connected:`——已连但没声音 → 查 `pactl` sink 是否默认/是否 RUNNING，切到 `bluez_sink.XX_XX_XX_XX_XX_XX`。
2. 未连 → 十有八九上次设备是手机/电视：按音箱 BT 键重拨，或直接 `bluetoothctl connect XX:XX:XX:XX:XX:XX`。
3. 3s/15s 内未回连 → 按电源键彻底断电重开一次（等价于用户的老办法"插拔 USB"）。

### B. 笔记本睡眠唤醒后连不上
1. `systemctl restart bluetooth` → 看门狗会在 15s 内抢连。
2. 若复发，属 AX201 suspend bug：可加 systemd 睡眠钩子在 resume 时 restart bluetooth（普通用户场景先用不着，别提前加）。

### C. 想确认"到底是电脑还是音箱"的问题
- 只跑一步：让用户开音箱，`for i in $(seq 1 6); do bluetoothctl info XX:XX:XX:XX:XX:XX | grep Connected; sleep 5; done`。
- 30s 内 `Connected: yes` → 电脑没问题，问题在音箱待机/记忆，转分支 A。

### D. 音箱彻底没反应（电源键也没用）
- 检查音箱自身供电/USB 线（它就是 USB 供电的），与电脑蓝牙无关。