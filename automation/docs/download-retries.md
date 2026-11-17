# 图片下载失败重试

0.2.10起，下载与独立回读使用[统一完整请求标识](image-http-profile.md)。此前因简化标识/CDN缓存路径导致的5182失败链接已通过真实补下载验证；下述限速、缓存和重试机制继续保留。

配置位置：`local/download.local.json`。正式V2采集入口自动读取，初始化只补缺失文件，不覆盖已有设置。独立安装使用其配置目录；可通过 `MYEC_CONFIG_DIR` 指定目录。

```json
{
  "max_retries": 3,
  "retry_base_seconds": 2,
  "retry_max_seconds": 30,
  "min_interval_seconds": 1
}
```

max_retries 是首次请求之外的重试次数，3表示每个失败URL最多请求4次，0关闭自动重试。允许0–10。等待按2/4/8秒递增，常规退避不超过retry_max_seconds；同主机请求还遵守min_interval_seconds。模型请求重试仍为0，本配置只作用于图片下载。

对HTTP408/425/429/500/502/503/504、连接中断及超时重试。404、认证失败、证书错误、图片解码/MIME/大小校验失败不重复请求。Retry-After支持秒数和HTTP日期；服务器等待要求优先于常规退避上限。同主机共享等待时间，写入成功缓存旁的backoff文件，下次启动继续遵守。要求等待超过60秒时返回WAIT_REQUIRED和retry_not_before，不提前请求，也不占用线程长时间等待。

成功图片保留字节及SHA校验，后续只请求缺失、损坏或此前失败的URL。每个新Job保留自己的证据副本。下载设置、各次尝试、HTTP状态及总计保存到download_results.json；正常完整审核还将该记录加入证据清单。重试耗尽的图仍是未审核，不能当作KEEP或整件通过。

低层download_unique默认仍为0重试，保留历史调用语义；正式V2 download_only显式加载上述默认或本地配置。旧Job和已封存下载失败记录不回写。5094补下载记录单独位于reports/download-retry-5094-20261116/，不重跑已claim的执行脚本。
