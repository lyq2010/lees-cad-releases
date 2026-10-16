# COS／R2 核对约束

2026-10-16 起，发行运维核对不下载 COS／R2 对象，不读取桶内 `latest.json` 或其他清单正文，不消耗存储桶对象下行流量。禁止对象 GET、Range 和下载回读，也不通过 CDN／Worker 间接读取正文。管理 API 的账户、对象列表元数据不属于对象下载。

- 本地 `verify.mjs` 继续验证 Ed25519、Minisign、完整 SHA-256、大小和平台身份。
- COS 使用官方 SDK 直连 `head_object`；R2 使用 Cloudflare 管理 API 的对象列表，按精确键筛选大小与 ETag。上传判重、上传后检查、晋升、清理和历史撤回共用此规则。
- 元数据仅核对单次 PUT 对象的 MD5 ETag 与大小，不将 ETag 冒充 SHA-256 或签名，也不声称完成下载验包或公网可达性验收。COS 改用带 Content-MD5 校验的单次 PUT；R2 保留固定版本 Wrangler 单次 PUT。
- 缺少大小／ETag、弱 ETag、分块 ETag、权限错误、列表越界或分页异常均停止；不覆盖未知不可变对象，不回退下载。历史分块对象也须停止，另行处理不能绕过本约束。
- 晋升前只从 GitHub Release 获取上一版签名清单并本地验签，保留拒绝降级和同版本冲突。两源旧指针必须对应已验签的旧版或本次清单；只有 GitHub 尚无正式版时才允许缺失指针。每次指针写入前重查元数据。
- 两源晋升和 GitHub Release 成功后才允许清理旧版；双源指针元数据须匹配本次本地清单。完整分页及当前版、stable、其他产品、未知对象和较新暂存目录的保护不变。

此约束针对发行运维核对，不改变用户主动安装或应用更新的下载功能。工作流仅保留 `workflow_dispatch`，推送工具不触发构建或发版。

本地回归：`test-storage.py`、`test-mirror.py`、`test-prune.py`、`test-previous.py` 全部使用网络替身，不访问存储桶。执行仍需通过项目 `scripts/dev-macos.sh`；修改后须同步私有仓模板与公开发行仓的工具／工作流。

接口依据：[COS HEAD](https://cloud.tencent.com/document/product/436/65828)、[COS MD5 校验](https://intl.cloud.tencent.com/zh/document/product/436/32467)、[R2 列表元数据](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/list/)、[R2 上传与分块 ETag](https://developers.cloudflare.com/r2/objects/upload-objects/)。
