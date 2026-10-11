# Steam 独立游戏雷达｜采集系统

## V1.3 审核队列与正式入库（2026-10-11）

- 取数层发现的 AppID 进入中文「新作候选」，从不直接晋级。候选审核栏保留 `官方核验依据 / 最近核验时间 / 人工复核优先级`，原始来源、标签和最近发现时间均保留。
- 初筛排队分为 P0-优先、P1-关注、P2-观察、P3-排除；**此优先级仅决定审核顺序，不代表雷达评分或游戏质量。** 仅基于 Steam 官方分区及 Indie 标签的初筛不能证明游戏为独立制作。
- 必须核验 Steam 商店官方页面的 AppID/类型/发行日期/开发与发行主体/机制，再按 AppID 去重写入「游戏库」「重点观察」，按 AppID+玩法原子去重维护「玩法原子」。首次示范核验加入 Big Walk（成熟合作机制参照）和 On Hold - Call Center Simulator（小样本职业模拟）；其它状态保持候选或排除，未核验不可当作正式发现。
- 显著 AAA/大型商业 IP、工具软件不得进入独立游戏库，留在候选池并标记「排除」，不要删除来源审计轨迹。存在来源/发布时间冲突的候选用「待复核」处理。
- 2026-10-11 首轮 Steam US/CN 精选分区发现 60 个 AppID，新增49条候选；其中已完成少量官方页面核验，不把全部49条称为独立游戏，也不把高 CCU/静态累计评论推断为跨日增长。
- 新入库对象在后续 08:20 评论采样和六小时 CCU 采样自动并入 Watchlist，只有严格同 AppID、口径、时间匹配的历史才计算增长。不能用未发行母游戏的 Demo CCU 填母游戏。
- 「使用说明」D18:E21 显示动态候选待审核数、已入库数、排除数和最近核验时间。正常采样仍静默，只有新严重失败才由已配置的条件告警提醒。

## V1.2 新作候选、评论口碑与告警

- 每天北京时间约08:20由 `.github/workflows/radar-v12.yml` 自动运行，支持手动触发；GitHub 定时触发可能延迟。
- `radar_v12.py discover` 低频请求 Steam 官方 `/api/featuredcategories/` 美/中区的新发行、即将推出、畅销分区；合并AppID、最多每轮进一步核验30个详情，只增加/刷新中文「新作候选」候选池，不未经人工/日报来源核验自动转为游戏库及重点观察。这不是Steam全商店扫描。
- `radar_v12.py reviews` 读取「重点观察」「游戏库」获取正式版或明确映射的Demo的AppID；每天采样Steam官方 `/appreviews/{appid}`，固定 `filter=updated; language=all/schinese; review_type=all; purchase_type=all; filter_offtopic_activity=0`；中文「评论采样」按日期+AppID+语言+口径去重。
- 只有同AppID、口径、实测时间可比才计算评论24小时增量及7日/30日基准。首次样本不制造增长指标；简中与非简中好评率可在相同采样日用全语言减简中推导。生成中文「评论增速」并兼容当日旧行的更新。
- `radar_v12.py health` 在每日工作流及每6小时CCU流程后检查最近成功采样、有效样本量、发现及评论任务失败，记录中文「运行告警」；正常检查静默。首次演示及重跑应当查「运行日志」判定真实行数，不把0条新写入当失败（当天已有有效样本可复用）。
- `tests/test_v12.py` 不需要密钥，覆盖日期、字段解析、评论采样对照口径和Steam响应计数一致性。
- ChatGPT原有每日09:30日报先审核「新作候选」，再从「评论采样」「评论增速」消费新的统一口径数据；仅可信数据可用于趋势。异常才通过独立2小时条件告警通知，平常日报仅写Sheet。


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
- Collector or workflow changes also trigger a run on main; concurrency protects against overlap.
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
