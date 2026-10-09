# AI_RULES.md — 本仓库 AI 修改宪法（单一事实源）

本文件是所有 AI（含未来任意会话/助手）修改 `niuxiong123/-2026` 站点时的**强制行为锚**。
目的：在"免密钥好改"的前提下，防止 AI 跑偏导致线上温度计/仓位建议失真。

## 0. 仓库定位
- 站点：`https://niuxiong123.github.io/-2026/`（GitHub Pages，来源 `main` 分支 `docs/`）
- 网页（展示+计算）：`docs/index.html`（部署源），`web/index.html`（镜像，须同步）
- 网页后台（数据源/引擎）：`engine.py` `fetch_macro.py` `app.py` `daily_job.py` `alert.py` `quote.py` `macro.json` `niuxiong.db`
- 审计/蓝图（事实依据）：资料库《大盘牛熊温度13项》、对比文档、`E_plan_blueprint.md`

## 1. 改动边界（谁能动什么）
- ✅ 默认只改 `docs/index.html` 的**展示层/UI**（折叠、文案、卡片、标签）。
- ⚠️ 改**评分核心**（`engine.py` 权重 `w`/`wM`/`wE`、`basePosition`、`tanh`、保险丝三柱、美债硬上限、envAdj 公式、命理硬上限）必须：
  1. 先说明"为什么改"（底层逻辑）；
  2. 改完**必须跑内部一致性校验**（见 §4）；
  3. 在回复里明示改动行号与零回归证据。
- ❌ 禁止：删除用户文件、删除工作日志 `.workbuddy/memory/`、改部署脚本 `一键发布到GitHub.sh` 不改引用。

## 2. 铁律（不可"优化"掉）
- **命理财杀年总仓位硬上限**（2026-27 为 4.5 成）是固定约束，AI 不得为"显得更准"而调高。
- **温度纯净度**：温度只答"贵贱"，环境项（美债/汇率/货币/盈利）移出温度只做轻度 `envAdj`，且只计一次（无双计）。这是已定架构，回退需用户明示。
- **八大信号保险丝**、**顶底判定门不进温度权重**为既定逻辑。

## 3. 修改前必读（硬性第一步，不可跳过）
- **任何 AI 在动键盘前，必须先读本文件（AI_RULES.md）+ 资料库审计文档 + `E_plan_blueprint.md`**，确认改动不是已被否决的方案、不违反 §2 铁律。
- 未读宪法就改 → 视为跑偏；改动须符合"总分总 + 底层逻辑 + 具体应用"输出格式，向用户讲清理由。
- **强制执行机制（2026-10-09 更新）**：分支保护已无技术拦截（见 §6），"先读宪法、先自检"靠纪律 + 惯例落地：所有上线改动先推 `draft` 分支跑 `verify.yml` 校验，全绿后再合 `main`；数据类提交由 `daily.yml` 内置自检兜底。AI 直推 main 前必须已完成本地校验。

## 4. 交付前校验（零回归门槛）
每次宣称"改完"前必须：
1. 本地跑 `node tests/verify_site.js`，全绿；
2. 同步 `web/index.html`；
3. 推到 `draft` 分支并开 PR；`verify.yml` 在 CI 跑同样校验，红灯不许合入 `main`；
4. 合入后抓 `raw.githubusercontent.com` 或 API 核验修复标记在位。

## 5. 推送纪律（安全）
- 日常改动推 `draft` 分支：`git -c http.version=HTTP/1.1 push origin draft`（代理 502 时）。
- 重试仍失败可走 GitHub Git Data API 通道（blob→tree→commit→PATCH ref），**保住历史**。
- ❌ 禁止 `git push --force`、禁止丢失用户文件的 `git reset --hard`、禁止直推 `main`。
- 发布以 git tag 留快照，便于回滚。

## 6. 护栏落地状态
- [x] `tests/verify_site.js`：内部一致性校验（语法 + 回归标记 + 港股跌13月数值 + 命理铁律）
- [x] `.github/workflows/verify.yml`：推送/PR 跑校验，红灯即拦（需在后台设为 main 必过项才成闸门）
- [x] `draft` 分支：所有上线改动入口（AI 推 draft，PR 合 main）
- [x] **GitHub 后台·main 分支保护（2026-10-09 定稿形态，勿凭印象改）**：
  - 背景：曾试过「PR+必过verify」强闸门，实测把 `daily.yml`（GITHUB_TOKEN 直推 main 写数据）永久拦死——GITHUB_TOKEN 的推送不会触发新 workflow，verify 永远无法在机器人提交上先跑，死锁（GH006: Required status check "verify" is expected）。
  - **定稿形态：规则卡片保留（防强推/防删除），所有 Require... 项全部不勾**：
    1. ❌ Require a pull request before merging = 不勾（勾了机器人数据链路断）
    2. ❌ Require status checks to pass = 不勾（同上，死锁根源）
    3. ❌ Require conversation resolution / signed commits / linear history / deployments = 都不勾（单人项目无意义）
    4. 底部 Allow force pushes / Allow deletions = 不勾（即禁止强推与删分支，这是残留硬保护，勿动）
  - **闸门内移**：verify 校验已内置进 `daily.yml`（推送前自检，不过不推），数据链路自带校验。
- ⚠️ **已知安全边界（知情接受，非疏漏）**：现在直推 main 无技术拦截，AI 行为约束完全靠本宪法 §1/§2/§5 + `tests/verify_site.js` 本地自检 + verify.yml 每次推送亮红灯报警（不拦门）。AI 每次改动仍须：先读本文件 → 本地校验全绿 → 推 draft 留痕 → 再合 main。
- ❌ **不要把 `daily.yml` 改成"开 PR + 自动合并"**（已否决方案，勿再提议）：`GITHUB_TOKEN` 触发的 `pull_request` 事件只会进入 **"需要审批"（approval-required）状态**而不会自动运行，必须有人手动点 "Approve workflows to run"；若依赖自动合并 + 必过 check，则数据更新永久卡住。要自动触发必须另配 PAT/GitHub App，复杂度远大于收益。
- [ ] **GitHub 后台·用户本人点（可选）**：本机明文 PAT 降级为细粒度令牌（仅本仓库、contents:write）或 SSH deploy key。

## 7. 一键回滚
任一版本发布即打 tag（如 `site-20261009`）；发现跑偏：`git checkout <tag> -- docs/index.html web/index.html` 后走 draft PR 还原。
