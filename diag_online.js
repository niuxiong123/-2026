// 运行时诊断：线上页面数据是否填充 + 控制台错误 + 失败请求
const { chromium } = require('C:/Users/76751/.workbuddy/binaries/node/workspace/node_modules/playwright-core');
const EXE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const BASE = 'https://niuxiong123.github.io/-2026/';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  for (const q of ['', '?role=owner']) {
    const page = await browser.newPage({ viewport: { width: 1000, height: 1400 } });
    const errors = [], failed = [];
    page.on('pageerror', e => errors.push('pageerror: ' + e.message.slice(0, 200)));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200)); });
    page.on('requestfailed', r => failed.push(r.url().slice(0, 100) + ' :: ' + (r.failure() ? r.failure().errorText : '')));
    await page.goto(BASE + q, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(e => errors.push('goto: ' + e.message));
    await page.waitForTimeout(12000); // 等数据链路完成/超时回退
    const st = await page.evaluate(() => {
      const g = id => { const el = document.getElementById(id); return el ? (el.textContent || '').trim().slice(0, 60) : 'MISSING'; };
      const vis = id => { const el = document.getElementById(id); return el ? (el.hidden ? 'hidden' : 'visible') : 'MISSING'; };
      return {
        title: document.title,
        tempVal: g('tempVal'), tempTag: g('tempTag'),
        bannerPos: g('bannerPos'), pBottom: g('pBottom'), pTop: g('pTop'),
        own_tempGauge_vis: vis('own_tempGauge'), own_tempVal: g('own_tempVal'), own_tempTag: g('own_tempTag'),
        own_posCard_vis: vis('own_posCard'), own_posVal: g('own_posVal'),
        own_posDetail: (document.getElementById('own_posDetail') || { textContent: '' }).textContent.trim().slice(0, 120),
        moneyBox_head: g('moneyBox').slice(0, 60),
        dataWarn: g('dataWarn'),
        statusFlags: (typeof statusFlags !== 'undefined') ? JSON.stringify(statusFlags) : 'n/a',
        hasSRV: (typeof SRV !== 'undefined') ? (SRV ? Object.keys(SRV) : 'null') : 'n/a'
      };
    });
    console.log('===== 视图: ' + (q || '粉丝') + ' =====');
    console.log(JSON.stringify(st, null, 1));
    console.log('页面错误:', errors.length ? errors.slice(0, 8) : '无');
    console.log('失败请求:', failed.length ? failed.slice(0, 10) : '无');
    await page.close();
  }
  await browser.close();
})();
