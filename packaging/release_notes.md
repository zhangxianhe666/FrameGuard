## 帧防 FrameGuard {{VERSION}}

用多模态大模型逐帧理解监控画面，对照你自己写的规则判定违规，并输出分时段报告。
本页为 **{{VERSION}}** 版本的安装包，包内已自带 Python 与全部依赖，**无需另装环境**。

### 下载对应平台

| 平台 | 文件 | 安装方式 |
| --- | --- | --- |
| macOS（Apple 芯片，M 系列） | `FrameGuard-{{VERSION}}-macos-arm64.dmg` | 打开 dmg，把 FrameGuard 拖进「应用程序」 |
| macOS（Intel 芯片） | `FrameGuard-{{VERSION}}-macos-x86_64.dmg` | 同上 |
| Windows 10 / 11（64 位） | `FrameGuard-{{VERSION}}-windows-x64-setup.exe` | 双击安装，支持免管理员安装 |
| Linux（x86_64） | `FrameGuard-{{VERSION}}-linux-x86_64.AppImage` | `chmod +x` 后直接运行；无 FUSE 环境用同名 `.tar.gz` |

### 首次启动需要放行

安装包未做商业代码签名，系统会拦一次：

- **macOS**：在「应用程序」里**右键 → 打开 → 再点一次「打开」**。
  若仍被拦下，终端执行：`xattr -dr com.apple.quarantine /Applications/FrameGuard.app`
- **Windows**：出现 SmartScreen 提示时点「更多信息 → 仍要运行」。

### 启动之后

程序会在本机启动服务并自动打开浏览器（默认 <http://127.0.0.1:7891>，端口被占用会自动顺延），
在界面「**⑥ 模型配置 → API Key**」填入 Key 即可开始分析，无需手工创建 `.env`。

- 报告与缓存位置：
  - macOS：`~/Library/Application Support/FrameGuard/`
  - Windows：`%APPDATA%\FrameGuard\`
  - Linux：`~/.local/share/FrameGuard/`
- 关闭服务：
  - macOS：按 ⌘Q
  - Linux：`./FrameGuard-{{VERSION}}-linux-x86_64.AppImage stop`
  - Windows：开始菜单 → 「Stop FrameGuard」

### 说明

- 判定结果仅作合规巡查的辅助参考，最终结论请以现场核实为准。
- 完整使用文档见 [README](https://github.com/{{REPO}}#readme)。
