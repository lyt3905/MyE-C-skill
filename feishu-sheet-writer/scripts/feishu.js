#!/usr/bin/env node
/**
 * feishu.js —— 飞书电子表格 / 多维表格 / 云空间 统一 CLI（零依赖，仅 Node 内置 fetch）。
 *
 * 凭据查找顺序：
 *   1) 环境变量 FEISHU_APP_ID + FEISHU_APP_SECRET
 *   2) 环境变量 FEISHU_CRED_FILE 指向的 json
 *   3) %USERPROFILE%\.dsh\feishu-app.json
 *   4) ./feishu/app.json （当前工作目录下）
 *   json 形如 {"app_id":"cli_xxx","app_secret":"xxx"}
 *
 * 常用：
 *   node feishu.js whoami
 *   node feishu.js wiki <wikiNodeToken>                     # wiki 链接 -> obj_token / obj_type
 *   node feishu.js sheets <spreadsheetToken>                # 子表 id + 标题 + resource_type
 *   node feishu.js read  <ssToken> 'sheetId!A1:H9' [--render ToString|Formula|FormattedValue]
 *   node feishu.js write <ssToken> 'sheetId!A4:H6' --data-file rows.json
 *   node feishu.js img   <ssToken> 'sheetId!I4:I4' pic.png pic.png
 *   node feishu.js export <ssToken> --out cur.xlsx
 *   node feishu.js import <xlsx> [--name 名字] [--parent <folderToken>]
 *   node feishu.js upload <file> [--name 名字] [--parent <folderToken>]
 *   node feishu.js share <token> <openId> [--type sheet|file] [--perm full_access]
 *   node feishu.js tables <baseAppToken> | fields | list | add | addmany | update
 *   node feishu.js raw <METHOD> <path> [--body-file f.json]
 *
 * ⚠️ Windows/PowerShell：内联 JSON 的双引号会被吞，一律用 --data-file / --body-file。
 */
'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const BASE = 'https://open.feishu.cn/open-apis';
const TIMEOUT_MS = 30_000;

/* ---------------------------------------------------------------- 凭据 & token */

function credCandidates() {
  return [
    process.env.FEISHU_CRED_FILE,
    path.join(process.env.USERPROFILE || os.homedir(), '.dsh', 'feishu-app.json'),
    path.join(process.cwd(), 'feishu', 'app.json'),
    path.join(__dirname, 'app.json'),
  ].filter(Boolean);
}

function loadCreds() {
  if (process.env.FEISHU_APP_ID && process.env.FEISHU_APP_SECRET) {
    return { app_id: process.env.FEISHU_APP_ID, app_secret: process.env.FEISHU_APP_SECRET, src: 'env' };
  }
  for (const p of credCandidates()) {
    try {
      const j = JSON.parse(fs.readFileSync(p, 'utf8'));
      if (j.app_id && j.app_secret) return { ...j, src: p };
    } catch {}
  }
  throw new Error(
    '缺少凭据：设 FEISHU_APP_ID / FEISHU_APP_SECRET，或写 %USERPROFILE%\\.dsh\\feishu-app.json ' +
      '{"app_id":"cli_xxx","app_secret":"xxx"}'
  );
}

function tokenCachePath(cred) {
  if (cred.src === 'env') return path.join(os.tmpdir(), 'feishu-token-cache.json');
  return path.join(path.dirname(cred.src), '.token.json');
}

async function getToken(force = false) {
  const cred = loadCreds();
  const cachePath = tokenCachePath(cred);
  if (!force) {
    try {
      const j = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
      if (j.app_id === cred.app_id && j.token && j.expire_at - 300_000 > Date.now()) return j.token;
    } catch {}
  }
  const res = await fetch(`${BASE}/auth/v3/tenant_access_token/internal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ app_id: cred.app_id, app_secret: cred.app_secret }),
  });
  const j = await res.json();
  if (j.code !== 0) throw new Error(`取 tenant_access_token 失败 code=${j.code} msg=${j.msg}`);
  try {
    fs.writeFileSync(
      cachePath,
      JSON.stringify({ app_id: cred.app_id, token: j.tenant_access_token, expire_at: Date.now() + (j.expire || 7200) * 1000 }),
      { mode: 0o600 }
    );
  } catch {}
  return j.tenant_access_token;
}

/* ---------------------------------------------------------------- HTTP */

async function api(method, urlPath, body, { raw = false, timeout = TIMEOUT_MS } = {}) {
  const token = await getToken();
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeout);
  let res;
  try {
    res = await fetch(`${BASE}${urlPath}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json; charset=utf-8' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ac.signal,
    });
  } finally {
    clearTimeout(timer);
  }
  if (raw) {
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return Buffer.from(await res.arrayBuffer());
  }
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`非 JSON 响应 HTTP ${res.status}: ${text.slice(0, 300)}`);
  }
  if (json.code !== 0) {
    const err = new Error(`飞书 API 错误 code=${json.code} msg=${json.msg}`);
    err.payload = json;
    err.hint = hintFor(json.code);
    throw err;
  }
  return json.data;
}

/** 常见错误码 -> 人话 */
function hintFor(code) {
  switch (code) {
    case 91403:
      return '文档级权限不足：把应用加成该文档的「可编辑」协作者（表格右上「分享/···」→ 添加文档应用）';
    case 99991672:
      return '应用缺 scope：开放平台「权限管理」开通对应权限，并「创建版本发布」才生效';
    case 131006:
      return '知识库权限不足：知识库「设置→成员管理」把应用加成可编辑/可管理';
    case 1254003:
      return 'WrongBaseToken：这个 token 不是多维表格 app_token（Wiki 节点要先用 wiki 命令反查 obj_token）';
    case 90204:
      return '参数/内容格式问题（写公式要 {"type":"formula","text":"=..."}；插图 name 要带 .png/.jpg 且图片不能有 alpha 通道）';
    case 91402:
      return 'NOTEXIST：token 不对，或目标对象类型不匹配（sheet vs bitable）';
    case 131002:
      return 'param err：请求体字段不对（建 wiki 节点需要 obj_type/obj_token/parent_node_token）';
    default:
      return '';
  }
}

/* ---------------------------------------------------------------- 参数解析 */

function args(argv) {
  const out = { _: [], opts: {} };
  const takesValue = new Set([
    '--data',
    '--body',
    '--data-file',
    '--body-file',
    '--render',
    '--view',
    '--limit',
    '--page-token',
    '--parent',
    '--name',
    '--out',
    '--type',
    '--perm',
  ]);
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (takesValue.has(a)) out.opts[a.slice(2)] = argv[++i];
    else if (a.startsWith('--')) out.opts[a.slice(2)] = true;
    else out._.push(a);
  }
  return out;
}

function payload(opts, inlineKey, fileKey, what) {
  if (opts[fileKey] !== undefined) {
    try {
      return JSON.parse(fs.readFileSync(opts[fileKey], 'utf8'));
    } catch (e) {
      throw new Error(`读取 ${what} 文件失败 (${opts[fileKey]}): ${e.message}`);
    }
  }
  if (opts[inlineKey] !== undefined) {
    try {
      return JSON.parse(opts[inlineKey]);
    } catch (e) {
      throw new Error(`${what} 不是合法 JSON: ${e.message}`);
    }
  }
  throw new Error(`缺少 ${what}：用 --${inlineKey} '<json>' 或 --${fileKey} <path>（PowerShell 建议后者）`);
}

const print = (o) => process.stdout.write(JSON.stringify(o, null, 2) + '\n');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------------------------------------------------------------- 异步任务轮询 */

async function pollImport(ticket) {
  for (let i = 0; i < 30; i++) {
    const d = await api('GET', `/drive/v1/import_tasks/${ticket}`);
    const r = d.result || {};
    if (r.job_status === 0) return r;
    if (r.job_status && r.job_status !== 1 && r.job_status !== 2) {
      throw new Error(`导入失败 job_status=${r.job_status} ${r.job_error_msg || ''}`);
    }
    await sleep(2000);
  }
  throw new Error('导入任务超时（>60s）');
}

async function pollExport(ticket, ssToken) {
  // 注意：导出任务的轮询必须带 ?token=<源文档 token>，否则报 field validation failed: token is required
  for (let i = 0; i < 30; i++) {
    const d = await api('GET', `/drive/v1/export_tasks/${ticket}?token=${encodeURIComponent(ssToken)}`);
    const r = d.result || {};
    if (r.job_status === 0) return r;
    if (r.job_status && r.job_status !== 1 && r.job_status !== 2) {
      throw new Error(`导出失败 job_status=${r.job_status} ${r.job_error_msg || ''}`);
    }
    await sleep(2000);
  }
  throw new Error('导出任务超时（>60s）');
}

/* ---------------------------------------------------------------- 主命令 */

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  if (!cmd || cmd === '-h' || cmd === '--help' || cmd === 'help') {
    const head = fs.readFileSync(__filename, 'utf8').split('\n');
    const from = head.findIndex((l) => l.includes('常用：'));
    console.log(head.slice(from, from + 18).join('\n'));
    return;
  }
  const { _, opts } = args(rest);

  switch (cmd) {
    /* --- 基础 --- */
    case 'whoami': {
      const cred = loadCreds();
      await getToken(true);
      print({ app_id: cred.app_id, cred_file: cred.src, token_ok: true });
      return;
    }
    case 'wiki': {
      const d = await api('GET', `/wiki/v2/spaces/get_node?token=${encodeURIComponent(_[0])}&obj_type=wiki`);
      print(d.node || d);
      return;
    }
    case 'raw': {
      const body = opts.body !== undefined || opts['body-file'] !== undefined ? payload(opts, 'body', 'body-file', '--body') : undefined;
      print(await api(_[0].toUpperCase(), _[1], body));
      return;
    }

    /* --- 电子表格 --- */
    case 'sheets': {
      const d = await api('GET', `/sheets/v3/spreadsheets/${_[0]}/sheets/query`);
      print((d.sheets || []).map((s) => ({
        sheet_id: s.sheet_id,
        title: s.title,
        resource_type: s.resource_type,
        rows: s.grid_properties && s.grid_properties.row_count,
        cols: s.grid_properties && s.grid_properties.column_count,
      })));
      return;
    }
    case 'read': {
      const [token, range] = _;
      const render = opts.render || 'ToString';
      const d = await api(
        'GET',
        `/sheets/v2/spreadsheets/${token}/values/${encodeURIComponent(range)}?valueRenderOption=${render}`
      );
      print(d.valueRange || d);
      return;
    }
    case 'write': {
      const [token, range] = _;
      const values = payload(opts, 'data', 'data-file', '--data');
      print(await api('PUT', `/sheets/v2/spreadsheets/${token}/values`, { valueRange: { range, values } }));
      return;
    }
    case 'append': {
      const [token, range] = _;
      const values = payload(opts, 'data', 'data-file', '--data');
      print(await api('POST', `/sheets/v2/spreadsheets/${token}/values_append`, { valueRange: { range, values } }));
      return;
    }
    case 'img': {
      const [token, range, imgPath, imgName] = _;
      if (!imgName) throw new Error('用法: img <ssToken> <range> <图片路径> <带扩展名的文件名，如 a.png>');
      const b64 = fs.readFileSync(path.resolve(imgPath)).toString('base64');
      print(
        await api('POST', `/sheets/v2/spreadsheets/${token}/values_image`, {
          range,
          image: b64,
          name: imgName,
        }, { timeout: 120_000 })
      );
      return;
    }
    case 'export': {
      const [token] = _;
      const d = await api('POST', '/drive/v1/export_tasks', {
        file_extension: 'xlsx',
        token,
        type: 'sheet',
      });
      const r = await pollExport(d.ticket, token);
      const out = opts.out || `export-${token.slice(0, 6)}.xlsx`;
      const buf = await api('GET', `/drive/v1/export_tasks/file/${r.file_token}/download`, undefined, { raw: true });
      fs.writeFileSync(out, buf);
      print({ saved: out, bytes: buf.length, file_token: r.file_token });
      return;
    }

    /* --- 云空间 --- */
    case 'upload': {
      const file = _[0];
      const abs = path.resolve(file);
      const buf = fs.readFileSync(abs);
      const name = opts.name || path.basename(abs);
      let parent = opts.parent;
      if (!parent) parent = (await api('GET', '/drive/explorer/v2/root_folder/meta')).token;
      const form = new FormData();
      form.append('file_name', name);
      form.append('parent_type', 'explorer');
      form.append('parent_node', parent);
      form.append('size', String(buf.length));
      form.append('file', new Blob([buf]), name);
      const res = await fetch(`${BASE}/drive/v1/files/upload_all`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${await getToken()}` },
        body: form,
      });
      const j = await res.json();
      if (j.code !== 0) throw new Error(`上传失败 code=${j.code} msg=${j.msg}`);
      print({ parent, ...j.data });
      return;
    }
    case 'import': {
      const file = _[0];
      const abs = path.resolve(file);
      const name = opts.name || path.basename(abs, path.extname(abs));
      let parent = opts.parent;
      if (!parent) parent = (await api('GET', '/drive/explorer/v2/root_folder/meta')).token;

      // 1) 先上传
      const buf = fs.readFileSync(abs);
      const form = new FormData();
      form.append('file_name', path.basename(abs));
      form.append('parent_type', 'explorer');
      form.append('parent_node', parent);
      form.append('size', String(buf.length));
      form.append('file', new Blob([buf]), path.basename(abs));
      const up = await fetch(`${BASE}/drive/v1/files/upload_all`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${await getToken()}` },
        body: form,
      }).then((r) => r.json());
      if (up.code !== 0) throw new Error(`上传失败 code=${up.code} msg=${up.msg}`);

      // 2) 转成原生电子表格
      const d = await api('POST', '/drive/v1/import_tasks', {
        file_extension: path.extname(abs).replace('.', ''),
        file_token: up.data.file_token,
        type: 'sheet',
        file_name: name,
        point: { mount_type: 1, mount_key: parent },
      });
      const r = await pollImport(d.ticket);
      print({ source_file_token: up.data.file_token, sheet_token: r.token, url: r.url });
      return;
    }
    case 'share': {
      const [token, openId] = _;
      const type = opts.type || 'sheet';
      print(
        await api('POST', `/drive/v1/permissions/${token}/members?type=${type}`, {
          member_type: 'openid',
          member_id: openId,
          perm: opts.perm || 'full_access',
        })
      );
      return;
    }

    /* --- 多维表格 --- */
    case 'tables': {
      const d = await api('GET', `/bitable/v1/apps/${_[0]}/tables?page_size=100`);
      print(d.items || d);
      return;
    }
    case 'fields': {
      const d = await api('GET', `/bitable/v1/apps/${_[0]}/tables/${_[1]}/fields?page_size=100`);
      print(d.items || d);
      return;
    }
    case 'list': {
      const qs = new URLSearchParams({ page_size: String(Math.min(Number(opts.limit || 100), 500)) });
      if (opts.view) qs.set('view_id', opts.view);
      if (opts['page-token']) qs.set('page_token', opts['page-token']);
      const d = await api('GET', `/bitable/v1/apps/${_[0]}/tables/${_[1]}/records?${qs}`);
      print({ has_more: d.has_more, page_token: d.page_token, items: d.items || [] });
      return;
    }
    case 'add': {
      const fields = payload(opts, 'data', 'data-file', '--data');
      print((await api('POST', `/bitable/v1/apps/${_[0]}/tables/${_[1]}/records`, { fields })).record);
      return;
    }
    case 'addmany': {
      const raw = payload(opts, 'data', 'data-file', '--data');
      const records = raw.map((r) => (r && r.fields ? r : { fields: r }));
      const d = await api('POST', `/bitable/v1/apps/${_[0]}/tables/${_[1]}/records/batch_create`, { records });
      print({ created: (d.records || []).length });
      return;
    }
    case 'update': {
      const fields = payload(opts, 'data', 'data-file', '--data');
      print((await api('PUT', `/bitable/v1/apps/${_[0]}/tables/${_[1]}/records/${_[2]}`, { fields })).record);
      return;
    }

    default:
      throw new Error(`未知命令: ${cmd}（node feishu.js help）`);
  }
}

main().catch((e) => {
  console.error('❌ ' + e.message);
  if (e.hint) console.error('💡 ' + e.hint);
  if (e.payload) console.error(JSON.stringify(e.payload, null, 2));
  process.exit(1);
});
