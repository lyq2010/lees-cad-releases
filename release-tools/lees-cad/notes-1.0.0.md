Lee's CAD 1.0.0 按 Windows 和 macOS 分别对齐常用 AutoCAD 操作习惯，完善 CLI。

- ⌨️ 按平台调整常用快捷键，完善面板切换、选择循环、临时正交和 Shift 移除选择。
- 🛠️ 修复正交与极轴同时开启、组合键匹配顺序及切换面板丢失未提交输入的问题。
- 🧰 CLI 支持命令别名和别名搜索，完善参数校验与双平台使用说明。

Windows 仅提供 MSI，包含桌面应用、CLI、共享字体和许可。macOS 提供 DMG 和应用更新 TAR，CLI 位于 `.app/Contents/MacOS/lees-cad-cli`，与桌面共用全部 80 份随包字体，不修改 PATH。macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。
