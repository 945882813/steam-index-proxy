// Offline independent Google Apps Script CCU fallback tests. No real token/API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('ops/steam_radar_backup.gs', 'utf8');

function setup(ageHours, activeRun = false) {
  const props = new Map([
    ['STEAM_RADAR_SHEET_ID', 'TEST_SHEET'], ['STEAM_RADAR_REPO', 'owner/repo'],
    ['STEAM_RADAR_GITHUB_TOKEN', 'MOCK_TOKEN']
  ]);
  const tickTime = new Date(Date.now() - ageHours * 3600000).toISOString();
  const raw = Array.from({length: 18}, (_, i) => [
    tickTime, String(4000000 + i), 'Game', 100, '7d', 'Steam Index',
    'https://public-api.steamidx.com', 'VERIFIED', 'OK'
  ]);
  const dispatched = [];
  const calls = [];
  const ctx = {
    console: {log(){}, error(){}},
    PropertiesService: {getScriptProperties: () => ({
      getProperty(key) { return props.get(key) || ''; },
      setProperty(key, value) {props.set(key, value);},
    })},
    LockService: {getScriptLock: () => ({tryLock: () => true, releaseLock(){}})},
    SpreadsheetApp: {openById: () => ({getSheetByName: () => ({
      getLastRow: () => 19,
      getRange: () => ({getValues: () => raw})
    })})},
    UrlFetchApp: {fetch: (url, options) => {
      calls.push({url, method: options.method});
      if (options.method === 'get') {
        return {
          getResponseCode: () => 200,
          getContentText: () => JSON.stringify({workflow_runs: activeRun ? [{
            event: 'schedule', status: 'in_progress',
            created_at: new Date().toISOString(),
          }] : []}),
        };
      }
      dispatched.push({url, payload: options.payload});
      return {getResponseCode: () => 204, getContentText: () => ''};
    }},
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return {ctx, props, calls, dispatched};
}

{
  const t = setup(4);
  t.ctx.steamRadarCCUBackupTick_();
  assert.equal(t.dispatched.length, 0, 'fresh validated CCU must not dispatch');
}
{
  const t = setup(10);
  t.ctx.steamRadarCCUBackupTick_();
  assert.equal(t.dispatched.length, 1, '10h-old full batch must request a new live CCU sample');
  assert.match(t.dispatched[0].url, /ccu-sampler\.yml\/dispatches$/);
  t.ctx.steamRadarCCUBackupTick_();
  assert.equal(t.dispatched.length, 1, 'same check cannot dispatch twice');
}
{
  const t = setup(10, true);
  t.ctx.steamRadarCCUBackupTick_();
  assert.equal(t.dispatched.length, 0, 'queued or running scheduled sampler blocks fallback');
}
{
  const t = setup(10);
  t.props.set('RADAR_CCU_LAST_DISPATCH_MS', String(Date.now() - 3600000));
  t.ctx.steamRadarCCUBackupTick_();
  assert.equal(t.dispatched.length, 0, 'CCU last dispatch 3h cooldown');
}
console.log('Apps Script independent CCU backup: 4 scenario tests passed');
