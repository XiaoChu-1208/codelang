# codelang — macOS 打包说明

Windows 走 `installer/codelang.iss`（Inno Setup）出 `.exe`。
macOS 这边用 **py2app** 把 `desktop/` 打成一个原生 `codelang.app`，再封进
拖拽式 `.dmg`。

## 出包（在一台 Mac 上跑）

```bash
chmod +x installer/build_mac.sh        # 第一次给执行权限
./installer/build_mac.sh
```

脚本会自动：

1. 建一个临时 venv（`.build-venv`），装运行依赖 + `py2app`；
2. 用 `iconutil` 把 `assets/logo/icon-*.png` 合成 `installer/codelang.icns`；
3. 跑 `py2app`，产出 `dist/codelang.app`；
4. `codesign` ad-hoc 签名（让辅助功能授权在重打包后不丢）；
5. `hdiutil` 封 `dist/codelang-<版本>.dmg`，DMG 里带 `/Applications` 软链。

## 用户怎么装（图形化）

1. 双击 `codelang-<版本>.dmg` 挂载；
2. 把 `codelang` 拖进 `Applications`；
3. 首次打开：**右键点 codelang → 打开**（ad-hoc 签名没过公证，需手动绕过
   Gatekeeper，只需第一次）；
4. 启动后 macOS 会要权限 —— 到 **系统设置 → 隐私与安全性 → 辅助功能**，
   把 `codelang` 勾上（不勾 Option + 划词没反应）；
5. 想开机自启：**系统设置 → 通用 → 登录项** 点 `+` 把 `codelang` 加进去。

应用是 `LSUIElement` 代理程序：没有 Dock 图标，只在菜单栏显示小飞碟。

## 关于签名 / 公证

`build_mac.sh` 默认只做 **ad-hoc 签名**（免费），用户首次打开要右键绕过
Gatekeeper。若要对外正式分发、免去这一步，需要 Apple Developer 账号
（$99/年），把第 4 步换成：

```bash
codesign --force --deep --options runtime \
    --sign "Developer ID Application: <你的名字> (<TEAMID>)" dist/codelang.app
xcrun notarytool submit dist/codelang-<版本>.dmg \
    --apple-id <你的 Apple ID> --team-id <TEAMID> --wait
xcrun stapler staple dist/codelang-<版本>.dmg
```

## 从源码跑（开发者）

不打包、直接跑仍然走 `install_mac.sh` + 终端命令 `codelang`，见仓库根
`install_mac.sh`。`desktop/paths.py` 会自动识别是源码运行还是 `.app` 内运行
并解析资源路径，两种方式都能用。
