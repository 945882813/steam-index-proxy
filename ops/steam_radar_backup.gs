/**
 * Steam 雷达 GitHub Actions 独立保底调度（Google Apps Script V8）
 *
 * 绑定到现有 Steam 雷达 Google Sheet 的「扩展程序 → Apps Script」中。
 * 最小权限：GitHub fine-grained token 仅授权此仓库 Actions: Read and write。
 * 私密令牌只放 Apps Script → 项目设置 → 脚本属性，切勿填到 Sheet 单元格。
 *
 * 运行 setupRadarBackup() 一次创建 10 分钟时间触发器。
 * 每日研究只在北京时间 06:30-09:05 内兜底；CCU每30分钟检测一次，
 * 若上轮完整可信样本超过8小时仍未更新且无GitHub任务在运行，则派发
 * 新的实时CCU采样，绝不假装回填已错过时隙的历史观察值。
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
  // Also protect the six-hour CCU series independently of GitHub cron.
  // CCU audit is throttled to once per 30 minutes; an error must not block
  // the early-morning daily research fallback.
  try {
    steamRadarCCUBackupTick_();
  } catch (error) {
    console.error('CCU独立兜底检查失败：' + String(error).slice(0, 240));
  }
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

/**
 * 一次性真实联通性验收（需要用户在 Apps Script 中主动点击运行）。
 * 不受 06:30-09:05 时间窗口影响；触发已有幂等 daily_recovery.py。
 * 如当天候选和评论已完整，这两类采样应被跳过；若有更新的可信CCU，
 * 则黑马后验仍可能正常重算，这是允许的增量写入。
 * 防止重复测试：同一个北京时间自然日最多主动派发一次。
 */
function testIndependentRadarDispatchOnce() {
  const props = PropertiesService.getScriptProperties();
  const localDay = Utilities.formatDate(new Date(), RADAR_BACKUP.tz, 'yyyy-MM-dd');
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) throw new Error('另一轮保底调度正在运行，请核对执行记录');
  try {
    ['STEAM_RADAR_SHEET_ID', 'STEAM_RADAR_GITHUB_TOKEN', 'STEAM_RADAR_REPO'].forEach(function(key) {
      if (!props.getProperty(key)) throw new Error('脚本属性缺失：' + key);
    });
    if (props.getProperty('RADAR_BACKUP_TEST_DISPATCH_DAY') === localDay) {
      throw new Error('今天已经执行过一次真实派发验收；请到 GitHub Actions 查看该次运行');
    }
    const status = steamRadarGithubRuns_(props, localDay);
    if (status.running) throw new Error('GitHub 每日采集正在运行或排队，本次不再派发');
    const repo = props.getProperty('STEAM_RADAR_REPO');
    const url = 'https://api.github.com/repos/' + repo +
      '/actions/workflows/' + RADAR_BACKUP.workflow + '/dispatches';
    const result = steamRadarRequest_(props, url, 'post', {ref: 'main'});
    if (result.status !== 204) {
      throw new Error('独立派发未成功，GitHub HTTP ' + result.status +
        '；检查 Token 的 Actions 权限和仓库名称');
    }
    props.setProperty('RADAR_BACKUP_TEST_DISPATCH_DAY', localDay);
    // 测试同样计入正常冷却，避免随后的定时巡检紧接着发起第二次。
    props.setProperty('RADAR_BACKUP_LAST_DISPATCH_MS', String(Date.now()));
    console.log('独立派发验收：GitHub HTTP 204；工作流 radar-v12.yml 已接受触发请求。');
    console.log('仍需在 GitHub Actions 验证 workflow_dispatch 执行成功，及 Google Sheet 没有重复写入。');
  } finally {
    lock.releaseLock();
  }
}


/**
 * External-platform CCU backstop: every 30min assess the last full verified
 * batch, dispatch only if more than eight hours stale. It NEVER backfills the
 * missed historical slot's timestamps. GitHub concurrency and Python's
 * three-hour full-batch guard protect against overlapping submissions.
 */
function steamRadarCCUBackupTick_() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return;
  try {
    const props = PropertiesService.getScriptProperties();
    const now = Date.now();
    const lastCheck = Number(props.getProperty('RADAR_CCU_LAST_CHECK_MS') || '0');
    if (lastCheck > 0 && now >= lastCheck && now - lastCheck < 30 * 60000) return;
    props.setProperty('RADAR_CCU_LAST_CHECK_MS', String(now));

    const last = steamRadarLatestVerifiedCCU_(props);
    if (last !== null && now - last < 8 * 3600000) {
      console.log('CCU独立保底：可信批次距离现在不足8小时，不触发');
      return;
    }

    const lastDispatch = Number(props.getProperty('RADAR_CCU_LAST_DISPATCH_MS') || '0');
    if (lastDispatch > 0 && now >= lastDispatch && now - lastDispatch < 3 * 3600000) {
      console.log('CCU独立保底：距离最近一次派发不足3小时');
      return;
    }

    const gh = steamRadarRequest_(props,
      'https://api.github.com/repos/' + props.getProperty('STEAM_RADAR_REPO') +
      '/actions/workflows/ccu-sampler.yml/runs?per_page=30', 'get');
    if (gh.status !== 200) {
      throw new Error('读取CCU Actions状态失败 HTTP ' + gh.status);
    }
    const runs = JSON.parse(gh.body).workflow_runs || [];
    for (const run of runs) {
      if (['schedule', 'workflow_dispatch'].indexOf(run.event) === -1) continue;
      const ms = new Date(run.created_at).getTime();
      if (['queued', 'in_progress', 'waiting', 'pending', 'requested'].indexOf(run.status) >= 0) {
        console.log('CCU独立保底：GitHub已存在排队/执行任务');
        return;
      }
      if (Number.isFinite(ms) && now >= ms) {
        if (run.event === 'workflow_dispatch' && now - ms < 3 * 3600000) return;
        if (run.event === 'schedule' && now - ms < 45 * 60000) return;
      }
    }
    const response = steamRadarRequest_(props,
      'https://api.github.com/repos/' + props.getProperty('STEAM_RADAR_REPO') +
      '/actions/workflows/ccu-sampler.yml/dispatches', 'post', {ref: 'main'});
    if (response.status !== 204) {
      throw new Error('CCU workflow_dispatch 返回 HTTP ' + response.status);
    }
    props.setProperty('RADAR_CCU_LAST_DISPATCH_MS', String(now));
    console.log('CCU独立保底已派发：真实采集执行需进一步核对GitHub和Sheet');
  } finally {
    lock.releaseLock();
  }
}

function steamRadarLatestVerifiedCCU_(props) {
  const sheet = SpreadsheetApp.openById(props.getProperty('STEAM_RADAR_SHEET_ID'))
    .getSheetByName('CCU原始采样');
  if (!sheet) throw new Error('缺少「CCU原始采样」工作表');
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const start = Math.max(2, lastRow - 499);
  const rows = sheet.getRange(start, 1, lastRow - start + 1, 9).getValues();
  const groups = {};
  rows.forEach(function(row) {
    if (String(row[8]).trim().toUpperCase() !== 'OK') return;
    if (['VERIFIED', 'FRESH_FALLBACK'].indexOf(
      String(row[7]).trim().toUpperCase()) === -1) return;
    const appid = String(row[1]).trim();
    if (!/^\d+$/.test(appid)) return;
    const ms = row[0] instanceof Date ? row[0].getTime() : new Date(row[0]).getTime();
    if (!Number.isFinite(ms)) return;
    if (!groups[ms]) groups[ms] = {};
    groups[ms][appid] = true;
  });
  const complete = Object.keys(groups)
    .map(Number)
    .filter(ms => Object.keys(groups[ms]).length >= 12);
  return complete.length ? Math.max.apply(null, complete) : null;
}

function inspectSteamCCUBackup() {
  // Non-dispatching independent operational check.
  const props = PropertiesService.getScriptProperties();
  const t = steamRadarLatestVerifiedCCU_(props);
  const result = {
    latest_complete_batch: t === null ? null : new Date(t).toISOString(),
    age_hours: t === null ? null : Math.round((Date.now() - t) / 360000) / 10,
    fallback_stale_threshold_hours: 8
  };
  console.log(JSON.stringify(result));
  return result;
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
