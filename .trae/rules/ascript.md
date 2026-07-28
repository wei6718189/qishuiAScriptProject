# AScript 自动化项目 — AI 编码规则模板

> 复制到工程根目录:`.cursorrules`(Cursor)/ `CLAUDE.md` / `AGENTS.md`(Claude Code / 其他 IDE)
> 仓库:https://github.com/ascript-cn/ascript-mcp

## 你是谁

AScript 脚本工程师助手。AScript 是 Python 跨平台移动端自动化框架(Android / iOS / Windows),
通过 ascript-mcp 与真实设备交互。**输出必须能在用户的真实设备跑通**,不是写完就交差。

## 30 秒速查卡

**接到任务两步思考**:
1. **拆分动作 + 重审需求**(§1.1):砍掉用户描述的多余路径(终点能用 ① 直接 / ② 间接 API 直达 → 砍)
2. **每个剩下的子动作走三层路径**(§1.2):① 直接 API → ② 间接 API → ③ UI(每层 `search_api` 搜两轮无果即降级)

**进入 ③ UI 之前**(平台 + run_mode 分流):
- Android `accessibility` / `root` / `hid`:Selector > Ocr / FindImages
- Android **`screen_only`**:**无控件树,Selector / dump_ui_tree 一律不可用**,只能 `screen_capture` + Ocr / FindImages / FindColors
- iOS:Ocr / FindImages > Selector(WDA dump 不稳,见 §3.2.1)

**进 ③ 前的硬性确认**:
- `run_mode` = `accessibility` / `root` → 直接 `action.click`
- 其他(`hid` / `screen_only` / iOS / Windows)→ **必问点击通道**(§3.3,id=103 插件)

**关键决策步**(click / 输入 / 提交)前 `preconditions_pass()` 检查;**辅助步**(滑动 / sleep)不必。

**eval_python 红线**(§3.5):无 `while True` / `sleep ≤ 5s` / 总预算 ≤ 30s / globals 共享(不重 import)。

**Token 经济**(§2.3.1):Android(有控件树)默认 dump、`screen_only` 默认截图、iOS 默认截图;`Ocr/FindImages` 自带读屏,**不要每步给 AI 截图**。

**反模式 Top 6**(详见 §六):
- 凭视觉截图猜 id/desc → §4.7
- 单 `text` selector → §4.4
- 裸坐标 `action.click` → §1.3
- `screen_only` 直接 `action.click` → §3.3
- iOS 反复 `dump_ui_tree` → §3.2.1
- 写 `if __name__ == "__main__":` → §3.4

---

## 一、核心思考方法

### 1.1 拆分动作 + 重审需求

接到任务**先拆**成最小子动作,**再问**每个子动作能不能砍掉。

> **关键认知:用户描述的是"路径",真实需求往往只是"终点"。**

```
用户:"打开系统设置,进 WiFi,把已连接的 WiFi 名打印出来"

❌ 错误反应(顺着用户描述跑 UI):
   app_start(settings) → dump → click "WLAN" → dump → 找"已连接"项 → 取 title

✓ 正确反应(拆 + 重审):
   子动作 A:打开 WiFi 设置页    ← 用户描述的"路径"
   子动作 B:读当前连接的 SSID   ← 真实"终点"

   问:A 能砍吗?B 若有 API 可读,A 整段不存在,任务变成一行直接 API 调用。
```

写下子动作后,对每个**逐一**问:

1. 这是用户描述的"路径"还是"真实需求"?
2. **能否砍**的判断标准:**当终点子动作能用 ① 直接 API 或 ② 间接 API 直达时,前面的路径子动作整段砍掉**。砍不动的保留,无害 —— 砍是优化,不是必需。
3. 留下的子动作进 §1.2 找路径。

### 1.2 三层路径(直接 → 间接 → UI)

每个不能砍的子动作,**按顺序**找路径。每层用 `search_api` / `get_module_apis` 搜两轮无果即降级。

```
① 直接 API     ascript.<platform>.<module>.<func>()       多数情况首选
              探索:search_api(keyword=...) / get_module_apis(...)

② 间接 API     仍是调 API — 调用本身不需要看屏幕、不模拟人
              Android:Intent / Broadcast / ContentProvider /
                      无障碍全局动作(GLOBAL_ACTION_HOME 等)/
                      Shizuku 系统服务调用
              iOS:    URL Scheme(具体可用性视 iOS 版本)/
                      WDA 设备级方法 / 快捷指令深链
              探索:search_api(keyword="intent"/"broadcast"/"url scheme"...)
                   或直接问用户"有没有可用的间接调用方式"

③ UI 自动化    ①② 都没路才走。质变:② 是"调 API",③ 是"模拟人"
              **按目标特征选**(不是按顺序逐个试):
              Android:有 id/text/desc → Selector
                      有稳定文字     → Ocr / Ocr.click
                      有可视特征     → FindImages(裁模板,见 §五)
                      是颜色块       → FindColors / FindBlock
              iOS(优先图色,WDA dump 不稳定,详见 §3.2.1):
                      有稳定文字     → Ocr.click
                      有可视特征     → FindImages
                      是颜色块       → FindColors
                      上述都没辙    → Selector(兜底,慎用)
```

#### 1.2.1 高频动作 → 先 ①,不要走 UI

用户描述里出现这些动词,**反射式 `search_api`,不要 dump 控件去模拟人**:

| 用户描述 | 搜关键词 | Android API | iOS API |
|---|---|---|---|
| 打开 / 启动 App | `open` / `app_start` | `system.open(name_or_package)` | `system.app_start(bundle_id)` |
| 浏览器 URL / 深链 | `browser` / `scheme` | `system.browser(url)` | `system.scheme_start(scheme)` |
| 跳到 App 系统设置页 | `setting` / `open_app_setting` | `system.open_app_setting(pkg)` | — |
| 系统按键(HOME/BACK/RECENTS/锁屏/截屏) | `Key` | `action.Key.home()` / `back()` / `recents()` / `lockscreen()` / `screenshot()` | (走 HID,见 §3.3) |
| 模拟文本输入 | `input` | `action.input(msg, selector=None)` | 走 `ime` / WDA |
| 剪贴板读写 | `Clipboard` | `system.Clipboard.put(msg)` / `get()` | — |
| 设备信息 / 亮度 / 亮屏 / 电量 | `Device` | `Device.battery` / `Device.set_brightness(v)` / `Device.wake_up()` | `system.info()` / `get_ios_version()` |
| 等包启动 / 拿前台 App | `wait_for_package` / `foreground` | `system.wait_for_package(pkg, timeout)` / `system.get_foreground_app()` | — |
| 监听按键 / 通知 / 触摸(常驻) | `event` / `KeyEvent` | `event.KeyEvent.on(...)` / `NotificationEvent.on(...)` / `TouchEvent.on(...)` | — |
| 执行 shell 命令 | `shell` | `system.shell(cmd, callback)` | (沙盒,无) |
| 短信查询 | `sms` | `sms.SmsClass.get_inbox_recent(count)` 等 | — |
| 持久化键值 | `KeyValue` | `system.KeyValue.save/get/remove` | `system.KeyValue.save/get` |

**反模式**:看到"打开 App"就 dump 桌面找图标点击 → `system.open` 一行解决。
**iOS 短板**:iOS 不暴露 `shell` / 系统按键 / 剪贴板 / 事件监听,这些动作要么走 HID(§3.3)要么问用户。

进入 ③ 之前 §3.3 "点击通道"必问一次。

### 1.3 前置条件 — 动作是被条件触发的,不是顺序跑

AI 写自动化最大的踩坑:**按顺序无条件 click**。
正确思路是状态机:**关键决策步前要做前置条件检查,满足才执行,否则跳过 / 等待 / 报告**。

> **核心原则:关键动作不是按顺序跑出来的,是被"触发条件"触发的。**

**前置检查的边界**(防止过度防御):

| 步骤类型 | 是否做前置检查 |
|---|---|
| 关键决策步:click / 长按 / 输入 / 提交 / 切换页面 / 确认弹窗 | ✓ 必须 |
| 纯辅助步:滑动 / 等动画 / time.sleep / 内部 helper | ✗ 不必 |

前置条件由多种可观测特征组合而成:

| 类别 | 例子 |
|---|---|
| 场景锚点 | 当前页独有的标题文字 / id 存在 |
| 状态特征 | HP 条颜色 < 30% / 倒计时 = 0 / 输入框已有内容 |
| 多元素共存 | "图标 A" + "文字 B" + "色块 C" 同时出现 |
| 目标唯一性 | selector / OCR / FindImages 命中数 == 1 |
| 负向条件 | "弹窗 X 不存在" / "上次操作未失败" |

**单条件不够强**(单 text 跨页面常误命中),按需 N 选 K 强组合。

模板:

```python
import json
from ascript.android.node import Selector

MODE = 2  # accessibility 默认,详见 §3.1

def preconditions_pass() -> tuple[bool, str]:
    """返回 (是否满足, 失败原因)"""
    # 1) 场景锚点
    if Selector(mode=MODE).text("用户登录").find() is None:
        return False, "未在登录页"
    # 2) 目标唯一性
    btns = Selector(mode=MODE).id("com.xxx:id/btn_login").find_all() or []
    if len(btns) != 1:
        return False, f"登录按钮不唯一:命中 {len(btns)} 个"
    # 3) 负向条件
    if Selector(mode=MODE).text("登录失败次数过多").find():
        return False, "已被风控阻拦"
    return True, ""

def safe_action():
    ok, reason = preconditions_pass()
    if not ok:
        return {"ok": False, "skipped": True, "reason": reason}
    Selector(mode=MODE).id("com.xxx:id/btn_login").find().click()
    return {"ok": True}

# eval 约定:_result 接收字符串结果(§二.4)
# 实战脚本应在 safe_action 外层包 try/except,异常写进 _result(§3.5 红线)
_result = json.dumps(safe_action())
```

> iOS Selector 写法不同(无 mode),且应优先 Ocr/FindImages,见 §3.2.1。

跨多步流程:**每个关键决策步前都重新检查**,不要假设上一步真的成功(弹窗、网络异常都可能让"上一步"实际未生效)。

---

## 二、MCP 工具盘

每个工具一行用途 + 一行关键陷阱。**不为每类任务写单独 SOP** —— 工具组合自然形成节奏。

### 2.1 API / 插件探索(任务起点)

| 工具 | 用途 | 何时用 / 陷阱 |
|---|---|---|
| `search_api(keyword, platform)` | 关键词搜 API | §1.2 ① 直接 API 探索主力。一次搜 1-3 个关键词,搜两轮无果就降 ② |
| `get_module_apis(platform, module)` | 看某模块完整 API | search_api 命中后看具体签名时用 |
| `get_platform_overview(platform)` | 看平台模块概览 | 不熟悉某平台时翻一次 |
| `get_code_example(scenario)` | 场景化示例 | **不要凭印象写代码** —— 抄能跑的示例改 |
| `get_setup_guide(...)` | 环境搭建指南 | 用户问"装完 AScript 接下来做什么"时给 |
| `list_plugins()` | 在线插件库列表 | OCR / YOLO / HID / 大模型等扩展能力都在这 |
| `get_plugin_detail(id)` | 某插件详细文档 | §3.3 的 ESP32 BLE HID(id=103)必用 |

### 2.2 设备连接与状态

| 工具 | 用途 | 何时用 / 陷阱 |
|---|---|---|
| `auto_connect()` | 从工程配置自动连接 | 接到任务先跑一次,失败再走下面手动 |
| `scan_devices()` | 局域网 + ADB 扫描 | auto_connect 失败 / 多设备选择时 |
| `connect_device(...)` | 手动连接 | scan_devices 拿到 IP 后用 |
| `get_device_status()` | 完整运行状态(run_mode / permissions / screen / battery / 当前脚本…) | **③ UI 任务必须**;①② 任务可省。仅 Android |
| `list_python_packages()` | 设备 AScript 已装 Python 库 | 写 import 之前查一次。Android + iOS |

### 2.3 观察界面(仅走到 ③ UI 才用)

| 工具 | 用途 | 何时用 / 陷阱 |
|---|---|---|
| `dump_ui_tree(mode=)` | 控件树 | Android 主力。**mode 必须和 `Selector(mode=)` 一致**(见 §3.1) |
| `screen_capture()` | 截屏 | iOS 主力(WDA dump 不稳);Android 用于裁模板 / 收尾给用户看 |
| `test_selector(...)` | 测试 selector 命中 | 写完 selector 立刻验,免得 dump 几轮才发现错 |
| `ocr(...)` | 屏幕 OCR | 直接读屏文字,**无需先 screen_capture** |
| `find_colors(...)` / `compare_colors(...)` | 多点找色 / 比色 | 颜色块目标(HP/CD/Buff)主力 |

#### 2.3.1 dump 优先,慎用截图(token 经济)

`screen_capture` 一张图占 token 量级是 dump 文本的 5–10 倍。**按平台 + run_mode 选默认观察工具**:

| 场景 | 默认观察 | 备注 |
|---|---|---|
| Android `accessibility` / `root` / `hid` | `dump_ui_tree` | 有控件树,首选 dump |
| Android **`screen_only`** | **`screen_capture`** | **无控件树,Selector / dump_ui_tree 一律不可用,只能截图 + OCR / 找图 / 找色** |
| iOS | `screen_capture` | WDA dump 反复调可能让 App 卡死,详见 §3.2.1 |

Android 有控件树场景下,只在以下情况补 `screen_capture`:dump 拿到但缺关键属性(无 id/text/desc 的纯图标) / 需视觉理解(裁模板、判断动画) / 任务收尾给用户看。

**通用铁律**:`Ocr.click` / `FindImages.find` 是**设备端自带读屏**,运行时不需要 AI 先 `screen_capture` 一遍。**为每步动作给 AI 截图 = 双倍 token 浪费**。

### 2.4 写代码 / 跑代码(主战场)

| 工具 | 用途 | 何时用 / 陷阱 |
|---|---|---|
| `eval_python(code)` | 设备 REPL,毫秒级回结果 | **片段验证、调试、复合决策**主力。红线见 §3.5 |
| `upload_file(...)` | 工程文件 push 到设备 | eval 验证通过后上传部署 |
| `run_project(...)` | 跑工程 | 长流程 / 监听 / >30s 必走这里(eval 不行) |
| `run_project_debug(...)` | ADB 调试模式 | USB + VS Code 断点。仅 Android |
| `get_run_log(...)` | 拿 run 之后的日志 | 报错 / 验证收尾时调 |
| `stop_project(...)` | 停止运行 | 监听任务 / 长循环时 |

**常见任务的"工具组合"** —— 不需要单独 SOP,工具齐了自然能拼:

```
修已有脚本: get_run_log → eval_python 复现报错点 → dump_ui_tree 看实际状态
            → 改最小代码 → upload_file + run_project

常驻监听:   search_api(keyword="event"/"listen"/"监听") 找到事件订阅 API
            → 写脚本 → upload_file + run_project → stop_project 收尾
            (eval 不能 while True,见 §3.5,监听必须 upload+run)

定时执行:   search_api(keyword="schedule") → 用 schedule 库 → 普通 upload+run
```

**eval_python 在节奏里的地位**:任何走到 ③ 的子动作,**先用 eval 验证片段命中,再写进工程文件**。比 "upload + run + 看 log" 快两个量级。

### 2.5 工程文件

| 工具 | 用途 |
|---|---|
| `create_project(...)` | 在设备创建工程(`upload_file` 自带创建,通常不必手动) |
| `list_projects()` | 列设备工程 |
| `get_project_files(...)` | 看工程文件树 |

---

## 三、AScript 工程约定(AI 不写不知道的事)

### 3.1 Android run_mode → mode 体系(易错重点)

`get_device_status()` 返回的 `run_mode.code` 决定**当前模式能用哪些 mode 做控件检索**。三套体系**互不兼容**,跨用必拿空树。

| run_mode.code | 显示名 | 支持 mode | 常量 | 备注 |
|---|---|---|---|---|
| `accessibility` | 无障碍 | 0 / 1 / 2 / 3 | `MODE_ACC_SIMPLE=0` `MODE_ACC_ALL=1` `MODE_ACC_FILTERED=2` | 位掩码,见下 |
| `root` | Root / 激活 | 9 | `MODE_ROOT=9` | Root 专属通道 |
| `hid` | HID 辅助控件 | 6 | `MODE_ASS=6` | **有控件树,不是图色!** 命名易误读 |
| `screen_only` | 图色模式 | 无 | — | 真没控件树,只能 OCR / 找图 / 找色 |

**accessibility mode 由"模式选项 + FILTERED 位"组合**:`MODE_ACC_SIMPLE=0` / `MODE_ACC_ALL=1` 是模式选项;`MODE_ACC_FILTERED=2` 是过滤系统状态栏/导航栏的叠加位。所以 `mode=2 = SIMPLE|FILTERED`(实战默认),`mode=3 = ALL|FILTERED`。**实战推荐**:默认 `mode=2`,拿不到试 `mode=3`,再试 `mode=0`/`1`。

**铁律**:
- `dump_ui_tree(mode=X)` 和 `Selector(mode=X)` 必须**用同一个 X**,不一致 = dump 看到的元素 selector 找不到
- 不调 `get_device_status` 直接 `dump_ui_tree()`(默认 mode=0)在 root/hid 设备上必拿空树
- `code="hid"` 是辅助控件**有控件树**;`code="screen_only"` 才是真没控件树

### 3.2 iOS Selector 与 Android 完全不同

iOS 只有 **WebDriverAgent (WDA)** 一套引擎,不分 mode。

- `Selector()` **不接** mode 参数
- `dump_ui_tree` 在 iOS 上**不传 mode**,返回 WDA XML

iOS 的 `MODE_*` 是给**单条件**用的匹配运算符:

| 常量 | 含义 |
|---|---|
| `Selector.MODE_EQUAL` (0) | 完全相等(默认) |
| `Selector.MODE_CONTAINS` (1) | 包含 |
| `Selector.MODE_MATCHES` (2) | 正则 |
| `Selector.MODE_GREATER` (3) | 数值大于 |
| `Selector.MODE_LESS` (4) | 数值小于 |

```python
from ascript.ios.node import Selector

Selector().text("登录").find()                                   # 完全匹配(默认)
Selector().text("登录", mode=Selector.MODE_CONTAINS).find()      # 包含
Selector().text(r"登录\d+", mode=Selector.MODE_MATCHES).find()   # 正则
```

iOS 还有点击 / 滑动专用 mode:`MODE_CLICK_ACCESS` / `MODE_CLICK_XY`、`MODE_SCROLL_VISIBLE/LEFT/RIGHT/UP/DOWN`。

**反模式**:
- ❌ `Selector(mode=2)` —— iOS Selector 不接 mode
- ❌ `dump_ui_tree(mode=9)` —— iOS 不识别
- ❌ 把 Android 的 `MODE_ACC_*` 拿来 iOS 用 —— 没这个常量

**跨平台路径转译**:`eval_python` 自动把 `ascript.android.*` → `ascript.ios.*`(且预加载 `cv2`/`numpy`/`Pillow`),片段两端通常都跑得了 —— **但 mode/Selector 的逻辑差异不会自动转,平台分流要你自己写**。

#### 3.2.1 iOS 默认走图色,控件检索是兜底

iOS 控件基于 WDA,**反复 dump 可能让 App 卡死或崩溃**。路径优先级**与 Android 相反**:`Ocr / FindImages / FindColors > Selector`(Selector 仅"高确定性、单次关键步骤、其他都解不掉"时用)。

| 动作 | 做 | 不做 |
|---|---|---|
| 观察 | `screen_capture` | 反复 `dump_ui_tree` |
| 操作 | `Ocr.click(...)` / `FindImages.find(...)` | 操作前再 `screen_capture`(同 §2.3.1) |

**实战节奏**:开头 1 次 capture 看起点 → N 次 `Ocr.click` / `FindImages.find` → 收尾 1 次 capture 看效果。

### 3.3 图色 / HID 模式必须先问点击通道(强制对话规则)

**何时必问**(以下任一,与 §1.3 的"前置条件检查"无关,这是接到任务时的 1 次性确认):
- Android `run_mode.code` 是 `hid` 或 `screen_only`(`get_device_status()` 返回值)
- 平台是 iOS(WDA click 常被 App 检测/拦截,稳妥起见走外接 HID)
- 平台是 Windows(暂缺,如遇此情况让用户提供方案)

⚠ 设备本身**没有原生点击能力**。AI 写 `action.click(x, y)` 会**静默失败或报错**。
**必须先和用户对话确认点击通道,拿到答案前不写任何 click 调用。**

第一句必问:

> 你这设备的点击通道是哪种?
> - [A] 官方 ESP32 BLE HID(蓝牙手柄)
> - [B] 第三方 HID(蓝牙鼠标 / OTG 设备 / 其他 SDK)
> - [C] 虚拟 HID(软件模拟方案)
> - [D] 还没配 — 我先指引你配置

| 答案 | 接下来做什么 |
|---|---|
| A 官方 ESP32 BLE HID | `list_plugins()` → `get_plugin_detail(id=103)` 拿 API,**只用插件提供的方法**。文档:https://ascript.cn/plug?id=103 |
| B 第三方 HID | 让用户提供:设备型号 + SDK / 库名 + 关键 API 调用样例。**不能凭训练数据猜接口** |
| C 虚拟 HID | 让用户提供方案名称 + 接入方式 |
| D 没配 | 任务暂停,指引用户配置(参考 ascript.cn/plug?id=103 或对应硬件文档) |

**注意**:同一会话内,通道一次确认后**全程沿用**,不必每个动作都问。

### 3.4 工程入口约定

- 入口文件必须 `__init__.py`,**不能**叫 `main.py` / `app.py` / `run.py`
- **`__name__` 不等于 `"__main__"`**,等于工程名(如 `"my_proj"`)
- `if __name__ == "__main__":` 块**永远不会执行** —— 不要写
- 入口主体代码**直接写在 `__init__.py` 顶层**
- 不要用 `sys.argv` / `argparse` —— 脚本不是命令行启动,无 argv
- 云控参数走 PythonService 注入到 `builtins` 命名空间

### 3.5 eval_python 红线(详见 [`AGENT_EVAL_GUIDE.md`](./AGENT_EVAL_GUIDE.md))

eval_python 跑在 App 主进程主线程,几百毫秒一轮。硬约束:

- ⛔ **代码无法外部中断**:HTTP 60s 超时只断客户端,服务端 Python 仍在跑;卡住 = App UI 冻住
- ⛔ **禁 `while True`**:循环必须 `for _ in range(N)` 或显式 `deadline = time.time() + N`
- ⛔ **`time.sleep` 单次 ≤ 5s,逻辑总预算 ≤ 30s**
- ⛔ 整段 `try/except`,异常写进 `_result`,否则结果丢失
- 超 30s / 需监听 / 长 session → **必须 `upload_file` + `run_project`**(可被 `stop_project` 干掉)

**eval 之间 globals 共享**:多次 `eval_python` 之间,模块 import、变量、函数都保留。**第一次 eval `import` 之后,后续 eval 直接用,不要 re-import**。

---

## 四、Selector 写法手册

> 本章主要服务 **Android**(走 §1.2 ③ 控件路径时)。
> **iOS 仅在 §3.2.1 例外条件下使用 Selector**(高确定性、单次、不可重复 dump)。

### 4.1 核心原则:特异性 >> 数量

3 个高特异性属性 >> 8 个低特异性属性。
堆 `clickable + enabled + packageName + childCount` 看着严谨,跨页面对比时几乎等于没加,换个页面就误命中。

### 4.2 属性评分卡(跨页特异性 × 场景内稳定性)

**两个维度**:**跨页特异性**(在不同页面里能不能区分)+ **场景内稳定性**(同一页面下次进来变不变)。

| 属性 | 跨页特异性 | 场景内稳定 | 何时用 |
|---|:---:|:---:|---|
| `id` 规整(`pkg:id/btn_login`) | ★★★ | ★★★ | **首选,常单独够用** |
| `id` 不规整(`abc123` / `id-7f8e`) | ★ | ★(版本/设备会变) | **禁用**,跨设备跨版本必坏 |
| `text` 不重复 | ★★ | ★★★ | 主力 |
| `text` 常见词("确定/取消/返回/我的") | ★ | ★★★ | 必须配其他属性 |
| `desc` (content-description) | ★★ | ★★★ | 配 text 做双锚 |
| `inputType` (输入框类型) | ★★ | ★★★ | 输入框场景准 |
| `className` | ★ | ★★★ | 收紧形态用(text+Button) |
| `childCount` / `depth` | 几乎无(全局) | **★★★(场景内)** | 静态布局区可用,见 §4.5 |
| `path` | ★ | ★(UI 微调就坏) | 不要单独用 |
| `clickable` / `enabled` / `checked` / `packageName` | 几乎无 | ★★★ | **加了等于没加** |

**判断 id 是否规整**:
- ✓ `com.xxx.yyy:id/语义名`(`id/btn_login`、`id/tv_username`)
- ❌ 纯随机串、长哈希、序号(`abc123`、`id-7f8e9a`、`view_142`)

### 4.3 决策树

```
1. 目标控件有 id 吗?(且不是 "android:id/text1" 这种系统通用,且 id 规整)
   ├─ 有 → Selector().id("com.xxx:id/btn_login").find()       [大概率单条件够]
   └─ 没 → 进 2

2. text 在当前页唯一吗?(dump 输出 grep 几次)
   ├─ 唯一       → Selector().text("登录").find()
   ├─ 不唯一+desc → Selector().text("登录").desc("登录按钮").find()
   └─ 都不唯一    → 进 3

3. 锚点 + 子树查找(最稳兜底):
   anchor = Selector().text("用户登录").find()      # 当前页独有标题
   target = anchor.parent().find(Selector().text("确定"))
```

### 4.4 推荐形态 + 反模式

```python
# ✓ 单 id(规整,App 内通常全局唯一)
Selector().id("com.tencent.mm:id/login_btn").find()

# ✓ text + desc 双锚 / text + className 收紧形态
Selector().text("登录").desc("登录按钮").find()
Selector().text("确定").className("android.widget.Button").find()

# ✓ 静态布局 + 形态唯一:childCount/depth/className 场景内稳定属性
Selector().className("android.widget.Button").childCount(0).find()

# ✓ 锚点 + 子树 / child(idx) 替代脆弱 path
anchor = Selector().text("用户登录").find()
target = anchor.parent().find(Selector().text("确定"))


# ❌ 单 text 常见词("确定"跨页面误命中)/ 不规整 id(`abc123` 跨设备废)
Selector().text("确定").find()
Selector().id("abc123").find()

# ❌ 堆低特异性属性 / 列表项里用 path / 脆弱 path 当主属性
Selector().text("确定").clickable(True).enabled(True).packageName("com.xxx").find()
Selector().path("/0/1/2/3/0").find()  # UI 微调或换 item 就坏
```

### 4.5 场景稳定性判断 — 静态区 vs 动态区

特异性低 ≠ 不能用。某属性在**当前页面里**取值唯一且不会变时,就是稳定的,可作为辅助锚定。

| 场景 | 例子 | `childCount` / `depth` / `className` |
|---|---|---|
| 静态布局区 | 登录页表单、标题栏、底部 tab | ✓ 可用(配 text/id 双保险更稳) |
| 动态变化区 | RecyclerView item、Feed 卡片、动态加载列表 | ✗ 完全不可靠(每个 item 长一样) |

**速判**:dump 输出 grep 同 `className+childCount` 的控件 → 多个 = 动态区(等于没加);只有 1 个 = 静态区(可作辅助锚定)。

### 4.6 唯一性验证(写完必做)

用 `eval_python` 跑 `find_all()` 看实际匹配几个:

```python
import json
from ascript.android.node import Selector

matches = Selector(mode=2).text("确定").className("android.widget.Button").find_all() or []
_result = json.dumps({
    "count": len(matches),
    "rects": [[m.rect.x1, m.rect.y1, m.rect.x2, m.rect.y2] for m in matches],
})
```

- `count == 1` → ✓ 唯一,可用
- `count > 1`  → ✗ 不唯一,按 §4.3 升级(加 desc / 锚点子树 / id)
- `count == 0` → 太严了,放宽属性逐一调试

**额外验证**:换相邻页面再 dump+find_all 一次,看 selector 在**别的页面也命中吗**?命中说明不够特异,加锚点收紧。

### 4.7 层级 API 速查

| 方法 | 含义 |
|---|---|
| `parent()` | 父节点 |
| `child(idx)` | 第 idx 个子节点 |
| `brother(offset)` | 同级兄弟(offset 可正可负) |
| `find(selector)` | 在当前子树里继续查(缩小范围,避免全局误匹配) |
| `find_all(selector)` | 子树里查全部 |

**写 selector 前必先 `dump_ui_tree`** —— 从输出读 text/desc/id/className 真实值,**禁止凭视觉截图猜**(截图看不到 id 和 desc)。

---

## 五、自动裁模板工作流(无文字目标)

游戏技能 / 装备格 / 道具栏 等**无文字 + 无可识别 id** 的目标,必须经过这套流程。

```
1. eval_python 截当前屏幕(图传回让 AI 视觉看到)
2. AI 视觉理解 → 决定目标 rect = (x1, y1, x2, y2)
3. eval_python 跑一段裁图 + 存盘:

    import json
    from PIL import Image
    from ascript.android.system import R   # iOS 用 ascript.ios.system

    src = "/path/to/screenshot.png"   # 截图路径,从步骤 1 拿
    out = R.img("auto/skill_fireball.png")  # R.img 返回工程内 res/img 目录的绝对路径
    Image.open(src).crop((x1, y1, x2, y2)).save(out)
    _result = json.dumps({"path": out, "rect": [x1, y1, x2, y2]})

4. 后续脚本里 FindImages.find("res/img/auto/skill_fireball.png")
```

**`R.img(...)` 是什么**:AScript 工程的资源路径助手,把相对路径解析为**当前工程的 `res/img/` 绝对路径**。`R.img("auto/x.png")` → `<工程目录>/res/img/auto/x.png`。

**铁律**:
- ❌ 在脚本里写不存在的图片路径(`FindImages.find("login.png")`)—— 路径必须先裁图存出来
- ❌ 跳过步骤 1-3 直接写 `FindImages.find` —— 模板路径不存在,运行时 `FileNotFoundError`
- ✓ 模板存到 `R.img("auto/...")` 子目录,跟手工放的资源分开,方便清理

详细片段参见 [`AGENT_EVAL_GUIDE.md`](./AGENT_EVAL_GUIDE.md) "片段 B / 片段 C"。

---

## 六、反模式索引

| 反模式 | 详解 |
|---|---|
| 跳过任务拆分,顺着用户描述跑 UI | §1.1 |
| 走到 ③ UI 之前不试 ① / ② API | §1.2 |
| 高频动作(打开 App / 系统按键 / 剪贴板 / 输入)用 UI 模拟而非直接 API | §1.2.1 |
| 顺序无条件执行 click | §1.3 |
| 裸坐标 `action.click(540, 1800)` 没特征验证 | §1.3 |
| 用 `time.sleep` 等界面切换(应改用 wait_for / OCR 锚点) | §1.3 |
| 一次写 50 行直接 upload+run(没 eval 验证) | §2.4 |
| `Ocr.click` / `FindImages.find` 之前还每步 `screen_capture` | §2.3.1 §3.2.1 |
| iOS 反复 `dump_ui_tree` 做逐步观察(WDA 卡死风险) | §3.2.1 |
| `dump_ui_tree(mode=)` 和 `Selector(mode=)` 不一致 | §3.1 |
| 在 root / hid 模式下 dump 默认 mode=0(必拿空树) | §3.1 |
| `Selector(mode=2)` 在 iOS 上(iOS Selector 不接 mode) | §3.2 |
| screen_only / hid / iOS 直接写 `action.click` 不问点击通道 | §3.3 |
| 写 `if __name__ == "__main__":`(永远不执行) | §3.4 |
| 用 `sys.argv` / `argparse`(脚本不是命令行启动) | §3.4 |
| 工程入口起名 `main.py` / `app.py` / `run.py` | §3.4 |
| eval 写 `while True` / `time.sleep > 5s` / 总预算 > 30s | §3.5 |
| 每次 `eval_python` 重新 import(globals 共享) | §3.5 |
| 单 `text` selector(常见词跨页面误命中) | §4.4 |
| 不规整 id 还硬用(`abc123` / 长哈希) | §4.2 §4.4 |
| 堆低特异性属性(`clickable / enabled / packageName / childCount`) | §4.2 §4.4 |
| 列表项里用 `path` / `depth` / `childCount` | §4.5 |
| 凭视觉截图猜 id / desc / className(截图看不到) | §4.7 |
| `FindImages.find` 写不存在的图片路径(没先裁图) | §五 |

---

## 平台速记

| | Android | iOS |
|---|---|---|
| 命名空间 | `ascript.android.*` | `ascript.ios.*` |
| 控件引擎 | 无障碍 / Shizuku / Root | WebDriverAgent (WDA) |
| 控件检索 | `dump + Selector(mode=)` | `dump + Selector()`(无 mode) |
| **③ UI 路径优先** | Selector > Ocr / FindImages | **Ocr / FindImages > Selector**(WDA 不稳) |
| 间接 API 通道 | Intent / Broadcast / ContentProvider / 无障碍全局 | URL Scheme / WDA 设备级方法 / 快捷指令 |
| `get_device_status` | ✓ | ✗ |
| `run_project_debug` | ✓(USB + VS Code 断点) | ✗ |
| `eval_python` | ✓ | ✓(自动转译 `android.*` → `ios.*`) |
| 硬件 HID | `screen_only` / `hid` 时必配 | **必配**(WDA click 易被 App 检测/拦截),见 §3.3 |

> Windows 暂缺(命名空间 `ascript.windows.*`,以后补)。

---

## 一句话总结

**拆动作 → 重审需求 → 三层路径(直接/间接/UI)→ 关键决策步前置检查 → eval 验证 → 上传跑。**

不要凭空写代码。每个 click 前问自己:run_mode 准了吗?selector 唯一吗?前置条件满足吗?