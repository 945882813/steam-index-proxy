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
