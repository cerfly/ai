# 问题报告:Philips SPA3609 蓝牙音箱无法自动连接

- **日期**:2026-09-24
- **机器**:linuxmint / user `cerfly`(笔记本,内置 Intel AX201)
- **环境**:Linux Mint 21,内核 5.15.0-191-generic,BlueZ 5.64(bluetoothd),PulseAudio,blueman
- **关联技能**:`skills/fix-issue/SKILL.md`(本目录)

## 1. 症状

- Philips SPA3609 蓝牙音箱(USB 供电)不能自动连接。
- 每次要"插拔 USB"后才能自动连上;不插拔就一直是 `Host is down` / 连不上。
- 怀疑是电脑(蓝牙/驱动)的问题。

## 2. 诊断过程与发现

| 步骤 | 命令 | 结果 |
|---|---|---|
| 设备列表 | `bluetoothctl paired-devices` | 已配对,含 `XX:XX:XX:XX:XX:XX Philips SPA3609` |
| 设备属性 | `bluetoothctl info XX:XX:XX:XX:XX:XX` | `Paired: yes`, `Trusted: yes`, `Blocked: no` ✓ |
| 适配器 | `bluetoothctl show` / `hciconfig -a` | Powered、未封锁;Intel AX201(HCI 5.2) |
| 蓝牙日志 | `journalctl -u bluetooth \| grep MAC` | 唯一一条:`connect to …: Host is down (112)`(尝试时音箱未开机) |
| 内核日志 | `dmesg \| grep -iE "suspend\|hci0"` | `hci0: Timed out waiting for suspend events` / `Suspend notifier action (3) failed: -110`(AX201 休眠 bug) |
| 音频链路 | `pactl list sinks short` | 连上后:`bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink … RUNNING`(A2DP 48kHz) |

**关键观察**:PC 侧配置完全正确;`Host is down` 只出现在音箱未开机/待机时。

### 实机 30s 测试(判定"电脑 vs 音箱")

音箱开机成蓝牙模式后,轮询 `bluetoothctl info` 30 秒 → 全程 `Connected: yes`,**自动连上**。
→ PC 侧 100% 没问题,问题在音箱侧。

## 3. 根因分析

1. **主因**:SPA3609 是 USB 供电的低端音箱,蓝牙射频经常处于待机/"上次设备"记忆状态;
   用户"插拔 USB"实际上是**给音箱断电重启**,唤醒其射频并让它重新拨打上次设备(本机)。
   电脑只是被动等待,从不主动拨打。
2. **次因**:音箱的"上次设备"记忆会被手机/电视抢走,开机后只拨打它们。
3. **环境隐患**:Intel AX201 在笔记本休眠/唤醒时可能挂死(suspend timeout -110),
   唤醒后蓝牙完全静默。

## 4. 修复方案(已实施)

**思路**:让 PC 主动拨打音箱,不再等音箱来连——用 systemd 用户服务做看门狗。

### 文件

- `~/.local/bin/bt-spa3609-reconnect.sh` — 循环:每 15s 检查未连接则 `bluetoothctl connect`,已连接则每 30s 复查。
- `~/.config/systemd/user/bt-spa3609.service` — `Restart=always`,登录自启。

### 启用/控制

```bash
systemctl --user enable --now bt-spa3609
systemctl --user status bt-spa3609     # active
systemctl --user stop bt-spa3609       # 临时停
systemctl --user disable bt-spa3609    # 取消自启
```

## 5. 验证(实测)

- 看门狗启用后,强制 `bluetoothctl disconnect XX:XX:XX:XX:XX:XX`。
- **≤10 秒内自动重连,全程未碰任何 USB/电源** ✓
- 之后用户日常使用:音箱保持通电(待机),掉线后 ~15s 内自愈。

## 6. 遗留 / 可选增强

- **AX201 休眠挂死**:若睡眠唤醒后仍连不上 → `systemctl restart bluetooth`(看门狗 15s 内抢连);
  复发可加 systemd 睡眠钩子(resume 时 restart bluetooth)。普通使用暂不需要。
- 音箱彻底断电时任何软件都唤不醒它,只能物理按电源键;想全自动就保持通电。

## 7. 教训(下次别再踩)

1. "插拔 USB"这类用户习惯往往等于**给设备断电重启**,先问清楚插拔的是什么。
2. `Host is down` = 对方没在听,先查设备本身,别急着动电脑配置。
3. 低端蓝牙音箱的"上次设备记忆"是自动连接失败的高频根因,看门狗(主动拨打)是对策。
4. 判定责任方最快的方法:让设备开机,30s 轮询是否自动连上。