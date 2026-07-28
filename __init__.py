# -*- coding: utf-8 -*-
"""
汽水音乐 iOS 自动化脚本 — 自动看广告获取免费听歌权限
====================================================
功能：
  1. 启动汽水音乐 App
  2. 全局弹窗清理（会员续费 / 看视频领时长 等）
  3. 监测右上角"免"字按钮，点击进入广告
  4. 等待广告倒计时结束
  5. 领取奖励

技术栈：
  - OCR 文字识别（优先）：ascript.ios.screen.Ocr
  - 图像识别（兜底）  ：ascript.ios.screen.FindImages
  - 动作执行          ：ascript.ios.action
  - 应用管理          ：ascript.ios.system
"""

import time
import traceback

# ============== 基础模块导入 ==============
from ascript.ios import action
from ascript.ios.system import R, app_start, app_current, screen_size, notify
from ascript.ios.screen import Ocr, FindImages, capture

# ============== 全局配置 ==============

# 汽水音乐 App 名称 / Bundle ID（二选一，bundle_id 优先且更稳定）
APP_NAME = "汽水音乐"
APP_BUNDLE_ID = "com.soda.music"

# 主循环控制
MAX_LOOP_COUNT = 50         # 最大循环次数（防止无限跑）
LOOP_INTERVAL = 3           # 每次主循环间隔（秒）

# OCR 默认引擎（iOS 推荐 vision 或 paddle）
OCR_ENGINE = "vision"       # "vision"(iOS16+原生) / "paddle" / "mlkit"

# 区域配置（基于屏幕百分比，适配不同分辨率）
# 右上角"免"字按钮区域：屏幕右上 1/4
REGION_TOP_RIGHT = None     # 运行时根据屏幕尺寸动态计算
# 全屏区域
REGION_FULL = None


# ============== 工具函数 ==============

def log(msg: str):
    """统一日志打印"""
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{ts}] {msg}")


def safe_click(x: int, y: int, desc: str = ""):
    """
    安全点击：带日志 + 异常捕获
    说明：如果后续切换 HID 通道，只需修改此函数内部实现
    """
    try:
        log(f"点击 [{desc}] -> ({x}, {y})")
        action.click(x, y)
        time.sleep(0.8)  # 点击后等待界面响应
        return True
    except Exception as e:
        log(f"点击失败 [{desc}]: {e}")
        return False


def click_center():
    """点击屏幕中心（用于关闭弹窗的兜底策略）"""
    w, h = screen_size() or (0, 0)
    if w > 0 and h > 0:
        safe_click(w // 2, h // 2, "屏幕中心")
    else:
        safe_click(200, 400, "默认中心")


def init_regions():
    """根据屏幕尺寸初始化搜索区域"""
    global REGION_TOP_RIGHT, REGION_FULL
    w, h = screen_size() or (1080, 1920)
    log(f"屏幕尺寸: {w} x {h}")
    # 右上角区域：x 从 60%~100%，y 从 0%~20%
    REGION_TOP_RIGHT = [int(w * 0.6), 0, w, int(h * 0.2)]
    REGION_FULL = [0, 0, w, h]


# ============== 阶段一：启动 App ==============

def launch_app() -> bool:
    """启动汽水音乐 App"""
    log("=" * 50)
    log("阶段一：启动汽水音乐 App")
    try:
        if APP_BUNDLE_ID:
            ok = app_start(bundle_id=APP_BUNDLE_ID)
        else:
            ok = app_start(name=APP_NAME)
        if ok:
            log("App 启动指令已发送，等待加载...")
            time.sleep(5)  # 给 App 启动预留时间
            return True
        else:
            log("App 启动失败，尝试找图点击桌面图标...")
            return try_click_app_icon()
    except Exception as e:
        log(f"启动 App 异常: {e}")
        return try_click_app_icon()


def try_click_app_icon() -> bool:
    """兜底：通过找图点击桌面汽水音乐图标"""
    icon_path = R.img("qishuiyinyue.png")
    log(f"尝试找图点击桌面图标: {icon_path}")
    try:
        for attempt in range(3):
            pos = FindImages.find(icon_path, confidence=0.8)
            if pos:
                return safe_click(pos["center_x"], pos["center_y"], "汽水音乐图标")
            log(f"  第 {attempt+1} 次未找到图标，重试...")
            time.sleep(1)
        log("未找到汽水音乐图标，请检查图片或屏幕内容。")
        return False
    except Exception as e:
        log(f"找图点击图标异常: {e}")
        return False


# ============== 阶段二：全局弹窗清理 ==============

# 弹窗关键词黑名单（出现即尝试关闭）
POPUP_KEYWORDS = [
    "续费会员", "会员享专属", "开通会员", "立即开通",
    "看视频领取", "领取更多时长", "看视频得",
    "开启通知", "允许通知", "开启推送",
    "更新", "立即更新", "发现新版本",
    "签到", "立即签到",
    "同意", "同意并继续", "取消",
]

# 弹窗关闭按钮关键词
CLOSE_KEYWORDS = [
    "关闭", "叉", "×", "✕", "✖",
    "取消", "以后再说", "稍后", "暂不", "跳过",
]

# ============== 阶段一 B：开屏广告跳过 ==============

# 开屏「跳过」按钮常见文案（带倒计时的 3 秒跳过 / 跳过广告 / 跳过 Xs 等）
SPLASH_SKIP_KEYWORDS = [
    "跳过广告", "跳过", "跳过广告 ",
]


def skip_splash_ad(timeout=2) -> bool:
    """
    启动 App 后优先跳过开屏广告（开屏广告右上角一般有倒计时 + 跳过按钮）
    搜索区域：屏幕右上 1/3 区域（跳过按钮一般在右上角）
    timeout: 最长等待秒数（开屏广告一般 3~5 秒就自己消失，所以默认 5 秒够了）
    返回: 是否点击了跳过按钮（True=点了，False=没找到）
    """
    log("阶段一B：检测并跳过开屏广告")
    from ascript.ios.system import screen_size as _ss
    w, h = _ss() or (1080, 1920)
    # 右上角区域：x 60%~100%，y 0%~15%（开屏跳过按钮通常比"免"字更靠上）
    region_tr = [int(w * 0.55), 0, w, int(h * 0.2)]
    # 也全屏兜底扫一次（有些 App 跳过在右下角或底部）
    region_full = [0, 0, w, h]
    engine = OCR_ENGINE

    deadline = time.time() + timeout
    while time.time() < deadline:
        # 1) 先搜右上角（命中率最高）
        for kw in SPLASH_SKIP_KEYWORDS:
            try:
                r = Ocr.find(kw, rect=region_tr, mode=engine)
                if r:
                    log(f"  [右上角命中] 开屏跳过按钮: '{r.get('text','')}' 位置({r['center_x']}, {r['center_y']})")
                    safe_click(r["center_x"], r["center_y"], "开屏跳过(右上角)")
                    time.sleep(2)
                    return True
            except Exception as e:
                log(f"  开屏跳过 OCR 异常: {e}")
        # 2) 右上角没命中 → 全屏扫一次兜底（含「跳过」「跳过广告」）
        for kw in ["跳过", "跳过广告", "点击跳过", "点击跳过广告"]:
            try:
                r = Ocr.find(kw, rect=region_full, mode=engine)
                if r:
                    log(f"  [全屏命中] 开屏跳过按钮: '{r.get('text','')}' 位置({r['center_x']}, {r['center_y']})")
                    safe_click(r["center_x"], r["center_y"], "开屏跳过(全屏)")
                    time.sleep(2)
                    return True
            except Exception as e:
                log(f"  全屏兜底 OCR 异常: {e}")
        time.sleep(0.8)
    log("  未检测到开屏跳过按钮（可能无开屏广告，或已自动跳过）")
    return False


def ocr_find_text(keywords, rect=None, mode=None, timeout=0):
    """
    在屏幕上查找匹配关键词列表的文字
    返回第一个匹配的 OCR 结果: {text, confidence, x, y, center_x, center_y} 或 None
    """
    engine = mode or OCR_ENGINE
    start = time.time()
    while True:
        try:
            # 使用 Ocr.find：逐个关键词尝试
            for kw in keywords:
                result = Ocr.find(kw, rect=rect, mode=engine)
                if result:
                    log(f"  OCR 命中关键词: '{kw}' -> 实际文本: '{result.get('text', '')}' "
                        f"位置: ({result.get('center_x', 0)}, {result.get('center_y', 0)})")
                    return result
        except Exception as e:
            log(f"  OCR 识别异常: {e}")
        # 超时判断
        if timeout <= 0 or (time.time() - start) >= timeout:
            return None
        time.sleep(0.8)


def ocr_find_mid_first(keywords, mode=None):
    """
    【弹窗优先查找】先在屏幕中间区域（高度 20%~85%，弹窗集中区）搜索关键词，
    找不到再全屏搜。返回第一个命中的 OCR 结果或 None。

    为什么要这样做：
      - 弹窗按钮（领取奖励 / 继续观看 / 坚持退出）都在屏幕中间
      - 顶部状态栏有「领取成功×」等小字，和弹窗按钮同字会导致 OCR 先命中错按钮
    """
    from ascript.ios.system import screen_size as _ss
    w, h = _ss() or (1080, 1920)
    mid_rect = [0, int(h * 0.2), w, int(h * 0.85)]
    engine = mode or OCR_ENGINE
    try:
        for kw in keywords:
            r = Ocr.find(kw, rect=mid_rect, mode=engine)
            if r:
                log(f"  [中间区命中] '{kw}' -> '{r.get('text','')}' 位置({r.get('center_x',0)},{r.get('center_y',0)})")
                return r
        for kw in keywords:
            r = Ocr.find(kw, rect=REGION_FULL, mode=engine)
            if r:
                log(f"  [全屏命中] '{kw}' -> '{r.get('text','')}' 位置({r.get('center_x',0)},{r.get('center_y',0)})")
                return r
    except Exception as e:
        log(f"  OCR 中间优先查找异常: {e}")
    return None


# 【弹窗内优先点击的按钮】出现这些按钮时，不要打叉关闭，而是优先点击它们
#   - 领取奖励 / 领取成功 / 继续观看 是用户明确要求点的
PRIORITY_CLICK_KEYWORDS = ["继续观看", "领取奖励", "领取成功", "立即领取", "确认领取"]


def dismiss_popups(max_rounds=5) -> int:
    """
    全局弹窗清理（新版逻辑）：
      1) 优先检测「领取奖励 / 领取成功 / 继续观看」等按钮 → 有就点（不打叉关闭）
      2) 否则检测屏幕是否包含 POPUP_KEYWORDS（确认是弹窗场景）：
           - 是弹窗 → 找 CLOSE_KEYWORDS（关闭/×/取消…）点击关闭
           - 是弹窗但找不到关闭按钮 → 兜底点屏幕中心
      3) 没有 POPUP_KEYWORDS 也不是优先按钮 → 认为没弹窗，退出
    返回：已处理的弹窗/按钮数量
    """
    log("阶段二：全局弹窗清理")
    handled = 0
    for rnd in range(max_rounds):
        log(f"  [清理轮次 {rnd+1}/{max_rounds}]")
        # 1) 优先：弹窗里的领取类按钮 → 直接点，不关闭
        priority_btn = ocr_find_mid_first(PRIORITY_CLICK_KEYWORDS)
        if priority_btn:
            safe_click(priority_btn["center_x"], priority_btn["center_y"],
                       f"优先按钮 '{priority_btn.get('text', '')}'")
            handled += 1
            time.sleep(1.8)
            continue
        # 2) 确认是否弹窗场景（必须命中 POPUP_KEYWORDS 才算弹窗）
        popup_hit = ocr_find_text(POPUP_KEYWORDS, rect=REGION_FULL, timeout=0)
        if popup_hit:
            # 2a) 是弹窗 → 找关闭按钮（此时点 ×/关闭/取消 是安全的，已确认是弹窗）
            close_hit = ocr_find_text(CLOSE_KEYWORDS, rect=REGION_FULL, timeout=0)
            if close_hit:
                safe_click(close_hit["center_x"], close_hit["center_y"],
                           f"关闭按钮 '{close_hit.get('text', '')}'")
                handled += 1
                time.sleep(1.5)
                continue
            # 2b) 是弹窗但没找到关闭按钮 → 兜底点屏幕中心
            log(f"  检测到弹窗 '{popup_hit.get('text','')}' 但无关闭按钮，点屏幕中心兜底")
            click_center()
            handled += 1
            time.sleep(1.5)
            continue
        # 3) 既无优先按钮、也无弹窗关键词 → 清理完成
        log("  未检测到弹窗，清理完成。")
        break
    log(f"弹窗清理结束，共处理 {handled} 个")
    return handled


# ============== 阶段三：监测"免"字按钮并进入广告 ==============

def wait_for_mian_button(timeout=45) -> bool:
    """
    监测右上角"免"字按钮，出现则点击进入广告
    timeout: 最长等待秒数（0 表示只检查一次不等待）
    返回: 是否成功点击进入
    """
    log("阶段三：监测右上角'免'字按钮")
    deadline = time.time() + timeout if timeout > 0 else 0
    check_count = 0
    while True:
        check_count += 1
        # 每 10 次检查顺带做一次弹窗清理，防止中间弹广告
        if check_count % 10 == 0:
            dismiss_popups(max_rounds=2)
        # 在右上角区域找"免"字
        mian = Ocr.find("免", rect=REGION_TOP_RIGHT, mode=OCR_ENGINE)
        if mian:
            log(f"  找到'免'字按钮: ({mian['center_x']}, {mian['center_y']})")
            ok = safe_click(mian["center_x"], mian["center_y"], "'免'字按钮")
            if ok:
                time.sleep(2)
                return True
        # 超时检查
        if timeout > 0 and time.time() >= deadline:
            log(f"  等待'免'字按钮超时 ({timeout}s)，本轮跳过进入广告")
            return False
        # 无超时模式只跑一次
        if timeout == 0:
            log("  单次检查：未发现'免'字按钮")
            return False
        time.sleep(LOOP_INTERVAL)


# ============== 阶段四：等待广告倒计时结束 ==============

COUNTDOWN_KEYWORDS = [
    "秒后可领取", "秒后领取", "秒后关闭", "秒后获得",
    "领取奖励", "领取成功", "继续观看",
]


def check_and_click_continue_watching() -> bool:
    """
    【继续观看优先】只要屏幕上出现“继续观看”按钮（不管它和谁搭配出现）：
      - 如果同屏还有“领取奖励” → 这是用户说的二选一弹窗，优先点“继续观看”拿多倍
      - 如果只有“继续观看”没有“领取奖励” → 也点，继续看广告
    返回 True 表示已点击“继续观看”，调用者应该回到“等待广告倒计时”阶段。
    """
    continue_btn = ocr_find_mid_first(["继续观看"])
    if continue_btn:
        reward_btn = ocr_find_mid_first(["领取奖励"])
        if reward_btn:
            log("  [策略] 弹窗包含 '领取奖励' + '继续观看'，优先点击 '继续观看' 获取多倍奖励")
        else:
            log("  [策略] 检测到 '继续观看' 按钮，点击继续看广告")
        ok = safe_click(continue_btn["center_x"], continue_btn["center_y"],
                        f"继续观看按钮 '{continue_btn.get('text', '')}'")
        if ok:
            time.sleep(2.5)
            return True
    return False


def wait_ad_countdown(timeout=30) -> bool:
    """
    在广告界面等待倒计时结束。
    流程逻辑：
      1. 优先检测“继续观看” → 点了就延长 30s 继续等（最多 5 次，防死循环）
      2. 检测到以下任一按钮出现 → 认为倒计时结束，交给上层 claim_reward() 去点击：
           - 领取成功（顶部小按钮）
           - 立即领取
           - 领取奖励（中间弹窗）
      3. 否则 OCR 扫倒计时文案并打印日志
    返回: 是否检测到了可领取按钮（通常 True 代表进入领取阶段）
    """
    log("阶段四：等待广告倒计时结束")
    deadline = time.time() + timeout
    last_sec = -1
    continue_count = 0
    MAX_CONTINUE = 5
    while time.time() < deadline:
        # 1) 最高优先级：继续观看 → 点了继续等
        if continue_count < MAX_CONTINUE:
            if check_and_click_continue_watching():
                continue_count += 1
                log(f"  已点击继续观看 {continue_count}/{MAX_CONTINUE} 次，重新等待新一轮广告倒计时")
                deadline = max(deadline, time.time() + 30)
                last_sec = -1
                dismiss_popups(max_rounds=2)
                continue
        # 2) 检测可领取按钮（只要出现任一，就认为倒计时结束）
        claim_any = (ocr_find_mid_first(["领取奖励", "确认领取"])
                     or ocr_find_mid_first(["领取成功", "立即领取"]))
        if claim_any:
            log(f"  检测到可领取按钮 '{claim_any.get('text','')}'，倒计时真正结束，进入领取阶段")
            return True
        # 3) OCR 看倒计时文案，用于日志
        cd_hit = ocr_find_text(COUNTDOWN_KEYWORDS, rect=REGION_FULL, timeout=0)
        if cd_hit:
            text = cd_hit.get("text", "")
            sec = None
            for ch in text:
                if ch.isdigit():
                    sec = int(ch)
                    break
            if sec is not None and sec != last_sec:
                log(f"  广告倒计时中... {text}")
                last_sec = sec
        time.sleep(1.5)
    log(f"  广告等待超时 ({timeout}s)，或已达最大继续观看次数 {continue_count}，强行进入领取阶段")
    return False


# ============== 阶段五：领取奖励 ==============

def claim_reward() -> int:
    """
    按真实业务流程，循环点击「继续观看」「领取成功」「领取奖励」三个按钮：
    【为什么要多轮循环？】因为：
      - 广告倒计时结束 → 先出右上角「领取成功」→ **要点它**
      - 点完「领取成功」 → 才弹出中间弹窗的「领取奖励」→ **要点它**
      - 任何阶段中断广告时，会弹出二选一「继续观看 + 领取奖励」→ **优先点继续观看**（返回 -1 让上层继续等广告）
    所以不能只点一次就退出，要最多 6 轮循环，每轮按优先级：
      轮内优先级：
        1) 继续观看        → 点了直接返回 -1（拿多倍，继续看广告）
        2) 领取奖励        → 中间弹窗大按钮，优先级高于顶部「领取成功」
        3) 领取成功/立即领取 → 顶部小按钮，点了后会弹出领取奖励弹窗（下一轮命中）
    返回值（int）：
       1  = 本轮至少成功点了 1 个领取类按钮（领取成功 或 领取奖励）
       0  = 全程没找到任何可点击按钮
      -1  = 检测到并点击了「继续观看」，调用者应返回阶段四继续等新广告倒计时
    """
    log("阶段五：领取奖励（多轮循环点击）")
    claimed_any = False
    MAX_ROUNDS = 6
    # 记录连续空转次数，防止死循环
    idle_rounds = 0

    for rnd in range(1, MAX_ROUNDS + 1):
        log(f"  [领取轮次 {rnd}/{MAX_ROUNDS}]")

        # 优先级 1: 继续观看（只要出现就点，直接返回 -1）
        if check_and_click_continue_watching():
            log("  检测到继续观看并已点击，返回阶段四继续看新一轮广告")
            return -1

        # 优先级 2: 领取奖励（中间弹窗绿色大按钮）—— 因为它是确认弹窗，通常点一下就完
        reward_btn = ocr_find_mid_first(["领取奖励", "确认领取", "确认", "好的", "知道了"])
        if reward_btn:
            safe_click(reward_btn["center_x"], reward_btn["center_y"],
                       f"领取奖励/确认弹窗 '{reward_btn.get('text', '')}'")
            claimed_any = True
            idle_rounds = 0
            time.sleep(2)
            # 继续下一轮：检测点完后有没有弹继续观看，或另一个确认弹窗
            continue

        # 优先级 3: 领取成功 / 立即领取（顶部小按钮）—— 点了它会弹出上面的「领取奖励」
        success_btn = ocr_find_mid_first(["领取成功", "立即领取"])
        if success_btn:
            safe_click(success_btn["center_x"], success_btn["center_y"],
                       f"领取成功/立即领取 '{success_btn.get('text', '')}'")
            claimed_any = True
            idle_rounds = 0
            time.sleep(2)
            # 继续下一轮：点完这个应该会弹出「领取奖励」弹窗
            continue

        # 本轮没点任何按钮 → 空转
        idle_rounds += 1
        log(f"  本轮未找到可点击按钮（连续空转 {idle_rounds} 次）")
        if idle_rounds >= 2:
            log("  连续 2 轮没点到按钮，退出领取循环")
            break
        time.sleep(1)

    # 最后做一次兜底弹窗清理（奖励说明弹窗 / 广告残留弹窗）
    dismiss_popups(max_rounds=3)
    return 1 if claimed_any else 0


# ============== 主流程 ==============

def single_ad_cycle(cycle_idx: int) -> bool:
    """
    单轮看广告领时长完整流程
    返回: 是否成功完成一轮（含至少 1 次领取成功）
    内部支持"继续观看"循环：点了"继续观看"就回到阶段四继续等新广告倒计时
    """
    log("\n" + "#" * 60)
    log(f"### 开始第 {cycle_idx} 轮广告流程 ###")
    log("#" * 60)
    try:
        # 3. 监测右上角"免"字按钮并进入广告
        if not wait_for_mian_button(timeout=60):
            log(f"第 {cycle_idx} 轮：未等到'免'字按钮，可能无广告名额或按钮未出现")
            dismiss_popups(max_rounds=3)
            return False
        # 进入广告界面后，再做一次弹窗清理
        dismiss_popups(max_rounds=3)
        # 4 & 5 & 6. 大循环：倒计时 → 尝试领取；若领取时点了"继续观看"则重新等下一轮倒计时
        #    最多 8 次子循环（包含"继续观看"的嵌套广告），超过强制领取
        MAX_SUB_LOOP = 8
        any_success = False
        for sub in range(1, MAX_SUB_LOOP + 1):
            log(f"  --- 子流程 {sub}/{MAX_SUB_LOOP}: 等待广告倒计时 ---")
            wait_ad_countdown(timeout=30)
            dismiss_popups(max_rounds=2)
            log(f"  --- 子流程 {sub}/{MAX_SUB_LOOP}: 尝试领取奖励 ---")
            claim_res = claim_reward()
            if claim_res == 1:
                log(f"  子流程 {sub}/{MAX_SUB_LOOP}: 领取成功！")
                any_success = True
                # 领取成功后，再看界面上有没有多一轮的"继续观看"机会——有就继续，没有就结束本轮
                if check_and_click_continue_watching():
                    log("  领取后又检测到继续观看按钮，开启多倍奖励子流程...")
                    continue
                else:
                    break
            elif claim_res == -1:
                log(f"  子流程 {sub}/{MAX_SUB_LOOP}: 领取前点了继续观看，继续等待新一轮广告...")
                continue
            else:
                # claim_res == 0：没找到按钮，再做一次弹窗清理后退出子循环
                log(f"  子流程 {sub}/{MAX_SUB_LOOP}: 未找到领取按钮，尝试最后清理弹窗...")
                dismiss_popups(max_rounds=3)
                # 即使 claim_res=0，如果还能点"继续观看"就不退出
                if check_and_click_continue_watching():
                    continue
                break
        log(f"第 {cycle_idx} 轮：最终结果 = {'成功（至少领取 1 次）' if any_success else '未检测到可领取状态'}")
        return any_success
    except Exception as e:
        log(f"第 {cycle_idx} 轮流程异常: {e}")
        traceback.print_exc()
        return False


def main():
    """脚本入口主函数"""
    log("🎵 汽水音乐自动看广告脚本启动")
    log(f"   最大循环次数: {MAX_LOOP_COUNT}   OCR 引擎: {OCR_ENGINE}")
    try:
        # 0. 初始化
        init_regions()
        Ocr.set_engine(OCR_ENGINE)
        # 1. 启动 App
        if not launch_app():
            log("❌ 无法启动汽水音乐 App，脚本终止")
            return
        # 启动后先跳过开屏广告（右上角倒计时跳过按钮）
        skip_splash_ad(timeout=10)
        # 再清理一轮弹窗
        dismiss_popups(max_rounds=5)
        # 主循环：一轮一轮看广告
        success_count = 0
        for idx in range(1, MAX_LOOP_COUNT + 1):
            result = single_ad_cycle(idx)
            if result:
                success_count += 1
            # 轮次间隔 & 兜底清理
            log(f"  当前完成: {success_count}/{idx} 轮成功")
            dismiss_popups(max_rounds=3)
            # 如果连续 3 轮都失败，可能当日额度用完，提示并退出
            if idx >= 3 and success_count == 0:
                log("⚠️  连续 3 轮未成功，可能当日广告名额已用完，脚本退出")
                break
            time.sleep(LOOP_INTERVAL)
        # 结束
        log("=" * 60)
        log(f"✅ 脚本运行结束，共成功领取 {success_count} 次奖励")
        try:
            notify(f"汽水音乐脚本完成，成功 {success_count} 次")
        except Exception:
            pass
    except Exception as e:
        log(f"❌ 脚本主流程异常: {e}")
        traceback.print_exc()
    finally:
        log("脚本退出")


# ============== 入口：AScript 工程约定顶层直接执行 ==============
main()
