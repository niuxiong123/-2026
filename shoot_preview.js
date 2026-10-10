// 试运行：渲染 docs/index.html，校验粉丝/站主视图切换，并输出两张全页截图
const { chromium } = require('C:/Users/76751/.workbuddy/binaries/node/workspace/node_modules/playwright-core');

const URL = 'file:///C:/Users/76751/WorkBuddy/2026-10-07-18-42-47/repo_2026/docs/index.html';
const EXE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1000, height: 1400 } });
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));

  async function snap(suffix, q) {
    await page.goto(URL + q, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(e => errors.push('goto:' + e.message));
    await page.waitForTimeout(3500); // 等外部数据 fetch 失败回退基线 / 渲染完成
    const st = await page.evaluate(() => {
      const g = id => { const el = document.getElementById(id); return el ? (el.hidden === true ? 'hidden' : (el.style.display === 'none' ? 'display:none' : 'visible')) : 'MISSING'; };
      return {
        ownerView: g('ownerView'), toolsFold: g('toolsFold'), fundFold: g('fundFold'),
        ownerBadge: g('ownerBadge'), banner: g('actionBanner') || g('banner'),
        allocRows: document.querySelectorAll('#allocBody tr').length,
        histInOwnerHidden: (function(){ var t=document.getElementById('histTable'); if(!t) return 'MISSING'; var s=t.closest('section'); return s ? (s.hidden?'hidden':'visible') : 'NO-SECTION'; })(),
        navLinks: document.querySelectorAll('nav a, .nav a').length,
        title: document.title
      };
    });
    await page.screenshot({ path: 'C:/Users/76751/WorkBuddy/2026-10-07-18-42-47/preview_' + suffix + '.png', fullPage: true });
    console.log('[' + suffix + '] ' + JSON.stringify(st));
  }

  await snap('fan', '');
  await snap('owner', '?role=owner');
  console.log('JS errors: ' + (errors.length ? errors.join(' | ') : '无'));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
