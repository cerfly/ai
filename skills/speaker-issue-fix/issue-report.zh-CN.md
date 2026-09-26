# 案例报告 — Philips SPA3609 蓝牙音箱无法自动连接

- **日期**:2026-09-24(初次);2026-09-27(根因修正补充)
- **机器**:Linux Mint 21 笔记本(用户 `cerfly`),内核 5.15.0-191-generic,
  BlueZ 5.64 (bluetoothd)、PulseAudio、blueman
- **技能**:`skills/speaker-issue-fix/SKILL.md`(本案例遵循的通用方法论)
- **隐私**:MAC 地址一律打码为 `XX:XX:XX:XX:XX:XX`(适配器
  `YY:YY:YY:YY:YY:YY`);真实值仅存于本机系统服务文件

## 1. 症状

- Philips SPA3609 蓝牙音箱(USB 供电,**零物理按键**)无法自动连接。
- 用户必须手动插拔 USB 线才能连上;否则连接失败(`Host is down`),或笔记本重启后
  音箱明明上电却一直被拒。
- 后续症状(2026-09-27):PC 开机后蓝牙面板出现持续的"连接/断开"闪烁,但始终连不上。
- 最初怀疑是电脑(蓝牙/驱动/音频)的问题。

## 2. 诊断与发现

| 步骤 | 命令 | 结果 |
|---|---|---|
| 设备信息 | `bluetoothctl info XX:XX:XX:XX:XX:XX` | `Paired: yes`、`Trusted: yes`、`Blocked: no` ✓ |
| 适配器 | `bluetoothctl show` / `hciconfig -a` | 已供电、未屏蔽;Intel AX201(HCI 5.2,USB 总线) |
| 蓝牙日志 | `journalctl -u bluetooth \| grep <MAC>` | 混合出现 `Host is down (112)`、`Permission denied (13)`、`Connection refused (111)`、`br-connection-unknown` |
| 内核日志 | `dmesg \| grep -iE "suspend\|hci0"` | 故障当天无 suspend 事件(适配器健康) |
| 音频链路 | `pactl list sinks short` | 连接时:`bluez_sink.XX_XX_XX_XX_XX_XX.a2dp_sink … RUNNING`(A2DP) |
| **USB 设备模式** | `aplay -l \| grep -i philips` | **插在数据 USB 口时:`card 1: USB [… SPA3609 USB]` = 声卡模式** |

### 报错 → 含义对照(实测)

- `Host is down (112)` —— 音箱射频没在听(断电、待机,或处于声卡模式)。
- `Permission denied (13)` / `Connection refused (111)` / `br-connection-unknown` ——
  射频活着且能响应,但**拒绝 A2DP profile**:说明它仍处于声卡模式,或持有损坏/过期的配对。
- 底层能连上(`Connected: yes`)但 profile 随后报 `br-connection-unknown` —— 同一含义:
  设备侧 A2DP 服务被关闭。

### 决定性实测(区分"电脑 vs 设备")

1. **蓝牙模式实况轮询**(09-24):音箱处于蓝牙模式时轮询 `bluetoothctl info` 30 秒
   → 全程 `Connected: yes`。电脑侧 100% 没问题。
2. **双模验证**(09-27):同一只音箱插笔记本数据口 → 被识别为 USB 声卡,**拒绝一切
   BT 连接**(`br-connection-unknown`)。改插纯供电 USB 口(显示器 USB 口)→ 不再
   被识别为声卡,蓝牙恢复正常。

## 3. 根因

SPA3609 是**双模式音箱,模式由 USB 连接决定**(没有任何按键可切换):

1. **首要根因(09-27 确认)**:插在**带数据能力的 USB 口**(笔记本、接了笔记本的 hub)
   时变成 USB 声卡,蓝牙服务被关闭——BT 拨打返回 `Permission denied`/`br-connection-unknown`,
   看门狗的重试循环在外观上就像"连接/断开闪烁"。插**纯供电口**(显示器 USB 口、手机
   充电头)才是蓝牙模式。
2. **次要根因**:待机 / "上次设备记忆"——射频闲置,或只拨打最后用过它的设备
   (手机/电视),而不是 PC。用户"插拔 USB" = 给音箱断电重启(或换到纯供电口),
   让它重新拨打 PC。
3. **环境隐患**:Intel AX201 可能在休眠/唤醒时挂死(`-110`),唤醒后蓝牙静默。

## 4. 已实施的修复

### A. 使用规则(真正的修复)
- **用蓝牙(无线)**:音箱一直插在**纯供电 USB 口**(显示器 USB 口 / 充电头),别插
  笔记本数据口。
- **用 USB 声卡模式**:插笔记本 —— 直接可用,蓝牙按设计关闭。

### B. PC 侧看门狗(主动拨打 + 智能退避)
- `~/.local/bin/bt-spa3609-reconnect.sh` —— 循环:未连接就 `bluetoothctl connect`
  (单次尝试限 ~12 秒);前 5 次失败约每 20 秒快速重试,之后**退避到 60 秒并静默**;
  一旦连接成功立刻恢复快节奏。
- `~/.config/systemd/user/bt-spa3609.service` —— `Restart=always`,登录自启。

```bash
systemctl --user enable --now bt-spa3609
systemctl --user status bt-spa3609     # active
systemctl --user stop bt-spa3609       # 临时停
systemctl --user disable bt-spa3609    # 取消自启
```

### C. A2DP 被拒时的恢复流程(过期配对 / 卡死模式)
已实测一次治愈:`bluetoothctl remove XX:XX:XX:XX:XX:XX` → 音箱**完全断电 ≥60 秒**
(真断电)→ 插回纯供电口 → 它会自动广播配对 → `bluetoothctl scan on`、`pair`、`trust`、`connect`。

## 5. 验证(实测数据)

- 看门狗运行中强制 `bluetoothctl disconnect XX:XX:XX:XX:XX:XX`:约 **30 秒内自动重连**,
  全程不碰硬件 ✓
- 恢复流程后(2026-09-27):新配对成功,A2DP sink 恢复为默认输出,看门狗重连复验通过 ✓

## 6. 后续 / 可选

- **AX201 休眠挂死**:睡眠后无声 → `systemctl restart bluetooth`;若复发可加 systemd
  睡眠钩子在唤醒时重启 bluetooth —— 日常使用通常用不上。
- 音箱彻底断电时任何软件都无法唤醒它;保持通电(纯供电口)才能全自动。

## 7. 经验教训(下次直接套用)

1. **先问用户"拔的是什么"** ——"插拔 USB"可能是断电重启,也可能是在切换一个双模设备
   的工作模式。
2. **责怪协议栈之前,先查设备是否带隐藏模式**:同时是 USB 声卡的设备,插上数据口可能
   悄悄关闭蓝牙(`aplay -l` 一眼可见)。PC 侧症状和驱动/密钥问题长得一模一样。
3. `Host is down` = 对方没在听(供电/待机/模式);射频活着却 `Permission denied`/
   `Connection refused`/`br-connection-unknown` = 模式不对或过期配对 —— 先试
   remove + 断电 60 秒 + 重配,再动驱动。
4. 对射频已关的设备做重试循环,会产生肉眼可见的"连接/断开"闪烁 —— 加智能退避让它静默。
5. 最快区分"电脑 vs 设备":把设备放在正确的供电状态下,从 PC 侧轮询
   `bluetoothctl info`(并配合 `aplay -l`)。