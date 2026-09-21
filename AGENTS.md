# AGENTS.md — 提交前须知

## 每次 git 提交/推送前必须做的事
1. 先 `git status --short` + `git diff --stat`,把**主要修改文件清单**列给用户看(哪些改了、哪些是新增)。
2. 指出任何**可疑/无关/私有**的文件(如 `henren778*`、`data/`、凭据、临时产物),标记为"建议不提交"。
3. **等用户明确同意后**才 `git add` + `git commit`;push 前同样先征求同意。
4. 不要因用户"继续"就默认跳过 review —— 每次提交独立 review。

## 规则
- 本仓库是 **公开仓库**(cerfly/ai)。绝不让 `data/`、`szse` 凭据、`henren778*`、`transcripts/` 等私有内容进入提交。
- `git push` 用 `pull --rebase` 后再推,priority: 先展示 diff 摘要。
- 提交信息简洁、与仓库现有风格一致。