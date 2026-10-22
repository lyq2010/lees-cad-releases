Lee's CAD 1.0.3 完善 Windows 与 macOS 更新缓存自动清理。

- 🧹 更新成功并通过健康校验后，自动清理安装包、解包目录及旧应用和设置备份。
- 🛡️ 下载失败或取消时清除残包，安装或健康校验失败时保留旧应用、设置备份和诊断记录。
- 🔄 保护正在下载或安装的更新任务；文件占用等原因导致清理未完成时，下次启动自动重试。

Windows 仅提供 MSI，包含桌面应用、CLI、共享字体和许可。macOS 提供 DMG 和应用更新 TAR，CLI 位于 `.app/Contents/MacOS/lees-cad-cli`，与桌面共用全部 80 份随包字体，不修改 PATH。macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。
