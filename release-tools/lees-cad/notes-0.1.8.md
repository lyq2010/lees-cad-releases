Lee's CAD 0.1.8 修复 Windows 更新校验的启动环境兼容问题，并加固发版验包结果检查。

- 🛡️ 从 PowerShell 7 等宿主启动桌面应用时，更新校验使用 Windows PowerShell 的系统模块环境，避免继承不兼容模块路径而失败。
- 📦 Windows 发版验包等待程序真正退出，并同时验证无效输入失败、真实发行包成功。

本版保留 0.1.7 的默认首页、文件菜单选项、菜单交互修复、运行资源优化，以及桌面/CLI 共用全部 80 份随包字体。

Windows 仅提供 MSI，包含桌面应用、CLI、共享字体和许可。macOS 提供 DMG 和应用更新 TAR，CLI 位于 `.app/Contents/MacOS/lees-cad-cli`，不修改 PATH，不再新增独立 CLI ZIP。macOS 使用 ad-hoc 签名，非 Developer ID 或 Apple 公证。
