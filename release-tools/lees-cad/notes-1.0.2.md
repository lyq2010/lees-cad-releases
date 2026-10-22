Lee's CAD 1.0.2 修复图纸删除后的保存与 macOS 滚轮缩放问题。

- 🛠️ 修复删除含关联标注的图幅后无法保存的问题。
- 🖱️ 修复 macOS 鼠标滚轮误作平移，恢复围绕光标缩放并保留触控板手势。
- 🔒 软件更新窗口仅显示版本号，不再展示下载源域名。

Windows 仅提供 MSI，包含桌面应用、CLI、共享字体和许可。macOS 提供 DMG 和应用更新 TAR，CLI 位于 `.app/Contents/MacOS/lees-cad-cli`，与桌面共用全部 80 份随包字体，不修改 PATH。macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。
