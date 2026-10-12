# Steam 独立游戏雷达：Google Apps Script 独立保底调度

> 与 Google Sheets 绑定，不依赖 GitHub `schedule`。这一步需要工作表所有者**手动进行一次 OAuth 授权和触发器安装**；GitHub 提交源代码不等于已安装。无需新建 ChatGPT 定时任务。

## 安装（只需一次，预计几分钟）

1. 打开既有 [Steam 独立游戏雷达 Google Sheet](https://docs.google.com/spreadsheets/d/18qblps5QEsEObRL7TJuEpAfEQKGbmeLcU3AuicGRZfU/edit)，选择 **扩展程序 → Apps Script**。
2. 将仓库中的 [steam_radar_backup.gs](./steam_radar_backup.gs) 全文复制到项目的 `代码.gs`，保存。它不会更改原 Sheet 业务数据，仅只读「运行日志」并在需要时向 GitHub 发送 workflow_dispatch。
3. 在 GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens 生成一个仅授权仓库 `945882813/steam-index-proxy` 的令牌，Repository permissions 仅开启 **Actions: Read and write**（及系统默认 Metadata: Read）。不要把此令牌存放在工作表、GitHub 代码或聊天消息中。
4. Apps Script 左侧齿轮「项目设置 → 脚本属性」建立三项：

   | 属性名称 | 值 |
   |---|---|
   | `STEAM_RADAR_SHEET_ID` | 现有工作表 ID：`18qblps5QEsEObRL7TJuEpAfEQKGbmeLcU3AuicGRZfU` |
   | `STEAM_RADAR_REPO` | `945882813/steam-index-proxy` |
   | `STEAM_RADAR_GITHUB_TOKEN` | 刚创建的细粒度 GitHub PAT，**请只输入到脚本属性** |

5. 在 Apps Script 中选择函数 `setupRadarBackup` 并点击 **运行**，按提示授权（Google Sheets / 对外请求 / 安装定时触发器）。成功后会创建 **每 10 分钟一次**的安装式触发器，但只在北京时间 **06:30–09:05** 做联网补采检查。
6. 选择 `inspectSteamRadarBackup` 点击运行做**只读验收**，查看「执行记录」输出；不触发生产采集。检查定时触发器面板中是否有 `steamRadarBackupTick`。
7. 在日常采集未排队/执行时，**人工主动运行一次** `testIndependentRadarDispatchOnce`。此函数会实际调用 GitHub 的 `workflow_dispatch`，每天最多允许一次真实测试；即使当日已经完成发现与评论采样，也允许实际派发一次；现有 `daily_recovery.py` 应跳过已完成的发现和评论样本，不重复增加相同日期、AppID 与语言的记录。**如果有新采入的可信 CCU，黑马后验评估可以正常增量刷新，不一定整轮全 SKIP。**它会在「执行记录」打印 `GitHub HTTP 204`，表明 GitHub 接受请求，但此时还不代表执行成功。不要把 Token 填进聊天或工作表。
8. 打开 [GitHub Actions → Steam Radar - Early Daily Collection and Recovery](https://github.com/945882813/steam-index-proxy/actions/workflows/radar-v12.yml)，找到本次 `workflow_dispatch` 运行，确认各步骤成功，并回读 Sheet：正常成功重跑不应重复添加当日候选、评论采样或黑马后验记录。**这才完成独立平台真实派发验收。**
9. 次日早间在 06:30–09:05 观察自动触发器。需要验证**真正缺采后的自动补救**时，必须先确认确有缺口，再观察 `steamRadarBackupTick` 是否在窗口内自动派发；不要删除或改写生产样本来人为制造缺口，也不要把第 7 步主动测试冒充无人值守的缺采补救验收。

## 验收状态的三个层次

- **已部署代码**：GitHub 源文件和语法测试存在，不表示 Apps Script 已安装。
- **独立派发已验证**：账户所有者手动调用 `testIndependentRadarDispatchOnce`，GitHub 接收到 dispatch 且幂等工作流成功运行，不新增重复样本。
- **无人值守缺采补救已验证**：GitHub 当天确实缺席或失败，Google Apps Script 安装式触发器自动调用 `steamRadarBackupTick` 并完成后验落表。只有第三阶段才能声称独立保底全部闭环。

## 如何防止重复与限流

- 首先核验中文「运行日志」中**当日**「新作候选发现」「评论累计采样与增速」「黑马预测后验评估」三项成功。
- 查询 GitHub 当前早间运行：正在排队或运行时不再派发；同一天已完成则靠 Sheet 的实际完成状态决定是否重试。
- 使用 `LockService` 防止 Apps Script 自己并发，使用 `ScriptProperties` 保存最后一次派发时间，**90 分钟冷却**。
- 真正的 AppID、语言、预测行去重由 GitHub 的 `daily_recovery.py` 保证；因此新脚本不会直接写任何 Steam 采样行。
- Google Apps Script 时钟触发器和 GitHub 定时触发器都非硬实时；这个设计提供**不同平台的故障隔离**，不能保证 09:30 一定获得新数据。

## 安全、权限和常见问题

- **不要**共享含令牌的脚本属性或复制包含令牌的执行日志；脚本只输出状态和日期。
- 若原 Google Sheet 有其他共同编辑者，优先使用**仅自己可编辑的独立 Apps Script 项目**安装同一份代码（代码用 Sheet ID 打开目标表，不要求必须绑定）；不要让共享表的其他编辑者接触 GitHub Token 或脚本属性。
- 建议把 GitHub PAT 设置有效期并定期轮换；Token 到期或权限不足会在 Apps Script 执行记录中出现 401/403。无需改 GitHub 已有的 `GOOGLE_SERVICE_ACCOUNT_JSON`、`GOOGLE_SHEET_ID` Secrets。
- 安装式触发器以创建它的 Google 身份运行；该身份须能查看现有 Sheet。
- 若要停用：Apps Script → 触发器，删除 `steamRadarBackupTick` 的时间触发器，然后撤销 GitHub PAT。
- 此脚本**尚未由本助手安装到你的 Google 账户**，因为目前连接器不支持创建 Apps Script 工程并代用户完成 OAuth 与安装触发器。安装完成之前仍只有 GitHub 自身的非独立保底机制。

## 相关生产文件

- `.github/workflows/radar-v12.yml`：每日提前采集、幂等补采。
- `daily_recovery.py`：每次执行时判断 Sheet 内的今日真实完成状态。
- `radar_morning_fallback.py`：已有的 GitHub Watchdog 内部保底。
- `github_run_health.py`：独立于 Google Sheet 的 GitHub 运行状态验证。
