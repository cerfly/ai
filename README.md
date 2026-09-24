# cerfly/ai — 个人 AI 技能与自动化工具集

本仓库存放个人常用的 AI 辅助技能(可被 opencode 等工具加载)与配套脚本。

## 目录结构

| 目录 | 说明 |
|------|------|
| `skills/szse` | 深圳少儿图书馆借阅数据采集 · 统计 · 可视化看板(详见下方) |
| `skills/szlib-tracker` | 深圳图书馆(szlib.org.cn,成人馆)借阅跟踪 —— 与少儿馆 szse 区分 |
| `skills/youtube-summarize` | YouTube 视频总结技能(详情见其 `SKILL.md`) |
| `skills/fix-issue` | 本机已解决问题的修复流程与记录(蓝牙音箱自动连接等,详见下方) |

---

## skills/fix-issue — 本机问题修复记录

收录本机**已解决的具体问题**及其修复程序(可被 opencode 等工具加载)。每个问题一个
`SKILL.md` + 配套 `issue-report.md`:

- **蓝牙音箱自动连接(Philips SPA3609)**:PC 侧配置本无问题,根因是音箱待机/"上次设备
  记忆";修复 = systemd 看门狗服务让 PC 主动拨打。排查记录见 [`issue-report.md`](skills/fix-issue/issue-report.md)。

> ⚠️ 本目录内容含本机蓝牙 MAC 地址与路径,属半公开信息,公开仓库可见。

---

## skills/szse — 深圳少儿图书馆借阅数据看板

> 本技能数据源是**深圳少儿图书馆**(UILAS ILASOPAC,`ilas.szclib.org.cn`),与深户**深圳图书馆**(`szlib.org.cn`,成人馆,见 `skills/szlib-tracker`)**不是同一系统**,本机 4 个家庭账户均为少儿馆读者。

对深圳少儿图书馆的家庭借阅账户做**只读**数据采集与分析(唯一写操作 `renew.py` 续借,默认 dry-run、需明确确认):

- 自动登录(身份证号 + 验证码 OCR,`ddddocr`)
- 抓取当前在借、近 N 个月借阅史、全量借阅史统计
- 生成自包含 ECharts 数据看板(`dashboard.html`,单文件、离线可开)
- 生成 Markdown 借阅分析报告

### 目录说明

```
szse/
  szse              账户凭据(身份证号+密码,被 gitignore,**勿提交**)
  SKILL.md          使用流程说明(详细反向工程记录)
  scripts/
    szse_lib.py     数据抓取脚本(当前在借 + 借阅史 + 统计)
    dashboard.py    看板生成器(输出自包含 HTML)
    plan.py         待还计划 CLI(手动记录要还的书,看板提醒)
    plan_view.py    plan.html 编辑器生成器(内嵌在借快照)
    renew.py        续借工具(默认 dry-run,`--go --yes` 才会真实执行,唯一写操作)
    sanitize.py     脱敏导出脚本(供公开场合使用)
  assets/           echarts.min.js(构建时内联进看板)
  data/             原始抓取数据(含完整身份证号,被 gitignore,**勿提交**)
  export/           脱敏后的公开副本(身份证号已掩码为 前6****后4)
  reports/          借阅分析报告 / 最近借还记录 / 续借规则(Markdown)
```

### 快速开始

依赖:`python3` + `ddddocr` + `requests`(装于 `~/.local`)。

```bash
cd skills/szse
# 1. 凭据文件格式:每两行一组 身份证号 + 密码
cat > szse <<'EOF'
<身份证号1>
<密码1>
<身份证号2>
<密码2>
EOF

# 2. 抓取:当前在借 + 近3个月借阅史(数据写入 data/)
python3 scripts/szse_lib.py

# 3. 生成自包含看板(全量借阅史首次抓取较慢,之后走缓存)
python3 scripts/dashboard.py

# 4. (可选)导出脱敏副本到 export/,可安全公开/上传
python3 scripts/sanitize.py
```

### 隐私说明

- `szse` 与 `data/` 下的原始抓取结果含**完整身份证号**,已被 `.gitignore` 排除,请勿强制添加或外传。
- 公开发布前请运行 `scripts/sanitize.py`,它会将所有身份证号掩码为 `前6****后4` 后输出到 `export/`。

### 常用脚本参数

```bash
python3 scripts/szse_lib.py --history-months 6        # 回溯窗口
python3 scripts/szse_lib.py --all-history             # 追加全量借阅史统计(较慢,约5分钟)
python3 scripts/dashboard.py --refresh-full           # 强制重抓全量借阅史
python3 scripts/dashboard.py --no-fetch               # 纯离线重建(仅用本地缓存)
python3 scripts/dashboard.py --dummy                  # 演示数据(验证模板用)
```

### 待还计划(防忘还)

```bash
python3 scripts/plan.py import          # 把当前在借自动导入计划
python3 scripts/plan.py add "书名" --due 2026-10-01 --who 账户3·1987 --intent 提前还 --note 备注
python3 scripts/plan.py tag "书名" --intent 延迟 --note "等第二卷到馆再还"   # 改意图/备注/应还日
python3 scripts/plan.py check "书名"    # 加入清单;uncheck 移出
python3 scripts/plan.py list            # 按应还日排序,含 勾/方式/剩余天数/备注
python3 scripts/plan.py brief           # 生成勾选式简要清单(仅含已勾选条目)
python3 scripts/plan.py brief --out data/return_plan_brief.md   # 保存为文件
python3 scripts/plan.py done "书名"     # 还掉后标记; undo 撤销; remove 删除
```

- 每本书可标**归还方式**:`提前还` / `按期`(默认) / `延迟`,并可单独加备注。
- 计划存于 `data/return_plan.json`;维护统一用 `plan.html` 编辑器或 `plan.py` CLI(看板不含待还计划,避免与真实在借混淆)。

### 可视化编辑器(独立界面)

```bash
python3 scripts/plan_view.py                 # 合并 4 账户在借 + 已有计划 → 生成 plan.html(内置快照)
xdg-open skills/szse/plan.html               # 或双击打开,免服务器
```

打开即**默认加载 4 个账户的全部当前在借书目**。**书目与当前借阅严格一致**:快照由 `plan_view.py` 从在借数据生成,只含真实在借的书(已还的自动消失),不会出现没借过的书。

- **统计卡片(简化版 dashboard)**:在借/准备还/超期/7天内/提前还/延迟 六个图标卡片,点卡片即筛选对应书目;**到期分布条**(超期/7天内/8~30天/30天后 占比 + 图例)
- **按账户筛选**(下拉:全部/账户1·2020…账户4·1966)、状态(计划中/全部/仅已还)、搜索
- **自定义排序**:应还日近→远 / 远→近 / 剩余天数 / 题名 / 账户
- 勾选 = **准备还**(不勾 = 不还,筛选/排序状态下同样有效);**勾选的书自动归类到表格顶部的「准备还」分组,未勾的列入「暂不还」,**已还的归入「已还」组**;重绘不抢焦点、自动把当前勾选行保持在视口内,可**连续勾选不跳页顶**;表头复选框可**一键全选 / 全部取消**
- **列显隐**:工具栏「列」菜单可隐藏/显示任意列(账户、备注、操作…),选择自动记忆
- 改方式与备注、改应还日、标记已还、删除条目、导入在借 CSV
- 生成并下载勾选清单(`待还清单_YYYY-MM-DD.md`),按 提前还/按期/延迟 分组,**跟随当前账户/搜索/状态筛选**(选了某账户就只导出该账户的勾选书目)

备注只由你自己填写(系统不会自动添加);数据经浏览器 File System Access API 直接读写 `data/return_plan.json`(不支持时自动降级为"导入/导出文件");每次抓取最新在借后重跑 `python3 scripts/plan_view.py` 即可刷新快照。