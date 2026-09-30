#!/usr/bin/env node
/* 简报交互自检（真实浏览器）
 *
 * 为什么需要它：Edge 无头模式不做合成帧、不派发 IntersectionObserver，甚至不做 layout
 * （getBoundingClientRect 全为 0），所以 --dump-dom 只能验结构、验不了交互。
 * 2026-09-30 就是靠这个脚本抓到「同一张卡两份 DOM 共用一个键、隐藏副本把停留计时器
 * 清零，导致自动已读永不触发」的 bug —— 光看结构完全正常。
 *
 * 依赖：playwright-core + 本地已下载的 Chromium（缺任一则以退出码 2 跳过，不算失败）。
 * 用法：node scripts/check_ui.js
 *       node scripts/check_ui.js --html output/手办情报-2026-09-30.html
 */

const fs = require('fs');
const path = require('path');

const SKILL = path.dirname(__dirname);
const OUTPUT = path.join(SKILL, 'output');

function arg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
}
function latest(prefix, ext) {
  const files = fs.readdirSync(OUTPUT)
    .filter((f) => f.startsWith(prefix) && f.endsWith(ext) &&
      !f.includes('总览'))
    .sort();
  return files.length ? path.join(OUTPUT, files[files.length - 1]) : null;
}
const asUrl = (p) => 'file:///' + p.replace(/\\/g, '/') + '?probe=1';

const digestPath = arg('--html') || latest('手办情报-', '.html');
const indexPath = arg('--index') || path.join(OUTPUT, '手办情报-总览.html');

let chromium;
try {
  chromium = require('playwright-core').chromium;
} catch (e) {
  console.log('SKIP: 找不到 playwright-core，跳过交互自检（结构自检请另跑 Edge --dump-dom）');
  process.exit(2);
}

/* playwright-core 只认自己那一版浏览器（版本号差一位就报 "Executable doesn't exist"），
 * 但机器上往往已经装了别的版本。这里主动去缓存目录里挑一个能用的完整版 Chromium。 */
function findCachedChromium() {
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    path.join(process.env.LOCALAPPDATA || '', 'ms-playwright'),
    path.join(process.env.HOME || '', '.cache', 'ms-playwright'),
  ].filter(Boolean);
  const tails = [
    ['chrome-win64', 'chrome.exe'], ['chrome-win', 'chrome.exe'],
    ['chrome-linux', 'chrome'], ['chrome-mac', 'Chromium.app/Contents/MacOS/Chromium'],
  ];
  for (const root of roots) {
    let dirs = [];
    try { dirs = fs.readdirSync(root).filter((d) => d.startsWith('chromium-')).sort().reverse(); }
    catch (e) { continue; }
    for (const d of dirs) {
      for (const t of tails) {
        const p = path.join(root, d, ...t);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return null;
}

async function launch() {
  try {
    return await chromium.launch({ headless: true });
  } catch (e) {
    const exe = findCachedChromium();
    if (!exe) throw e;
    console.log('（切换本地缓存的 Chromium：' + exe + '）');
    return await chromium.launch({ headless: true, executablePath: exe });
  }
}

const fails = [];
const ok = (cond, label, extra) => {
  console.log((cond ? '  ✅ ' : '  ❌ ') + label + (extra ? ' ｜ ' + extra : ''));
  if (!cond) fails.push(label);
};

(async () => {
  const browser = await launch();

  // ---------- 单日简报：未读体系 ----------
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 1100 } })).newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push(e.message));
  await page.goto(asUrl(digestPath));
  await page.waitForTimeout(900);

  const probeOf = async () => {
    const t = (await page.textContent('#probe')) || '';
    const m = t.match(/未读=(\d+)\/首现=(\d+)\s+已读键=(\d+)/);
    return m ? { unread: +m[1], total: +m[2], keys: +m[3] } : null;
  };
  let p0 = await probeOf();

  console.log('单日简报：' + path.basename(digestPath));
  ok(!!p0, '未读探针可读', p0 ? JSON.stringify(p0) : '无');
  ok(await page.locator('#unreadbar').count() === 1, '未读操作条已渲染');
  ok((await page.locator('.nbadge').count()) > 0, '存在未读徽章');
  ok(await page.locator('#un-pill').count() === 1, '顶栏未读胶囊已渲染');

  await page.waitForTimeout(4200);
  const p1 = await probeOf();
  ok(p1 && p1.keys > 0, '首屏停留即自动标记已读', p1 ? `已读键 ${p1.keys}` : '无');
  ok(p1 && p1.unread < p0.unread, '未读计数随之下降', p1 ? `${p0.unread} → ${p1.unread}` : '无');

  const readCards = await page.locator('.card.read').count();
  ok(readCards >= 2, '两份 DOM 副本同步变已读（应为偶数）', '已读卡=' + readCards);

  const before = await page.textContent('#count');
  await page.click('#un-toggle');
  await page.waitForTimeout(400);
  const after = await page.textContent('#count');
  ok(before !== after, '「只看未读」筛选生效', before + ' → ' + after);
  await page.click('#un-toggle');
  await page.waitForTimeout(300);

  await page.reload();
  await page.waitForTimeout(1400);
  const p2 = await probeOf();
  ok(p2 && p2.keys >= p1.keys, '刷新后已读状态保留', p2 ? `已读键 ${p2.keys}` : '无');

  const texts = await page.evaluate(() =>
    [].slice.call(document.querySelectorAll('.nbadge')).map((b) => b.textContent));
  const bad = texts.filter((t) => t !== '🆕 未读' && t !== '✓ 已读');
  ok(bad.length === 0, '徽章文案只有未读/已读两态', bad.slice(0, 3).join(','));

  await page.click('#un-all');
  await page.waitForTimeout(700);
  const p3 = await probeOf();
  ok(p3 && p3.unread === 0, '「全部标为已读」清零未读', p3 ? JSON.stringify(p3) : '无');
  ok(await page.evaluate(() =>
    document.getElementById('unreadbar').classList.contains('done')), '清零后条带转为完成态');

  ok(errs.length === 0, '页面无 JS 异常', errs.slice(0, 2).join(' | '));
  await page.close();

  // ---------- 总览页：不能被未读模块影响 ----------
  if (fs.existsSync(indexPath)) {
    const ip = await (await browser.newContext({ viewport: { width: 1400, height: 1100 } })).newPage();
    const ierr = [];
    ip.on('pageerror', (e) => ierr.push(e.message));
    await ip.goto('file:///' + indexPath.replace(/\\/g, '/'));
    await ip.waitForTimeout(1500);
    console.log('\n总览页：' + path.basename(indexPath));
    ok(await ip.locator('#unreadbar').count() === 0, '总览页不出现未读组件（模块自动停用）');
    ok(await ip.locator('.nbadge').count() === 0, '总览页不带未读徽章');
    const cnt = (await ip.textContent('#count')) || '';
    ok(/显示\s*\d+\s*\/\s*\d+/.test(cnt), '总览页计数正常', cnt.trim());
    ok(ierr.length === 0, '总览页无 JS 异常', ierr.slice(0, 2).join(' | '));
    await ip.close();
  }

  await browser.close();
  console.log(fails.length ? `\n结果：${fails.length} 项未通过` : '\n结果：全部通过');
  process.exit(fails.length ? 1 : 0);
})().catch((e) => {
  console.error('自检异常：' + e.message);
  process.exit(1);
});
