# Steam 独立游戏雷达｜采集系统

## V1.4.2 提前调度及缺失自动补采（2026-10-12）

- **每日数据准备窗口**：`.github/workflows/radar-v12.yml` 不再只有北京时间08:20单次机会。现改为北京时间 **03:17 / 05:47 / 07:17** 三次错峰 `schedule`（UTC分别为19:17 / 21:47 / 23:17，UTC所属日是北京时间前一日）。仍支持人工 `workflow_dispatch`；GitHub schedule有延迟/丢失风险，不保证09:30前必完成。
- **按事实做幂等补采**：`daily_recovery.py` 每轮先核查中文「运行日志」当天新作发现是否OK、实际「评论采样」中每个被观察AppID的all/schinese同口径成功快照和「评论增速」物化行、黑马后验中每个预测ID的更新时间是否覆盖最新可信CCU/评论采样。仅处理未成功/缺失步骤；若全部已经完成，直接退出，不重复写入表格；每次实际采集后再回读完成度，未全量完成则保留Action失败状态并留给下一次窗口补采。
- **失败样本原位修复**：`radar_v12.py reviews` 对已有当日AppID+语言+固定口径的失败记录做批量原位覆盖，而非每次重试增加另一条相同唯一键；成功样本继续复用。自动重试不会制造假24小时增速或污染预测锁定时点。
- **独立保底触发**：现有两小时 `radar-watchdog.yml` 在北京时间06:30–09:05实际运行时，`radar_morning_fallback.py` 会检查当天每日研究是否成功或正在运行；若没有则通过仓库 GitHub Actions `workflow_dispatch` 启动补采，成功、排队或进行中的同日日程不会重复触发，最近一小时刚失败的运行也不会立刻重试。权限仅授予现有Watchdog使用 `actions:write`，不增加ChatGPT定时任务。GitHub工作流之间采用同一并发组串行执行，最终的Google Sheet状态决定是否重采。
- **09:30日报降级原则**：唯一启用的ChatGPT「独立游戏雷达日报」仍在09:30执行；如果Github采集由于延迟尚未到表，日报不能混同历史数据为当天新测，应注明实际可信数据时间、未完成的模块、并正常写日报而非虚构增长。Watchdog如实际运行晚于09:05则不会在当日09:30前触发保底；**不是准点交付SLA**。
- **验收**：离线CI的测试只验证选择性补采决策、失败样本去重和Watchdog防重复派发；只有今后实际定时GitHub Action出现当天新的候选/评论/后验数据，并第二轮无重复写入时，才能认定生产闭环。

## V1.4.1 生产稳定性整改（2026-10-11）

- **生产与代码测试隔离**：CCU Sampler、Steam Radar V1.2 和 Radar Watchdog 的生产 Workflows 只由 `schedule` / `workflow_dispatch` 触发；代码 `push` / `pull_request` 则由 `.github/workflows/radar-ci.yml` 离线编译与测试，不使用生产凭证或读写 Google Sheet。GitHub Actions 定时触发可能延迟。
- **Google Sheets 429 限流防护**：`sheets_retry.py` 只对 API 429/暂时性 5xx 重试，最多5次并指数退避；对权限类 403 立即报错。候选最后发现时间按**每天最多一次**更新并批量提交；评论增速同日不变的数据跳过写入，发生真实变化时一次批量提交，避免每行一次写请求。Google 官方每用户每项目每分钟约60次读/60次写的额度下，代码高频提交触发生产采集很容易超限。
- **独立于 Sheet 的健康检查**：两小时一次的 `radar-watchdog.yml` 首先调用 `github_run_health.py` 检查最后一次**定时** CCU/每日研究的 GitHub Actions 状态与新鲜度；不因旧开发 push 失败持续误报。然后再执行 `radar_v12.py health` 记录中文「运行告警」，即使 Google Sheet 429，GitHub Job 仍会显示失败。GitHub 是否发送邮件/推送取决于账号通知设置，不等同于 ChatGPT 条件告警。
- **数据语义边界**：Steam Index API 的 `data.current` 与 `points[-1].value` 可能不同；`meta.generatedAt` 和历史 `last_point.at` 存在于「CCU原始采样」原始响应摘要中，不能把最近历史点时间擅自视为 `data.current` 的精确观测时间。D1/D7/D30 按实际已验证多次采样做有时间容差的比较，缺历史不计算；待进一步将生成时间/观测时间拆成独立列后才能称严格时间对齐。
- **验收要点**：`radar-ci.yml` 成功只证明离线代码检查通过，不代表生产采集成功；需在下一轮真正 `schedule` 或 `workflow_dispatch` 后核实三个生产 Workflow、中文「运行日志」、实际 CCU/评论行数和「黑马后验评估」写入，以及无新的 Google Sheets 429。不得把“没有写新增行（正常去重）”当作失败。
- 此整改不增加 ChatGPT 定时任务；保持每天09:30正式日报一个活跃任务。

## V1.3 审核队列与正式入库（2026-10-11）

- 取数层发现的 AppID 进入中文「新作候选」，从不直接晋级。候选审核栏保留 `官方核验依据 / 最近核验时间 / 人工复核优先级`，原始来源、标签和最近发现时间均保留。
- 初筛排队分为 P0-优先、P1-关注、P2-观察、P3-排除；**此优先级仅决定审核顺序，不代表雷达评分或游戏质量。** 仅基于 Steam 官方分区及 Indie 标签的初筛不能证明游戏为独立制作。
- 必须核验 Steam 商店官方页面的 AppID/类型/发行日期/开发与发行主体/机制，再按 AppID 去重写入「游戏库」「重点观察」，按 AppID+玩法原子去重维护「玩法原子」。首次示范核验加入 Big Walk（成熟合作机制参照）和 On Hold - Call Center Simulator（小样本职业模拟）；其它状态保持候选或排除，未核验不可当作正式发现。
- 显著 AAA/大型商业 IP、工具软件不得进入独立游戏库，留在候选池并标记「排除」，不要删除来源审计轨迹。存在来源/发布时间冲突的候选用「待复核」处理。
- 2026-10-11 首轮 Steam US/CN 精选分区发现 60 个 AppID，新增49条候选；其中已完成少量官方页面核验，不把全部49条称为独立游戏，也不把高 CCU/静态累计评论推断为跨日增长。
- 新入库对象在后续 08:20 评论采样和六小时 CCU 采样自动并入 Watchlist，只有严格同 AppID、口径、时间匹配的历史才计算增长。不能用未发行母游戏的 Demo CCU 填母游戏。
- 「使用说明」D18:E21 显示动态候选待审核数、已入库数、排除数和最近核验时间。正常采样仍静默，只有新严重失败才由已配置的条件告警提醒。

## V1.2 新作候选、评论口碑与告警

- 每天北京时间03:17、05:47、07:17由 `.github/workflows/radar-v12.yml` 按缺失任务自动运行，支持手动触发；GitHub 定时触发可能延迟。
- `radar_v12.py discover` 低频请求 Steam 官方 `/api/featuredcategories/` 美/中区的新发行、即将推出、畅销分区；合并AppID、最多每轮进一步核验30个详情，只增加/刷新中文「新作候选」候选池，不未经人工/日报来源核验自动转为游戏库及重点观察。这不是Steam全商店扫描。
- `radar_v12.py reviews` 读取「重点观察」「游戏库」获取正式版或明确映射的Demo的AppID；每天采样Steam官方 `/appreviews/{appid}`，固定 `filter=updated; language=all/schinese; review_type=all; purchase_type=all; filter_offtopic_activity=0`；中文「评论采样」按日期+AppID+语言+口径去重。
- 只有同AppID、口径、实测时间可比才计算评论24小时增量及7日/30日基准。首次样本不制造增长指标；简中与非简中好评率可在相同采样日用全语言减简中推导。生成中文「评论增速」并兼容当日旧行的更新。
- `radar_v12.py health` 在每日工作流及每6小时CCU流程后检查最近成功采样、有效样本量、发现及评论任务失败，记录中文「运行告警」；正常检查静默。首次演示及重跑应当查「运行日志」判定真实行数，不把0条新写入当失败（当天已有有效样本可复用）。
- `tests/test_v12.py` 不需要密钥，覆盖日期、字段解析、评论采样对照口径和Steam响应计数一致性。
- ChatGPT每天09:30日报消费候选与可信数据且仅写 Sheet；每2小时的健康巡检已迁移到 GitHub Actions，不再占用第2个 ChatGPT 定时任务。


长期 Google Sheet 已切换为中文工作表名称和中文表头。采集脚本通过 sheet_schema.py 兼容中文展示字段与旧英文代码字段；不要直接把中文表头改回英文。主要工作表：游戏库、重点观察、CCU原始采样、CCU可信样本、CCU增长趋势、运行日志。

数据处理：GitHub Actions 每约6小时采样，先解析 Steam Index 的 data.current 并校验新鲜度，失败则使用 Steam 官方当前玩家接口。原始数据落入 CCU原始采样；仅 VERIFIED 等合法数据进入 CCU可信样本，后者支持 CCU增长趋势。RECONSTRUCTED 与 CCU历史存档不得用于正式增长计算。

保留技术ID：AppID、CCU、D1/D7/D30。GitHub Secrets 不得写入 Google Sheet、仓库或对话。

---

# Steam Indie Radar - CCU Collector

Scheduled data collection with GitHub Actions. Google Sheets is the durable data store. No Render service or credit card is required.

## Schedule and verification

- Workflow: .github/workflows/ccu-sampler.yml
- Runs on a six-hour UTC cron: 00:00, 06:00, 12:00 and 18:00 UTC (08:00, 14:00, 20:00 and 02:00 Beijing time). GitHub may delay scheduled runs.
- Actions > CCU Sampler > Run workflow permits a manual test.
- Collector or workflow changes trigger offline CI tests only, not a production collection. Real production collection runs on schedule or manual workflow_dispatch; concurrency guards against overlap.
- Production check: verify Run_Log, CCU_Samples, CCU_Validated and CCU_Trend. An Action exit code alone does not prove that CCU values were obtained.

## Required GitHub Actions repository secrets

- STEAM_INDEX_API_KEY - Steam Index API Bearer key
- GOOGLE_SERVICE_ACCOUNT_JSON - complete service-account JSON
- GOOGLE_SHEET_ID - target Google spreadsheet ID

The Google Sheet must grant the service account Editor permission. Never store a key in Git, the Sheet, run logs or chat.

## Data pipeline

1. Read Watchlist and Games. Use CCU_Target_AppID and CCU_Target_Type to distinguish parent games from their demo/playtest Steam AppIDs.
2. Call the Steam Index 7-day players endpoint; extract the nested data.current value. Check API generation time and the age of the last observed data point.
3. If Steam Index has no eligible current value, fall back to the Steam official GetNumberOfCurrentPlayers endpoint.
4. Append schema-checked observations and statuses to CCU_Samples. Never fill a missing value with 0.
5. Rebuild CCU_Validated from verifiably fresh, numerically valid samples only. The generated table is idempotent.
6. Rebuild CCU_Trend for D1, D7 and D30 only when matching older verified samples exist within the sampling-time tolerance.
7. Log counts and failures in Run_Log. The ChatGPT daily radar reads CCU_Validated and CCU_Trend but does not perform duplicate CCU sampling.

CCU_Legacy contains prior mixed-format observations. Reconstructed previous Steam Index results remain marked RECONSTRUCTED / HISTORICAL_ONLY and are never treated as verified daily growth.

Attribution: Data from Steam Index when the Source field identifies Steam Index.

For exact headers and data quality definitions, see ccu_schema.md.
