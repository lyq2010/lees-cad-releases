Lee's CAD 0.1.9 改善 DWG 兼容性，降低复杂图纸内存占用。

- 🛠️ 修复部分含标注关联记录的 DWG 无法打开的问题，保留关联与回存数据。
- 🧠 降低复杂图纸内存占用，保留完整文字轮廓和缩放细节。

Windows 仅提供 MSI，包含桌面应用、CLI、共享字体和许可。macOS 提供 DMG 和应用更新 TAR，CLI 位于 `.app/Contents/MacOS/lees-cad-cli`，与桌面共用全部 80 份随包字体，不修改 PATH。macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。
