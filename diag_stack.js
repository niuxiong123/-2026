// 定位错误堆栈 + 404来源；支持对比本地不同版本（经本地HTTP服务）
const { chromium } = require('C:/Users/76751/.workbuddy/binaries/node/workspace/node_modules/playwright-core');
const EXE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const BASE = process.argv[2] || 'https://niuxiong123.github.io/-2026/';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1000, height: 1400 } });
  const errors = [], bad = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message + '\nSTACK: ' + (e.stack || '').slice(0, 900)));
  page.on('response', r => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.url().slice(0, 110)); });
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(e => errors.push('goto: ' + e.message));
  await page.waitForTimeout(10000);
  console.log('错误数:', errors.length, '| 4xx/5xx:', bad.length);
  errors.slice(0, 4).forEach(e => console.log('----\n' + e));
  bad.slice(0, 8).forEach(b => console.log('HTTP ' + b));
  await browser.close();
})();
