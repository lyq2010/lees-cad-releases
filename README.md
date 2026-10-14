# Lee's CAD 发布

本仓库是 Lee's CAD 的公开发版仓，提供 Windows 与 macOS 的版本说明、安装包和校验信息。源码在独立的私有仓库维护。

## 下载

当前尚未发布正式版本。后续发行包会放在本仓库的 [Releases](https://github.com/lyq2010/lees-cad-releases/releases)，以每个版本说明列出的平台、架构、系统要求和文件为准。

## 发布内容

- 已验证的 Windows/macOS 安装包或便携包。
- 中文版本说明、更新内容及已知限制。
- SHA256 校验值，以及随包提供的许可证、版权和资产归属声明。

GitHub Actions 已按维护者授权启用，只有手动 `Lee's CAD 双平台闭源发行` Workflow。固定私有源码 SHA，默认 `publish=false`：分别构建/自签 Windows x64 和 macOS arm64，核对双端包身份与签名，仅保留二进制白名单资产。源码、历史、凭据和构建日志不上传。

`publish=true` 必须另有发行授权；COS 主源与 R2 备源是独立上传/公网回读 job，两端就绪屏障通过后才晋升并创建本仓 Release。工具仅操作 `lees-cad` 独立目录。

Lee's CAD 独立维护，与 Autodesk, Inc. 无关联。AutoCAD 和 DWG 是 Autodesk, Inc. 的商标。
