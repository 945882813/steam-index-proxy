/**
 * Steam 雷达 GitHub Actions 独立保底调度（Google Apps Script V8）
 *
 * 绑定到现有 Steam 雷达 Google Sheet 的「扩展程序 → Apps Script」中。
 * 最小权限：GitHub fine-grained token 仅授权此仓库 Actions: Read and write。
 * 私密令牌只放 Apps Script → 项目设置 → 脚本属性，切勿填到 Sheet 单元格。
 *
 * 运行 setupRadarBackup() 一次创建 10 分钟时间触发器。
 * 在北京时间 06:30-09:05 内，若今日三项每日采集尚未完成且 GitHub
 * 没有在排队/执行的每日采集，则最多每 90 分钟调度一次原有工作流。
 * 时间触发器不保证绝对准时，也不会修改原 Google Sheet 的业务数据。
 */
const RADAR_BACKUP = Object.freeze({
  tz: 'Asia/Shanghai',
  workflow: 'radar-v12.yml',
  minMinute: 6 * 60 + 30,
  maxMinute: 9 * 60 + 5,
  cooldownMinutes: 90,
  requiredTasks: [
    '新作候选发现',
    '评论累计采样与增速',
    '黑马预测后验评估'
  ]
});

function setupRadarBackup() {
  const props = PropertiesService.getScriptProperties();
  ['STEAM_RADAR_SHEET_ID', 'STEAM_RADAR_GITHUB_TOKEN', 'STEAM_RADAR_REPO'].forEach(function(key) {
    if (!props.getProperty(key)) throw new Error('脚本属性缺失：' + key);
  });
  SpreadsheetApp.openById(props.getProperty('STEAM_RADAR_SHEET_ID')).getSheetByName('运行日志').getLastRow();
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'steamRadarBackupTick') ScriptApp.deleteTrigger(trigger);
  });
  ScriptApp.newTrigger('steamRadarBackupTick').timeBased().everyMinutes(10).create();
  console.log('安装完成：每10分钟检查一次；仅北京时间06:30-09:05触发补采。');
}

function inspectSteamRadarBackup() {
  const props = PropertiesService.getScriptProperties();
  const now = new Date();
  const date = Utilities.formatDate(now, RADAR_BACKUP.tz, 'yyyy-MM-dd');
  const ready = steamRadarTodayComplete_(props, date);
  const active = steamRadarGithubRuns_(props, date);
  const result = {date: date, ready: ready, github: active};
  console.log(JSON.stringify(result));
  return result; // 只读诊断，不派发工作流
}

function steamRadarBackupTick() {
  const localTime = Utilities.formatDate(new Date(), RADAR_BACKUP.tz, 'HH:mm');
  const hhmm = localTime.split(':').map(Number);
  const minute = hhmm[0] * 60 + hhmm[1];
  if (minute < RADAR_BACKUP.minMinute || minute > RADAR_BACKUP.maxMinute) return;

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return;
  try {
    const props = PropertiesService.getScriptProperties();
    const now = new Date();
    const date = Utilities.formatDate(now, RADAR_BACKUP.tz, 'yyyy-MM-dd');
    const last = Number(props.getProperty('RADAR_BACKUP_LAST_DISPATCH_MS') || '0');
    const elapsed = now.getTime() - last;
    if (last > 0 && elapsed >= 0 && elapsed < RADAR_BACKUP.cooldownMinutes * 60000) {
      console.log('本轮跳过：前次补采尚在冷却期');
      return;
    }

    if (steamRadarTodayComplete_(props, date)) {
      console.log('本轮跳过：今天发现、评论和后验已齐全');
      return;
    }

    const github = steamRadarGithubRuns_(props, date);
    if (github.running) {
      console.log('本轮跳过：GitHub采集正在排队或执行');
      return;
    }

    // GitHub曾报成功但Sheet输出仍不完整，允许补采。真正的日内幂等性
    // 由 daily_recovery.py 根据实际记录逐模块判断。
    const repo = props.getProperty('STEAM_RADAR_REPO');
    const result = steamRadarRequest_(props,
      'https://api.github.com/repos/' + repo +
      '/actions/workflows/' + RADAR_BACKUP.workflow + '/dispatches',
      'post', {ref: 'main'});
    if (result.status !== 204 && result.status !== 200) {
      throw new Error('GitHub补采派发失败：HTTP ' + result.status + ' ' + result.body.slice(0, 300));
    }
    props.setProperty('RADAR_BACKUP_LAST_DISPATCH_MS', String(Date.now()));
    console.log('补采已派发：' + date + '；GitHub工作流请以实际运行结果验收');
  } finally {
    lock.releaseLock();
  }
}

function steamRadarTodayComplete_(props, today) {
  const book = SpreadsheetApp.openById(props.getProperty('STEAM_RADAR_SHEET_ID'));
  const sheet = book.getSheetByName('运行日志');
  if (!sheet) throw new Error('缺少「运行日志」工作表');
  const last = sheet.getLastRow();
  if (last < 2) return false;
  const start = Math.max(2, last - 499);
  const data = sheet.getRange(start, 1, last - start + 1, 3).getValues();
  const done = {};
  data.forEach(function(row) {
    const time = row[0] instanceof Date
      ? Utilities.formatDate(row[0], RADAR_BACKUP.tz, 'yyyy-MM-dd')
      : String(row[0]).slice(0, 10);
    if (time === today && String(row[2]).trim() === 'OK') done[String(row[1]).trim()] = true;
  });
  return RADAR_BACKUP.requiredTasks.every(function(task) { return done[task] === true; });
}

function steamRadarGithubRuns_(props, today) {
  const repo = props.getProperty('STEAM_RADAR_REPO');
  const url = 'https://api.github.com/repos/' + repo +
    '/actions/workflows/' + RADAR_BACKUP.workflow + '/runs?per_page=30';
  const r = steamRadarRequest_(props, url, 'get');
  if (r.status !== 200) throw new Error('读取 GitHub 运行结果失败：HTTP ' + r.status);
  const payload = JSON.parse(r.body);
  let running = false;
  let successful = false;
  let latest = '';
  (payload.workflow_runs || []).forEach(function(run) {
    if (run.event !== 'schedule' && run.event !== 'workflow_dispatch') return;
    // Actions时间戳为UTC，必须转换为北京时间日历日。
    const day = Utilities.formatDate(new Date(run.created_at), RADAR_BACKUP.tz, 'yyyy-MM-dd');
    if (day !== today) return;
    if (!latest || String(run.created_at) > latest) latest = String(run.created_at);
    if (['queued', 'in_progress', 'waiting', 'pending', 'requested'].indexOf(run.status) >= 0) running = true;
    if (run.conclusion === 'success') successful = true;
  });
  return {running: running, successful: successful, lastRunUtc: latest};
}

function steamRadarRequest_(props, url, method, jsonBody) {
  const token = props.getProperty('STEAM_RADAR_GITHUB_TOKEN');
  const options = {
    method: method,
    headers: {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'steam-radar-sheets-backup'
    },
    muteHttpExceptions: true
  };
  if (jsonBody !== undefined) {
    options.contentType = 'application/json';
    options.payload = JSON.stringify(jsonBody);
  }
  const r = UrlFetchApp.fetch(url, options);
  return {status: r.getResponseCode(), body: r.getContentText()};
}
