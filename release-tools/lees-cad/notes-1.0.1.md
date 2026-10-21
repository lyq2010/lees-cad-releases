Lee's CAD 1.0.1 优化 macOS 大图连续缩放时的内存占用。

- 🧠 减少显示缓冲的反复扩容，保留文字、曲线与填充精度。

Windows 仅提供 MSI，包含桌面应用、CLI、共享字体和许可。macOS 提供 DMG 和应用更新 TAR，CLI 位于 `.app/Contents/MacOS/lees-cad-cli`，与桌面共用全部 80 份随包字体，不修改 PATH。macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。
