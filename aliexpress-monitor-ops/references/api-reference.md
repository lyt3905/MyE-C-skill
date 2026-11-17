# AliExpressMonitor API 参考

服务默认 `http://127.0.0.1:18765`。代码在 `D:\GitHub\AliExpressMonitor\alimonitor\`。

## 鉴权

### 本地写鉴权（默认，`alm.py` 用这个）
`require_local_write`（`alimonitor\web\security.py:53-65`）对写接口校验：
- `Host: 127.0.0.1:18765`
- `Origin: http://127.0.0.1:18765`
- `Content-Type: application/json`
- `x-csrf-token == app.state.csrf_token`

CSRF token 从 `GET /` 返回 HTML 里正则 `\{"csrfToken":"([^"]+)"\}` 取（43 字符）。一次会话可复用。

### Agent REST（可选，若已配置 agent token）
前缀 `/api/agent/v1`，`Authorization: Bearer <token>`（`alimonitor\web\routes\agent.py:36-54`）。
命中后 `request.state.agent_authenticated=True`，可绕过 csrf。`GET /api/agent/v1/capabilities` 列全部能力。
token 由 `POST /api/settings/agent-token` 生成、只明文出现一次，库里只存 SHA-256（`data/settings.json` 的 `agentTokenHash`）。**拿不回旧 token**，需要就在控制台重新生成。

## 端点

### 系统
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | `{"service":"AliExpressMonitor","status":"ok"}` |
| GET | `/api/overview` | 见下 |
| GET | `/api/settings` | `{extensionPaired,extensionOnline,agentPaired}` |
| POST | `/api/settings/agent-token` | 生成 agent token（写）→ `{agentToken}` |

`GET /api/overview` →
```json
{
  "enabledShopCount": 31, "todayNewCount": 51,
  "lastScan": {"runId":44,"startedAt":"…","finishedAt":"…","status":"succeeded","newCount":51},
  "trend": [{"date":"2026-11-11","newCount":51}],
  "shopNewCounts": [{"shopId":1,"shopName":"…","newCount":40}],
  "recentDiscoveries": [ProductResponse…],
  "loginStatus": {"profileDirectoryExists":true,"profileOccupied":false,"loginVerifiedAt":null}
}
```

### 扫描
| 方法 | 路径 | body | 返回 |
|---|---|---|---|
| POST | `/api/scans` | `{shopIds: [int] \| null}` | `{runId,conflict,parentRunId}` |
| GET | `/api/scans/active` | – | `{active: ScanProgress \| null}` |
| POST | `/api/scans/{runId}/retry` | `{}` | `{runId,conflict,parentRunId}` |
| POST | `/api/scans/{runId}/pause\|resume\|stop` | `{}` | ScanProgress |
| GET | `/api/scans/{runId}` | – | ScanProgress |
| GET | `/api/scans?page=&pageSize=` | – | `{items,total,page,pageSize}` |

`ScanProgress`：`{runId,status,phase,currentShop,shopIndex,shopTotal,succeeded,failed,newCount,errorCode,actionableError,captchaRevealFailed}`。
历史 item：`{id,startedAt,finishedAt,status,newCount,attempts:[{id,startedAt,finishedAt,status,shopResults:[{shopId,shopName,status,newCount,errorCode,errorMessage}]}]}`。

`SAFE_SCAN_MESSAGES`（`alimonitor\web\routes\scans.py:20-30`）：

| errorCode | 中文 |
|---|---|
| TIMEOUT | 店铺扫描超时，请检查网络后重试 |
| PROFILE_LOCKED | 登录浏览器仍在运行，请关闭后再开始扫描 |
| LOGIN_REQUIRED | 登录状态已失效，请重新登录后重试 |
| CAPTCHA_REQUIRED | 速卖通要求验证码，请手动完成后重试 |
| BROWSER_CLOSED | Chrome 窗口已关闭，请重新启动扫描 |
| SCAN_FAILED / WORKER_FAILED | 扫描失败，请重试 |
| USER_STOPPED | 用户停止了扫描 |
| PLATFORM_RISK_REDIRECT | 平台风控跳转（需人工处理/IP 问题） |

### 商品
`GET /api/products` 参数：`state`(pending_review|to_process|ignored|completed|all，默认 pending_review)、`shopId`、`discoveredFrom`、`discoveredTo`(YYYY-MM-DD)、`scanRunId`、`title`、`includeDisabledShops`、`page`、`pageSize`(1–100)。
返回 `{items,total,page,pageSize,nextCursor,hasMore,filterSignature,selectionScopes}`。
`ProductResponse`：`{id,shopId,shopName,remoteProductId,title,url,imageUrl,firstSeenAt,lastSeenAt,state,stateUpdatedAt,stateVersion}`。

| 方法 | 路径 | body | 说明 |
|---|---|---|---|
| GET | `/api/products/selection` | 同筛选参数 | `{items:[{id,stateVersion}],total,filterSignature}`，批量改状态前拿快照 |
| PATCH | `/api/products/state` | `BulkStateBody` | 批量改状态 |
| PATCH | `/api/products/{id}/state` | `{state,expectedVersion}` | 单件改状态 |

`BulkStateBody`：`{scope:"page"|"filter", state, productIds:[], expectedVersions:{id:ver}, filter?, filterSignature?}`
- `scope="page"`：必须给 `productIds`（非空），带 `expectedVersions`。
- `scope="filter"`：必须给 `filter`+`filterSignature`（来自 `/selection`），`productIds` 留空，`expectedVersions` 覆盖全部命中项且与快照一致，否则 409 `FILTER_CHANGED`。
- 返回 `{scope,updatedCount,filterSignature,items}`。

`ProductState = Literal["pending_review","to_process","ignored","completed"]`，传别的 422。
状态中文：pending_review=**待判断**、to_process=**待处理**、ignored=**已忽略**、completed=**已完成**（`alimonitor\web\static\app.js:4-7`、`templates\index.html:153-156`）。

### Picker（采集队列）
| 方法 | 路径 | body | 说明 |
|---|---|---|---|
| GET | `/api/picker/status` | – | `{paired,online,queued,inFlight,lastActivitySecondsAgo,version,phase}` |
| POST | `/api/picker/queue` | `{productIds:[1..500]}` | `{queued,skipped,queueLength}` |
| POST | `/api/picker/clear` | `{}` | `{cleared}` |
| POST | `/api/picker/pair` | `{}` | `{pickerToken}` |

扩展侧（头 `X-Picker-Token`）：`GET /api/picker/next?wait=(0-30)`；`POST /api/picker/report {tag,productId,outcome:"succeeded"|"failed",reason?,uploaded?}`；`POST /api/picker/progress {phase,tag?,productId?}`。

### 导出
`POST /api/exports` body `{state,shopId,discoveredFrom,discoveredTo,scanRunId,title}` → `{id,status,total}`；
`GET /api/exports/{id}`；`GET /api/exports/{id}/download`（xlsx）。

## picker_coordinator 常量
`alimonitor\services\picker_coordinator.py`：
`HEARTBEAT_STALE_SECONDS=45.0`、`IN_FLIGHT_LEASE_SECONDS=210.0`、`QUEUEABLE_STATES=("pending_review","to_process")`、
`RISK_CONTROL_REASON_PREFIX="risk-control"`、`SUSPECT_RISK_REASON_PREFIX="risk-control-suspect"`、
`PAGE_HIDDEN_REASON_PREFIX="page-hidden"`、`CAPTCHA_WAIT_PHASE="awaiting-captcha"`、`COOLDOWN_PHASE="cooling-down"`。
行为：`sweep_stale()`(:168) 把超 210s 未回报的在途任务退回队列；`clear_queue()`(:155) 先 sweep 再清空队列；`claim_next()`(:196) 长轮询；`submit_report()`(:220) 仅当 `outcome=succeeded` 且 `uploaded` 才把商品置 `completed`，失败只记日志、商品状态不变。

## Item Picker 扩展常量
`D:\GitHub\toy-item-picker-chrome-extension\src\background\pickerLoop.mjs`：
`PICKER_HOST_WINDOW_TIMEOUT_MS=10000`、`PICKER_TAB_OPEN_TIMEOUT_MS=15000`、`PICKER_TAB_LOAD_TIMEOUT_MS=45000`、
`PICKER_TAB_LOAD_GRACE_MS=5000`、`PICKER_TAB_LOAD_RETRY_DELAY_MS=4000`、`PICKER_TAB_SETTLE_DELAY_MS=1500`、
`PICKER_EXCHANGE_RATE_TIMEOUT_MS=15000`、`PICKER_MESSAGE_TIMEOUT_MS=16000`、`PICKER_MESSAGE_RETRY_TIMEOUT_MS=5000`、
`PICKER_HOST_WINDOW_STATE="normal"`、`PICKER_HOST_WINDOW_BOUNDS={width:520,height:720,left:0,top:0}`。
流程：`opening-tab` → ensureHostWindow(focused:false、不最小化) → tabs.create(active:true) → waitForTabComplete → 失败重开一次 → settle → fetchExchangeRate → `extracting` → 发消息抓详情 → 上传 → `uploading`。
manifest：v0.2.14 MV3，`permissions=[activeTab,alarms,debugger,downloads,notifications,storage]`；`background.service_worker="src/background/index-v0.2.14.js"`；alarm `aliMonitorPickerPoll` 每 0.5min。

## DB schema（`alimonitor\schema.py`）
- `products`(:323)：`id, shop_id, remote_product_id, title, image_url, first_seen_at, last_seen_at, state, state_updated_at, state_version` + 生成列 `url`；`UNIQUE (shop_id, remote_product_id)`(:338)。
- `scan_runs`(:340)、`scan_attempts`(:347)、`scan_shop_results`(:354)、`scan_discoveries`(:364)（`UNIQUE(scan_run_id,product_id)`）、`scan_runtime_state`(:370)。
- `shops`(:303)：`shop_key UNIQUE`、`remote_store_id UNIQUE`。

## 运行路径（`alimonitor\launcher.py`）
`HOST="127.0.0.1"`、`PORT=18765`、`HEALTH_PATH="/api/health"`、`MUTEX_NAME=r"Local\AliExpressMonitorDashboard"`、`READY_TIMEOUT_SECONDS=15.0`。
`RuntimePaths.under(root)` → `data/products.db`、`data/browser_profile`、`data/settings.json`。
