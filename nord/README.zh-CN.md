# Picom · Nord / dwm

基于官方稳定版 v13（`d87a5ba3af7a9ee3c4e040ee29b2dea7e9e46317`）。

`nord/picom.conf` 使用 GLX、VSync 和 frame pacing，保留 damage 增量重绘，
保持全屏视频处于合成状态；无模糊或透明度特效。
窗口打开/恢复使用 140ms、96%→100% 的非线性缩放与淡入，
关闭/最小化使用 120ms、100%→98% 的缩放与淡出。
浮动窗口、Kitty 和小窗口均使用相同规则；只排除菜单、通知和锁屏等临时 UI。
没有配置 position/size 动画，拖动和交互缩放直接跟随鼠标。

源码修复：窗口映射后客户端/WM 往往继续发送位置、尺寸更新；未配置几何动画时，
上游会因此提前结束正在播放的动画。本分支让原动画继续推进，几何更新仍立即生效。
生命周期事件仍可中断动画，显式配置的几何动画仍遵从原行为。

本机 Intel 显示 + NVIDIA 计算卡还会使上游误选 NVIDIA 的 SGI 帧调度器。
本分支通过现有后端驱动检测接口，以实际 GL 渲染器选择调度器：
Intel/Mesa 使用 Present，NVIDIA 渲染器仍保留 SGI 兼容路径；
其他 provider 引起的驱动兼容处理继续保留。新增单元测试覆盖混合显卡及回退。
GLX 初始化日志会明确记录 VSync 启用成功。

GLX 的圆角着色器会沿圆弧补绘原 X11 边框颜色，从而保留 dwm 的
`#b48ead` 焦点边框；没有把边框颜色硬编码进合成器，失焦颜色也能跟随 WM。

构建与检查：

```sh
bash nord/build.sh
./build-nord/src/picom --config nord/picom.conf
```

在已有 X11 会话中运行隔离回归测试（需要 Xephyr、xdotool、Pillow、Kitty 和 dwm）：

```sh
python nord/test-runtime.py --picom build-nord/src/picom --dwm /path/to/dwm --output /tmp/picom-nord-test
```

测试实际采样 GLX 合成后的像素，检查 ConfigureNotify 后的开窗动画、四角边框、
即时移动、关闭残影的释放和真实 Kitty 的生命周期动画。
Xephyr 父窗口放在屏幕外；嵌套服务器不支持 swap-control 时会记录 VSync 警告。
可追加 `--electron /usr/share/code/code`，使用临时配置启动真实 Electron 应用，
检查连续移动的行为；这不是物理显示器上的拖动帧率测量。

上游许可证和构建依赖见根目录 README。X11 嵌套测试不等同于物理屏幕的
撕裂测试；实际视频/拖动效果需在显示器上复核，尤其是不同 GPU、驱动与刷新率。
