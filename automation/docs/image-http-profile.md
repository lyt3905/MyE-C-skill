# 图片下载与回读统一请求标识

0.2.10将三条图片HTTP入口统一到src/mye_c_automation/image_http.py的image_headers()：download_manager.download_unique、SiteWriteClient.fetch_image和Site.download。

复用原Site下载接口已有的完整Windows/Chrome User-Agent，统一Accept和Referer。浏览器Cookies、后台登录令牌不附加到公开图片请求。代理、TLS验证、下载限速、退避重试、成功缓存和图片校验保持现有逻辑。模型HTTP请求不受此修改影响。

原问题经真实冷链接对照复现：简化标识连续返回429，完整标识取得200并使后续简化请求命中CDN缓存。该兼容性问题与请求标识及缓存路径有关，不能一律按请求过快处理。现有重试机制继续处理实际返回的临时错误。

真实验证使用修复后的生产下载器和独立回读客户端：5182此前14个失败URL全部取回；当前21个唯一URL中4个成功缓存复用、17次网络下载全部200、0次重试，独立21个URL字节校验全部一致。旧Job保持不变，本轮未调用模型、未上传或保存商品。新增图片状态为DOWNLOADED_NOT_AUDITED，下载成功不等于审核通过。

证据：reports/image-http-fix-20261116/；此前对照实验：reports/image-429-diagnosis-20261116/。原Skill目录未修改。
