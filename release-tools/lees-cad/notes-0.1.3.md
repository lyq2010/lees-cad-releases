Lee's CAD 0.1.3 修复 macOS DMG 安装后的严格签名检查，并包含 0.1.2 的 DWG、文件打开及字体修复。

- DMG 改用 APFS，避免 HFS 混合镜像额外的 FinderInfo 元数据影响应用签名；新增镜像内和普通复制后的实际签名、应用身份门禁。
- 修复删除图形/块参照后的 QSAVE，以及部分节点图编辑后保存失败；保留严格数据回读校验。
- 修复 macOS Finder 冷启动、已运行及多文件打开 DWG/DXF。
- 改善中文 UI 字体选择，增加原生 SHX/Unicode/BigFont 单线字形及复杂线型符号；为过密填充和复杂字形增加资源预算，降低大图卡死风险。

建议 macOS 用户使用 0.1.3 DMG，替代 0.1.2 DMG。SHX 从本机用户目录、指定路径及已安装 CAD 读取，发行包不包含第三方字库；缺失字体保留替代，图纸内字体名称保持原样。

Windows 仅提供 MSI，包含桌面应用、CLI 和许可；macOS Apple Silicon 提供 DMG、应用更新 TAR 和 CLI ZIP。Windows 使用维护者自签证书，macOS 使用 ad-hoc 签名，不代表系统信任或 Apple 公证。代理数据保留不等于可编辑其插件语义，不承诺任意工程图完整无损或与 AutoCAD 完全等效。
