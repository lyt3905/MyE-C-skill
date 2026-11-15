# PID3527 新版V2真实只读测试

日期：2026-11-16（Asia/Shanghai）；shana1 / Shop 7。用户请求“测试下这个”。本次仅实际DeepSeek审核，不执行整改、上传或保存，不部署程序，不commit/push。

## 实际覆盖和结果

主图5、详情18、SKU池2、SKU引用2、正文商品图片18，共45处业务引用；25份不同图片内容。读取失败0处，正文尾部附加内容豁免。

DeepSeek实际请求25次，无自动重试，无MiMo；24份输出通过格式校验，1份缺少evidence_ids被拒绝。原始公开输出动作分布{"REMOVE_TEXT": 5, "KEEP": 19, "DELETE": 1}（包含格式未通过的动作，不表示可执行）。程序动作分布{"KEEP": 19, "DELETE": 0, "REMOVE_TEXT": 4, "AI_REGENERATE": 0, "REVIEW": 2}。审核状态INCOMPLETE，合规结论UNKNOWN。置信度与Token仅记录，Token 230000，USD未知。

独立新登录会话回读商品状态与审核前一致，应用源码/提示词与已通过917项测试的版本一致。真实上传/保存0。本次只读审核结束不表示商品已经整改完成。

## 规则一致性检查

主图1包含SENLEBAO店铺标识、全新/现货徽标与底部促销色带。DeepSeek原始判断为REMOVE_TEXT，程序为REMOVE_TEXT。

此前用户要求明确其他店铺促销边框整图删除；若本图属于该规则，应为DELETE。本次模型将这些区域识别成局部叠加文字，未给出OTHER_STORE_FRAME角色，因此现有程序没有将其整图删除。这是新版提示词在新商品上的规则泛化偏差，不能宣称边框规则真实验证全部通过；原判断保留，没有伪造成模型DELETE，没有修改代码或重复调用模型刷结论。

参数文字图、Legendary Toys品牌标识、空白SKU图分别以模型真实观察记录，不能将“纯文字”或“后加图形”一概当店铺宣传/可擦水印。原逐图说明见下文。

- 详情12的LEGENDARY TOYS标识被判厂家标识并KEEP；详情13–15的同类标识却被判为叠加店铺水印并REMOVE_TEXT。此不一致需要修正或复核，不能直接按这3条擦除建议执行。
- 详情11的公开输出原动作REMOVE_TEXT，但缺少必填evidence_ids，程序REVIEW。记录了真实用量，没有自动重试或伪造补齐。
- SKU池1/无盒规格是近乎空白图片，模型DELETE但visual_class=UNKNOWN，程序因CLASS_UNKNOWN保留REVIEW。该暂缓不是置信度门槛导致。
- 有盒规格目前引用无包装玩具图，详情18有实际包装照；read-only-sku-candidates.json保留只读候选建议，未执行分派。空白无盒图也需要另选有效商品图，不能仅删引用而留下坏SKU。

## 逐图原始判断与程序结果

| 对应位置 | DeepSeek原始动作 | 程序动作 | 置信度（仅记录） | 程序暂缓原因 |
|---|---|---|---|---|
| 主图1 | REMOVE_TEXT | REMOVE_TEXT | 0.86 |  |
| 主图2 | KEEP | KEEP | 0.95 |  |
| 主图3 | KEEP | KEEP | 0.94 |  |
| 主图4 | KEEP | KEEP | 0.97 |  |
| 主图5 | KEEP | KEEP | 0.9 |  |
| 详情1、正文1 | KEEP | KEEP | 0.95 |  |
| 详情2、正文2 | KEEP | KEEP | 0.9 |  |
| 详情3、正文3 | KEEP | KEEP | 0.95 |  |
| 详情4、正文4 | KEEP | KEEP | 0.98 |  |
| 详情5、正文5 | KEEP | KEEP | 0.93 |  |
| 详情6、正文6 | KEEP | KEEP | 0.95 |  |
| 详情7、正文7 | KEEP | KEEP | 0.96 |  |
| 详情8、正文8 | KEEP | KEEP | 0.96 |  |
| 详情9、正文9 | KEEP | KEEP | 0.92 |  |
| 详情10、正文10 | KEEP | KEEP | 0.95 |  |
| 详情11、正文11 | REMOVE_TEXT（输出格式未通过） | REVIEW | 0.9 | MODEL_OUTPUT_INCOMPLETE |
| 详情12、正文12 | KEEP | KEEP | 0.92 |  |
| 详情13、正文13 | REMOVE_TEXT | REMOVE_TEXT | 0.93 |  |
| 详情14、正文14 | REMOVE_TEXT | REMOVE_TEXT | 0.94 |  |
| 详情15、正文15 | REMOVE_TEXT | REMOVE_TEXT | 0.92 |  |
| 详情16、正文16 | KEEP | KEEP | 0.88 |  |
| 详情17、正文17 | KEEP | KEEP | 0.9 |  |
| 详情18、正文18 | KEEP | KEEP | 0.92 |  |
| SKU池1、SKU引用1 | DELETE | REVIEW | 0.95 | CLASS_UNKNOWN |
| SKU池2、SKU引用2 | KEEP | KEEP | 0.95 |  |

### 主图1

Central image is a clear toy product photograph on a complex dark display background. The visible top-left SENLEBAO badge, top-right '全新 现货' badge, and bottom black/yellow promotional strips are clearly superimposed store/promotional text overlays with no useful product specifications; remove those text regions locally while preserving the toy. No retail box is visible, so the toy-only SKU grouping applies. Ownership of the overlay text is visually unresolved, but the added-overlay role is visible.

### 主图2

The image shows a yellow and black transforming robot figure in a dynamic front three-quarter pose against a dark blurred sci-fi background. No retail box or packaging is visible. No store frame, seller notice, added watermark, or other removable overlay is visible; only ordinary product/photo content is present. The figure is usable as a toy main image, with the lower feet slightly cropped by the frame edge.

### 主图3

Single yellow/black transforming robot figure is fully visible in a front three-quarter view against a complex industrial display background. No retail box is visible, and no overlaid seller notice, other-store frame, or added watermark is observed. The product is clear and usable, so keep unchanged; identity observations are record-only.

### 主图4

Visible image is a clear product photograph of a yellow and black striped Camaro-style toy vehicle in front three-quarter view on a blurred neon street-like background. No retail box, seller notice, other-store promotional frame, or added store watermark is visible. The only visible marks are manufacturer/model product print on the toy itself, which remains protected. The vehicle mode is consistent with the Bumblebee listing context, and the image is usable as a toy product photo.

### 主图5

The image shows two complete toy vehicles in a staged industrial scene: a red/blue truck and a yellow Camaro-style car. No retail box, seller notice, other-store frame, or added watermark is visible. The only visible markings are manufacturer/product print on the yellow car, which is protected. Exact model code LT01/MPM03 is not visible, but the yellow car is visually consistent with the Bumblebee context; identity observations are record-only and do not affect the KEEP decision.

### 详情1、正文1

The image is a product-information text sheet for the listed LT01/MPM03 item, containing size, material, contents, retail price and shipping-estimate text. No toy or retail box is visible. The text is useful product specification/information rather than an added watermark, seller frame, or pure promotional notice, so the image should be kept and its text preserved.

### 详情2、正文2

The image shows the yellow-and-black transforming robot figure posed in an industrial diorama. No retail box, packaging, added store watermark, seller notice, or other explicit overlay is visible. A small background sign contains ordinary scene text and is not an actionable watermark. The toy and its details are clearly visible and should be retained; listing identity observations are consistent but remain record-only.

### 详情3、正文3

Visible yellow/black transforming robot figure in a dynamic pose against a dark blurred sci-fi-style background. No retail box, packaging print, overlaid text, store frame, seller notice, or added watermark is visible. The image is a usable product detail photograph and should be kept unchanged. Listing context mentions LT01/MPM03 Bumblebee; the model code is not visibly printed, but the visible structure and yellow/black color scheme are consistent.

### 详情4、正文4

Close-up detail photograph of a yellow Bumblebee-style robot figure showing the head, face, chest, and upper torso. The subject is clear but cropped, so it is not a complete figure view. No retail box, packaging, text overlay, store watermark, seller notice, or other-store frame is visible. The image is a usable product detail photo and should be kept unchanged.

### 详情5、正文5

Usable product detail photograph of a yellow/black transformation robot figure in a complex industrial scene. The full toy is visible, no retail box is present, and no visible text or watermark requires editing. Keep the image unchanged.

### 详情6、正文6

Full-body front product photo of the yellow/black Bumblebee-style transforming toy against a dark industrial backdrop. No retail box, added watermark, seller notice, or other-store frame is visible. The toy is complete and clear, so this is usable product imagery and should be kept.

### 详情7、正文7

Ordinary product-detail photograph of a yellow and black transforming robot toy with accessories on a textured industrial-style background. The full figure and accessories are visible, with no retail box, seller notice, promotion frame, or visible text/watermark overlay. Listing-identity indications are recorded only and do not require removal.

### 详情8、正文8

Visible image is a clear three-quarter view of a yellow and black-striped Camaro-style transforming toy in vehicle mode on a textured surface with a blurred neon background. No retail box or packaging is visible. The only visible text/marks are product print (CAMARO side lettering) and the manufacturer bowtie emblem, both protected. No seller notice, other-store frame, or added watermark is visible, so KEEP.

### 详情9、正文9

The image shows a yellow toy Camaro-style vehicle in a staged dark industrial scene. No retail box, seller notice, frame, or added watermark is visible. The visible CAMARO and front badge markings are product/manufacturer print on the toy and must be preserved, not removed. The image is usable as a toy product scene, so it is kept.

### 详情10、正文10

Staged product scene showing two fully visible toy vehicles on a dark industrial background. No retail box, seller frame, seller notice, or added watermark is visible. This is usable product imagery, so keep it and preserve the toy structures and printed details.

### 详情11、正文11

Dark studio product scene showing a yellow Bumblebee-style robot and yellow Camaro toy; no retail box is visible. A clearly superimposed white hand logo with 'LEGENDARY TOYS' text sits on the left background. It is an added store watermark rather than product or packaging print, so remove that region while preserving the toy details. Exact model text is not visible, so product identity against the LT01/MPM03 context is recorded as UNKNOWN.

### 详情12、正文12

Studio product-detail photograph showing two complete yellow-and-black Bumblebee-style transforming robot figures on a dark background. No retail box or packaging is visible. The centered LEGENDARY TOYS logo and fist graphic appear to be manufacturer branding and are consistent with the LT01 model context, so they are protected manufacturer-marking content rather than a removable added store watermark. Product identity is visually consistent with the listing context; no model code text is visibly printed on the figures.

### 详情13、正文13

The image shows the full yellow/black Bumblebee-style toy figure on a plain dark background with no retail box visible. A clearly superimposed 'LEGENDARY TOYS' logo/watermark appears at the bottom right on the background, separated from the product, so it is treated as an added store watermark and removed locally while preserving the figure and its details.

### 详情14、正文14

Full-view product detail of a yellow/black transforming figure on a black studio background. No retail box or packaging is visible. A superimposed 'LEGENDARY TOYS' logo/text appears at the lower right on background; it is treated as an added store/creator watermark and can be removed by a low-risk local region edit while preserving the toy.

### 详情15、正文15

Studio three-quarter full-body photograph of a yellow and black Bumblebee-style transforming robot figure on a dark seamless background. No retail box is visible. The bottom-left 'LEGENDARY TOYS' logo is a clearly superimposed store-style watermark over background area, not product or packaging print; it has low overlap risk and can be removed locally. Preserve the toy figure and its visible product markings.

### 详情16、正文16

Product-detail photograph of a yellow-and-black transforming robot figure in a dynamic pose on a dark studio background. No retail box is visible. The visible 'LEGENDARY TOYS' mark appears to be a manufacturer/brand logo matching the LT01 product context, and the bottom-right handle text is an unresolved creator/credit mark; both are protected print/marks and do not justify removal. No explicit removable store overlay is present, so the image is kept.

### 详情17、正文17

Product-only studio photo of a yellow/black transforming robot on a dark seamless background. The toy is complete and clear, and no retail box is visible. The lower-right 'LEGENDARY TOYS' badge appears to be a manufacturer/brand logo consistent with the LT01 context rather than an explicit added third-party store watermark or seller notice, so it is protected and kept. Identity observations are record-only: appearance matches the Bee-style context and color, while the model code is not visibly printed.

### 详情18、正文18

Retail-box-only detail photo showing the LT01 Metal Diton / WASP packaging with printed Bumblebee figure and vehicle artwork. The visible box text, manufacturer logo, model markings, age label and disclaimer are packaging/manufacturer print and remain protected. No added store watermark, seller notice, or other-store promotional frame is visible, so the image is usable and should be kept.

### SKU池1、SKU引用1

The supplied SKU image is a uniform near-white blank frame with no visible toy, retail box, packaging, product print, model detail, or overlay text. No actionable regions are present, and the image has no usable product presentation, so DELETE is appropriate.

### SKU池2、SKU引用2

The image clearly shows a complete yellow-and-black transforming robot figure with its loose accessories on a dark industrial-style display surface. No retail box or packaging is visible, and no overlay text, seller notice, store frame, or watermark is visible. This is a usable toy product scene suitable for a no-retail-box SKU grouping; no removal or deletion is warranted.

## 证据

- work/v2-audit-3527-20261116/status.json、events.jsonl：实际请求与最终状态。
- jobs/JOB_7e1ec9724d47493b8d8d900c46f90643：正式V2原图、队列、原响应、预算账本、覆盖与证据清单。
- prompt-*.txt：实际发送提示词，不含API密钥。
- description-scope.json、body-judgements.json：正文范围和逐图对应。
- independent-after.json：独立会话的只读回读。
- conclusions.json：原始/程序动作及规则偏差。
- read-only-sku-candidates.json：仅计算候选，未上传、分配或保存。
- source-contact-sheet.jpg：原图总览，编号按唯一内容顺序，标注为零基内部位置ID。

本轮未修改应用代码。历史Job/原响应/账本不重跑、不改写。新版局部修复、上传、保存和生产部署在本商品上均NOT_RUN。
