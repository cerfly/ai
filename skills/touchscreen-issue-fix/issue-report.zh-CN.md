# 案例报告 — Pixelbook(eve)触屏失灵:数字转换器已枚举但零事件输出

- **日期**:2026-10-13
- **设备**:Google Pixelbook(2017),主板 `eve`(`eve-signed-mp-v11keys`),2-in-1 可折叠本
- **系统**:Chrome OS `16700.63.0`(Official Build),里程碑 **M150**、频道 `ltc-channel`
- **技能**:`skills/touchscreen-issue-fix/SKILL.md`(本案例遵循的通用方法论)
- **隐私**:不涉及 MAC/序列号;设备与系统标识均为系统自身输出

## 1. 症状

- 触屏对手指无任何响应;屏幕显示、键盘、触摸板均正常。
- 不存在任何变通手段(没有任何操作能让触摸恢复)。

## 2. 诊断与发现

| 步骤 | 命令 | 结果 |
|---|---|---|
| 系统 / 主板 | `/etc/lsb-release`、`/sys/class/dmi/id/product_name` | Pixelbook(`eve`),M150 `16700.63.0`,`ltc-channel` |
| 内核枚举 | `cat /proc/bus/input/devices` | `event6` = `WCOM50C1:00 2D1F:5143`,总线 `0x18`(I2C-HID),`PROP=2`(DIRECT),`ABS=6f3800001000003` —— 触屏存在 ✓ |
| 手写笔数字转换器 | 同上 | `event8` = `… Stylus` 存在 ✓ |
| 触摸板(对照组) | 同上 | `event5` = `ACPI0C50:00 18D1:5028`,`PROP=5` 存在 ✓ |
| 设备能力 | `evtest /dev/input/event6` | 完整多点触控:`ABS_MT_SLOT` max 9、`ABS_MT_POSITION_X/Y`、`ABS_MT_PRESSURE`、`ABS_MT_TRACKING_ID`、`BTN_TOUCH`、`INPUT_PROP_DIRECT`;面板尺寸相符(10368/40 × 6912/40 mm ≈ 12.3") |
| 原始触摸捕获 | `timeout 20 evtest /dev/input/event6 > /tmp/touch.log 2>&1` + `grep -a 'Event:'` | 手指划过 20 秒,**0 个事件**(日志共 67 行,恰为 evtest 头部) |
| **对照组** | `timeout 10 evtest /dev/input/event5`(触摸板) | **9760 个事件** —— 同一套工具、同一权限 ✓ |
| 内核日志 | `dmesg` | 不可读(`no_new_privs` 阻止 `sudo`;空日志是权限产物,不是"无错误") |
| 冷启动 | 电源菜单 → 关机,等 ~30 秒,再开机 | 复测触摸仍静默 |

备注:

- `evtest /dev/input/event6` **未用 sudo** 直接打开成功 —— 本构建的事件节点对普通用户可读。
- `sudo` 被开发环境 shell 的 `no_new_privs` 标志拦截:
  ```
  sudo: The "no new privileges" flag is set, which prevents sudo from running as root.
  ```
- 第一次交互式 `evtest` 输出里的 `Esc[1;2B` 序列是终端对 **Shift+↓ 按键的回显**,不是触摸
  数据;所有定量测量均重定向到文件。

## 3. 根因

Wacom 数字转换器(厂商 `2d1f`)能**通过 I2C-HID 完成枚举** —— 供电、总线、HID 描述符均完好
—— 但**从不投递触摸报告**。该结论来自 `evtest` 对原始内核输入层的直接读取,绕过了
ChromeOS 的输入/UI 栈,因此:

- **不是**设置 / 无障碍 / 策略 / 手势问题。
- **不能**通过 Powerwash 或重装系统修复(那只重置软件层)。
- 冷启动(EC 复位)也无效。

结论:**触控数字转换器属硬件级故障**,最可能是手指**触控感应层**或控制器**中断(IRQ)线**
损坏 —— 典型的"已枚举但静默"画像。

Eve(Pixelbook 2017)已过 Auto Update Expiration,`ltc-channel` 配 M150 属于非常规组合;
曾考虑过构建回归,但原始 0 事件已排除软件因素。

## 4. 已实施修复 / 决策

**不存在软件修复** —— 这本身即是结论,而非修复。按序已执行:

1. 核对内核枚举与能力(无需特权)。
2. 原始事件捕获 → 0 事件。
3. 触摸板对照组 → 9760 事件(方法有效)。
4. 完全冷启动 → 无变化。
5. EC/硬件复位(Refresh + Power)→ 撰写时尚未执行。

该设备的硬件选项(按成本/难度递增):

- 测**手写笔**(`event8`)—— 若可用则保留笔输入。
- **重插显示/数字转换器排线**(主板侧)(DIY;IRQ 线假设值得一试)。
- **更换屏幕总成** —— Pixelbook 触控层与 LCD 一体;2017 年已停支持设备上通常不划算。

务实结论:以键盘 + 触摸板方式继续使用。

## 5. 验证(实测)

| 测试 | 结果 |
|---|---|
| 触屏事件,20 秒滑动 | **0** |
| 触摸板,同一方法,10 秒 | **9760** ✓ |
| 冷启动后触屏复测 | 仍为 **0** |

9760-vs-0 的对比是关键实测:同一工具、同一用户、同一权限,不同设备 → 触屏本体静默。

## 6. 后续 / 可选

- **手写笔测试**(`event8`):确认笔输入是否幸存。
- **EC/硬件复位**(长按 Refresh + Power):最后一个免费尝试。
- **排线重插**:DIY,仅对自己动手有信心时执行。
- **Diagnostics 应用触屏测试**(设置 → Diagnostics):无需 root 的官方确认,此处与
  `evtest` 结论等价。

## 7. 经验教训(下次直接套用)

1. **`lsusb` 是排查触屏的错误工具** —— 触屏走 I2C-HID,不出现在 USB 上;用
   `/proc/bus/input/devices` 与 `evtest`。
2. **没有对照组,0 事件毫无意义** —— 先用完全相同的命令测一个已知良品的兄弟设备
   (触摸板)。
3. **已枚举但静默 = 硬件** —— `evtest` 证明 0 事件且对照组通过后,就别再折腾 ChromeOS:
   任何设置 / Powerwash / 重装都作用不到输入层之下。
4. **没有特权时别相信空 `dmesg`** —— `no_new_privs`/限制会让它看起来干净;而
   `/dev/input/eventN` 往往**不用 sudo** 也能 `evtest`,直接试。
5. **终端回显可能伪装成数据** —— 判断"无事件"前,务必把 `evtest` 输出重定向到文件。
6. **冷启动 + EC 复位各做一次,然后记录结论** —— 对已硬件故障的面板反复断电重启纯属浪费时间。