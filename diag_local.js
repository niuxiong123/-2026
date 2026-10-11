const { chromium } = require('C:/Users/76751/.workbuddy/binaries/node/workspace/node_modules/playwright-core');
const EXE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const BASE = 'http://localhost:8789/docs/index.html';
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  for (const q of ['#m1', '?role=owner#m1']) {
    const page = await browser.newPage({ viewport: { width: 1000, height: 1600 } });
    const errors = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message.slice(0, 200)));
    page.on('console', m => { if (m.type() === 'error') errors.push('console.error: ' + m.text().slice(0, 160)); });
    await page.goto(BASE + q, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(e => errors.push('goto: ' + e.message));
    await page.waitForTimeout(13000);
    const st = await page.evaluate(() => {
      const g = id => { const el = document.getElementById(id); return el ? (el.textContent || '').trim() : 'MISSING'; };
      const vis = id => { const el = document.getElementById(id); return el ? (el.hidden ? 'hidden' : 'visible') : 'MISSING'; };
      return {
        tempVal: g('tempVal'),
        bannerRegime: g('bannerRegime'), bannerPos: g('bannerPos'), bannerBand: g('bannerBand'),
        fhSig: g('fhSig'), fhPos: g('fhPos'), fhNote: g('fhNote').slice(0, 120),
        pBottom: g('pBottom'), pTop: g('pTop'),
        own_tempGauge_vis: vis('own_tempGauge'), own_tempVal: g('own_tempVal'),
        own_posCard_vis: vis('own_posCard'), own_posVal: g('own_posVal'),
        own_posDetail: g('own_posDetail').slice(0, 200),
        quadWhy: g('quadWhy').slice(0, 80),
        actionList: g('actionList').slice(0, 160),
        dataWarn: g('dataWarn'),
        statusFlags: (typeof statusFlags !== 'undefined') ? JSON.stringify(statusFlags) : 'n/a'
      };
    });
    console.log('===== 视图: ' + (q || '粉丝') + ' =====');
    console.log(JSON.stringify(st, null, 1));
    console.log('页面错误:', errors.length ? errors.slice(0, 10) : '无');
    await page.close();
  }
  await browser.close();
})();
