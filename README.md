# Honor Hunter V700 RGB Lighting Control for Linux (`honer-v700-lights`)

专为 **荣耀猎人游戏本 V700 (`HUAWEI FRD-WX9`)** 打造的 Linux 原生全机身 RGB 灯光控制套件。支持 **A 面猎人 LOGO 灯**、**四分区 RGB 背光键盘**、以及 **机身升降风谷 70 灯珠灯带** 的独立调色、硬件级 16 分段渐变、动态流光跑马灯与**零延迟打字波纹涟漪**。

---

## ✨ 功能特性

- **全机身三区联动控制**：
  - **A 面 LOGO (`0xA0`)**：屏幕背面标志灯独立 RGB 控制。
  - **四分区背光键盘 (`0xB0`)**：支持左区 (`WASD`)、中左区、中右区、右区（数字键）4 分区独立撞色或全局联动，支持一键恢复原厂经典的 `蓝/绿/黄/红` 四色配置。
  - **机身风谷灯带 (`0xD0`)**：支持 70 颗独立寻址 RGB 灯珠（4 大硬件分段 / 16 细分色块）的精细控制。
- **🌈 硬件级多色渐变主题（零后台占用）**：
  - 内置 **霓虹彩虹渐变**、**赛博朋克撞色**、**冰火两重天**、**极光幻境渐变**、**猎人竞技 FPS (`WASD` 烈焰红)** 等主题，直接刷入主板 EC 硬件保持，写完立即卸载内核模块，**0% 后台 CPU 占用**。
- **🚀 9 种动态灯效与按键涟漪引擎**：
  - **交互式按键反馈**：💧 按键波纹涟漪 (`key-ripple`)、🎆 七彩打字烟花 (`key-rainbow`)、⚡ 疾速按键充能 (`key-reactive`)。
  - **全局氛围动效**：💨 单色呼吸灯 (`breathe`)、🎇 七彩交替呼吸 (`breathe-rainbow`)、☄️ 流光跑马灯 (`marquee`)、🛸 霹雳游侠扫描 (`scanner`)、🌊 动态彩虹波浪 (`rainbow-wave`)、🔮 赛博双色律动 (`cyber-pulse`)。
- **🛡️ 零延迟打字防冲突架构 (Zero-Lag EC Typing Guard)**：
  - 针对内置 `i8042` 键盘与 ACPI WMI 灯光共享同一颗嵌入式控制器 (`EC0`) 的硬件特性，内置 `115ms` 打字静默让路窗口与 `16ms` 包间按键抢占中断，确保高速盲打时 **0% EC 总线争用、绝不卡键**。
- **GTK4 现代化桌面控制中心**：
  - 顶部配备实时发光 LOGO 徽章、四分区键盘色块与 16 分段风谷灯带动态预览条。

---

## 🏗️ 架构与通信协议

荣耀猎人 V700 的灯光由主板 BIOS/EC 通过专有 **ACPI WMI** 接口控制（GUID：`ABBC0F5B-8EA1-11D1-A000-C90629100000`）：

1. **DKMS 内核模块 (`dkms/honer_v700_lights.c`)**：
   - 校验 DMI (`HUAWEI` / `FRD-WX9`) 并暴露 `/sys/kernel/honer_v700_lights/{request,response}`。
   - 每次写入 64 字节十六进制指令包，调用 `wmi_evaluate_method` 下发至 ACPI `SLED`/`GLED` 方法，并接收 256 字节固件响应。
   - **即用即载**：静态操作完成后立即自动执行 `modprobe -r honer_v700_lights` 卸载模块。
2. **64 字节协议数据包格式 (`src/v700-lights.py`)**：
   - **读取状态 (`0x06 0x06`)**：`[0x06, 0x06, <zone>, <selector>, 0...]`，响应包 `reply[7:10]` 为当前 `[R, G, B]`。
   - **写入颜色 (`0x06 0x05`)**：`[0x06, 0x05, <zone>, <mode>, <start>, <end>, <speed_hi>, <speed_lo>, <count>, R, G, B, ...]`。

---

## 📦 安装与使用

### 1. 一键安装

```bash
git clone <repo-url>
cd honor-hunter-v700-lights
sudo ./install.sh
```

### 2. 图形界面

安装后可在 GNOME 应用菜单或桌面启动 **「灯光控制」**，也可以直接运行：

```bash
python3 /usr/local/lib/honer-v700-lights/light-control-app.py
```

### 3. 命令行工具 (`honer-lights`)

```bash
# 查看所有灯区当前状态
sudo honer-lights status

# 一键恢复全机出厂默认灯光（冰川蓝 + 键盘原厂四色）
sudo honer-lights all-on

# 一键关闭全机所有灯光
sudo honer-lights all-off

# 刷入硬件级 16 段霓虹彩虹渐变（零后台占用）
sudo honer-lights theme --name gradient-rainbow

# 自定义键盘四分区撞色（左、中左、中右、右）
sudo honer-lights kbd-zones --zones-hex ff007f,a855f7,00f0ff,00ff88

# 启动「七彩打字烟花」按键涟漪效果
sudo honer-lights effect --name key-rainbow --speed normal

# 启动「流光跑马灯」效果
sudo honer-lights effect --name marquee --hex a855f7 --speed fast

# 停止动态灯效
sudo honer-lights stop-effect
```

---

## 🧪 运行单元测试

```bash
python3 tests/test_v700_lights.py
python3 tests/test_light_control.py
```

## 📄 开源协议

GPL-2.0 License
