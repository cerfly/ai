# cerfly/ai — 个人 AI 技能与自动化工具集

本仓库存放个人常用的 AI 辅助技能(可被 opencode 等工具加载)与配套脚本。

## 目录结构

| 目录 | 说明 |
|------|------|
| `skills/szse` | 深圳图书馆借阅数据采集 · 统计 · 可视化看板(详见下方) |
| `skills/youtube-summarize` | YouTube 视频总结技能(详情见其 `SKILL.md`) |

---

## skills/szse — 深圳图书馆借阅数据看板

对深圳图书馆(UILAS ILASOPAC,`ilas.szclib.org.cn`)的家庭借阅账户做**只读**数据采集与分析:

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
    sanitize.py     脱敏导出脚本(供公开场合使用)
  assets/           echarts.min.js(构建时内联进看板)
  data/             原始抓取数据(含完整身份证号,被 gitignore,**勿提交**)
  export/           脱敏后的公开副本(身份证号已掩码为 前6****后4)
  reports/          借阅分析报告(Markdown)
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