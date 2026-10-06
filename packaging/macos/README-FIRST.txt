帧防 FrameGuard · macOS 安装说明
================================

1. 把左边的「FrameGuard」拖进右边的「Applications」文件夹。

2. 首次打开：在「应用程序」里右键点 FrameGuard → 选择「打开」→ 再点一次「打开」。
   （这是 macOS 对未上架 App Store、且未做苹果开发者签名的应用的默认拦截，
     只需要放行这一次，之后双击即可正常启动。）

   如果右键「打开」仍被拦下，可在终端执行一次：
       xattr -dr com.apple.quarantine /Applications/FrameGuard.app

3. 启动后会自动打开浏览器并进入操作界面。界面地址默认为：
       http://127.0.0.1:7891
   若该端口已被占用，程序会自动顺延到下一个可用端口，
   实际端口可在「运行日志」或终端输出中查看。

4. 关闭：在程序坞右键 FrameGuard → 退出，或按 Command + Q。

报告与缓存的存放位置（卸载时如需彻底清理可一并删除）：
    ~/Library/Application Support/FrameGuard/
        outputs/   每次任务的报告（HTML / Markdown / CSV / JSON）
        cache/     抽帧缓存、演示图片、崩溃日志
        .env       可选，配置 FRAMEGUARD_API_KEY 等（放在这里升级不丢）

在界面上填写 API Key 即可，无需手工建 .env。
