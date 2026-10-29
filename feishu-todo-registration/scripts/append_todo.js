#!/usr/bin/env node
/**
 * append_todo.js — 往飞书「刘宇彤-测试 / 待办事项清单」追加一条待办
 *
 * 复用 feishu-sheet-writer 的 scripts/feishu.js 做鉴权与 API 调用（零依赖）。
 *
 * 用法：
 *   node append_todo.js --item "待办内容" [--priority P1] [--category 工作]
 *                       [--note "备注"] [--template "模板名"] [--progress 0]
 *                       [--due ""] [--image shot.png] [--row 12]
 *                       [--ss TOKEN] [--sheet bfe2ca] [--dry-run]
 *                       [--clear-row 12]
 *
 * 输出：一行 JSON {ok, row, image, verified}
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const DEFAULT_SS = 'HUo3sTcWShlZxMtVIkvc7hJ6nrg';
const DEFAULT_SHEET = 'bfe2ca';
const DEFAULT_CLI = path.resolve(__dirname, '..', '..', 'feishu-sheet-writer', 'scripts', 'feishu.js');
const NOTE_MAX = 2000;

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const key = a.slice(2);
    if (key === 'dry-run' || key === 'no-verify') { out[key] = true; continue; }
    const next = argv[i + 1];
    if (next === undefined || (next.startsWith('--') && next.length > 2)) {
      out[key] = true;
    } else {
      out[key] = next;
      i++;
    }
  }
  return out;
}

function cliPath() {
  return process.env.FEISHU_CLI || DEFAULT_CLI;
}

function runCli(args) {
  const cli = cliPath();
  if (!fs.existsSync(cli)) {
    throw new Error('找不到 feishu.js：' + cli + '（可用环境变量 FEISHU_CLI 指定）');
  }
  const r = spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) {
    const msg = (r.stderr || r.stdout || '').trim();
    throw new Error('feishu.js ' + args[0] + ' 失败: ' + msg.slice(0, 800));
  }
  return r.stdout;
}

function runCliJson(args) {
  const out = runCli(args);
  const start = out.indexOf('{');
  const startArr = out.indexOf('[');
  const from = start === -1 ? startArr : (startArr === -1 ? start : Math.min(start, startArr));
  if (from === -1) throw new Error('feishu.js 输出无法解析: ' + out.slice(0, 400));
  return JSON.parse(out.slice(from));
}

function colLetter(i) { return String.fromCharCode(65 + i); }

/** 同步 sleep（零依赖） */
function sleepMs(ms) {
  try {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
  } catch (_) {
    const end = Date.now() + ms;
    while (Date.now() < end) { /* busy wait */ }
  }
}

/** 读表，返回二维数组（从第 3 行开始） */
function readGrid(ss, sheet, lastRow) {
  const range = sheet + '!A3:J' + lastRow;
  const res = runCliJson(['read', ss, range, '--render', 'ToString']);
  return res.values || [];
}

/** C 列为空即空行；返回 1-based 行号 */
function findEmptyRow(grid, startRow) {
  for (let i = 0; i < grid.length; i++) {
    const rowNo = startRow + i;
    const c = grid[i] && grid[i][2];
    const isEmpty = c === null || c === undefined || String(c).trim() === '';
    if (isEmpty) return rowNo;
  }
  throw new Error('在读取范围内没找到空行，扩大 --last-row 或先看表');
}

/** 组装 A..J 一行：A=数字，B=公式，其余字符串；I 先置空，图片单独插 */
function rowValues(r, opt) {
  const item = String(opt.item || '').trim();
  if (!item) throw new Error('缺少 --item');
  const priority = String(opt.priority || 'P1').toUpperCase();
  const category = String(opt.category || '工作');
  const progress = Number(opt.progress === undefined || opt.progress === true ? 0 : opt.progress) || 0;
  let note = String(opt.note === true || opt.note === undefined ? '' : opt.note).trim();
  if (note.length > NOTE_MAX) note = note.slice(0, NOTE_MAX - 1) + '…';
  const due = String(opt.due === true || opt.due === undefined ? '' : opt.due);
  const template = String(opt.template === true || opt.template === undefined ? '' : opt.template);

  return [
    0,
    { type: 'formula', text: '=IF(C' + r + '="","",IF(A' + r + '=0,"未完成","已完成"))' },
    item,
    priority,
    category,
    progress,
    due,
    note,
    '',
    template,
  ];
}

function writeTmpJson(obj) {
  const p = path.join(os.tmpdir(), 'feishu_row_' + process.pid + '_' + Date.now() + '.json');
  fs.writeFileSync(p, JSON.stringify(obj), 'utf8');
  return p;
}

function findPython() {
  const cands = [];
  if (process.env.DSH_PYTHON) cands.push(process.env.DSH_PYTHON);
  if (process.env.PYTHON) cands.push(process.env.PYTHON);
  cands.push('python');
  cands.push('python3');
  for (const c of cands) {
    const r = spawnSync(c, ['-c', 'import PIL; print(1)'], { encoding: 'utf8' });
    if (r.status === 0) return c;
  }
  return null;
}

/** 转 RGB 去 alpha（飞书插图不接受 alpha） */
function toRgb(src) {
  const py = findPython();
  if (!py) {
    console.error('[warn] 没找到带 Pillow 的 python，直接上传原图（若带 alpha 会 90204）');
    return { path: src, converted: false };
  }
  const out = path.join(os.tmpdir(), 'feishu_img_' + process.pid + '_' + Date.now() + '.png');
  const code = 'from PIL import Image;Image.open(r"' + src + '").convert("RGB").save(r"' + out + '")';
  const r = spawnSync(py, ['-c', code], { encoding: 'utf8' });
  if (r.status !== 0) {
    console.error('[warn] 转 RGB 失败，直接上传原图: ' + (r.stderr || '').trim().slice(0, 300));
    return { path: src, converted: false };
  }
  const info = { path: out, converted: true };
  try {
    const probe = spawnSync(py, ['-c', 'from PIL import Image;print(Image.open(r"' + out + '").mode)'], { encoding: 'utf8' });
    info.mode = (probe.stdout || '').trim();
  } catch (_) { /* ignore */ }
  return info;
}

function clearRow(ss, sheet, row) {
  const blanks = [['', '', '', '', '', '', '', '', '', '']];
  const p = writeTmpJson(blanks);
  runCli(['write', ss, sheet + '!A' + row + ':J' + row, '--data-file', p]);
  fs.unlinkSync(p);
  const back = runCliJson(['read', ss, sheet + '!A' + row + ':J' + row, '--render', 'FormattedValue']);
  const vals = (back.values && back.values[0]) || [];
  const clean = vals.every(v => v === null || v === undefined || v === '');
  return { row, cleared: true, isClean: clean };
}

function main() {
  const opt = parseArgs(process.argv.slice(2));
  const ss = String(opt.ss || process.env.FEISHU_SS || DEFAULT_SS);
  const sheet = String(opt.sheet || DEFAULT_SHEET);

  if (opt['clear-row']) {
    const row = Number(opt['clear-row']);
    if (!row) throw new Error('--clear-row 需要行号');
    const res = clearRow(ss, sheet, row);
    console.log(JSON.stringify({ ok: true, ...res }, null, 2));
    return;
  }

  const lastRow = Number(opt['last-row'] || 400);
  let row;
  if (opt.row) {
    row = Number(opt.row);
  } else {
    const grid = readGrid(ss, sheet, lastRow);
    row = findEmptyRow(grid, 3);
  }

  const values = rowValues(row, opt);
  const payload = [values];

  if (opt['dry-run']) {
    console.log(JSON.stringify({ ok: true, dryRun: true, row, payload }, null, 2));
    return;
  }

  const p = writeTmpJson(payload);
  runCli(['write', ss, sheet + '!A' + row + ':J' + row, '--data-file', p]);
  fs.unlinkSync(p);

  let image = null;
  if (opt.image && opt.image !== true) {
    const src = path.resolve(String(opt.image));
    if (!fs.existsSync(src)) throw new Error('图片不存在: ' + src);
    const conv = toRgb(src);
    runCli(['img', ss, sheet + '!I' + row + ':I' + row, conv.path, conv.path]);
    image = { source: src, uploaded: conv.path, mode: conv.mode || null, converted: conv.converted };
  }

  let verified = null;
  if (!opt['no-verify']) {
    // 刚插完图飞书有最终一致性延迟，读回可能还是空，需轮询几次
    const attempts = image ? 6 : 1;
    for (let i = 0; i < attempts; i++) {
      const back = runCliJson(['read', ss, sheet + '!A' + row + ':J' + row, '--render', 'FormattedValue']);
      const v = (back.values && back.values[0]) || [];
      // FormattedValue 把图片单元格渲染成对象（不是数组），ToString 返回 [{id,type}]，两种形状都要认
      const cell = v[8];
      let imgType = null;
      if (Array.isArray(cell)) imgType = cell[0] && cell[0].type ? cell[0].type : null;
      else if (cell && typeof cell === 'object') imgType = cell.type || 'embed-image';
      verified = {
        item: v[2],
        status: v[1],
        priority: v[3],
        category: v[4],
        image: imgType,
        ok: v[2] === values[2] && (v[1] === '未完成' || v[1] === '已完成'),
      };
      if (image) verified.ok = verified.ok && verified.image === 'embed-image';
      if (verified.ok) break;
      if (i < attempts - 1) sleepMs(1500);
    }
  }

  console.log(JSON.stringify({ ok: !!(verified && verified.ok), row, image, verified }, null, 2));
  if (verified && !verified.ok) process.exitCode = 1;
}

try {
  main();
} catch (e) {
  console.log(JSON.stringify({ ok: false, error: String(e.message || e) }, null, 2));
  process.exitCode = 1;
}
