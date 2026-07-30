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
from ascript.ios import action  # type: ignore
from ascript.ios.system import R, app_start, screen_size, notify  # type: ignore
from ascript.ios.screen import Ocr, FindImages  # type: ignore

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
# 直播间关闭按钮模板图是否存在（启动时检查一次）
HAS_LIVE_ROOM_TEMPLATE = False


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
    """根据屏幕尺寸初始化搜索区域，并检查资源文件"""
    global REGION_TOP_RIGHT, REGION_FULL, HAS_LIVE_ROOM_TEMPLATE
    w, h = screen_size() or (1080, 1920)
    log(f"屏幕尺寸: {w} x {h}")
    # 右上角区域：x 从 60%~100%，y 从 0%~20%
    REGION_TOP_RIGHT = [int(w * 0.6), 0, w, int(h * 0.2)]
    REGION_FULL = [0, 0, w, h]
    # 检查直播间关闭按钮模板图是否存在
    import os as _os
    template_path = R.img("img_zhibojian-close01.png")
    HAS_LIVE_ROOM_TEMPLATE = _os.path.exists(template_path)
    log(f"直播间关闭按钮模板图: {'✅ 存在 ' + template_path if HAS_LIVE_ROOM_TEMPLATE else '❌ 不存在（将使用 OCR 兜底方案）'}")


# ============== 阶段一：启动 App ==============

def launch_app() -> bool:
    """启动汽水音乐 App（发指令后立即返回，不阻塞，让 skip_splash_ad 能立刻跟上）"""
    log("=" * 50)
    log("阶段一：启动汽水音乐 App")
    try:
        if APP_BUNDLE_ID:
            ok = app_start(bundle_id=APP_BUNDLE_ID)
        else:
            ok = app_start(name=APP_NAME)
        if ok:
            log("App 启动指令已发送，立即开始监控开屏跳过...")
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


def skip_splash_ad(timeout=5) -> bool:
    """
    启动 App 后立即检测并跳过开屏广告（paddleocr 精准识别版）
    使用 Ocr.paddleocr 在右上角小区域精准识别「跳过」文字，识别率高 (~98%)。
    rect 按屏幕比例动态计算：x:80%~97%, y:6%~10%。
    """
    log("阶段一B：检测并跳过开屏广告（paddleocr 精准识别中...）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 右上角跳过按钮区域（经实测在 x:80%~97%, y:6%~10% 范围）
    rect_skip = [int(w * 0.80), int(h * 0.06), int(w * 0.97), int(h * 0.10)]

    deadline = time.time() + timeout
    scan_count = 0

    while time.time() < deadline:
        scan_count += 1
        try:
            # 核心：paddleocr 精准匹配「跳过」文字
            results = Ocr.paddleocr(rect=rect_skip, pattern=r"跳过")
            if results and isinstance(results, list) and len(results) > 0:
                for item in results:
                    cx = item.get("center_x", 0)
                    cy = item.get("center_y", 0)
                    if cx > 0 and cy > 0:
                        text = item.get("text", "")
                        conf = item.get("confidence", 0)
                        log(f"  [扫描#{scan_count} paddleocr 命中] '{text}' 置信度={conf:.2f} ({cx},{cy})")
                        action.click(cx, cy)
                        time.sleep(0.2)
                        return True
        except Exception as e:
            log(f"  扫描#{scan_count} paddleocr 异常: {e}")

        time.sleep(0.1)
    log(f"  扫描结束（共 {scan_count} 次），未检测到开屏跳过按钮")
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
    from ascript.ios.system import screen_size as _ss  # type: ignore
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


def paddle_find_first(pattern, rect, log_label=""):
    """
    用 Ocr.paddleocr 在指定小区域精准识别关键词，返回第一个有效命中结果 dict 或 None。
    比 vision 引擎的 Ocr.find 更快、识别率更高（用户推荐方案）。
    pattern 是正则；rect = [x1, y1, x2, y2]。
    """
    try:
        results = Ocr.paddleocr(rect=rect, pattern=pattern)
        if results and isinstance(results, list):
            for item in results:
                cx = item.get("center_x", 0)
                cy = item.get("center_y", 0)
                if cx > 0 and cy > 0:
                    if log_label:
                        log(f"  [{log_label}] '{pattern}' -> '{item.get('text','')}' "
                            f"置信度={item.get('confidence',0):.2f} ({cx},{cy})")
                    return item
    except Exception as e:
        log(f"  paddle_find '{pattern}' 异常: {e}")
    return None


# 【弹窗内优先点击的按钮】出现这些按钮时，不要打叉关闭，而是优先点击它们
#   - 领取奖励 / 领取成功 是用户明确要求点的
#   - 注意："继续观看"不在这里！它有"中间区(恢复广告)"和"底部(下载诱导)"两种，
#           必须由 check_and_click_continue_watching 在中间区单独识别，避免误点底部下载按钮
PRIORITY_CLICK_KEYWORDS = ["领取奖励", "领取成功", "立即领取", "确认领取"]


def close_membership_popup() -> bool:
    """
    检测并关闭"续费会员"弹窗（开屏进入播放界面后唯一需要处理的弹窗）。
    判定特征：底部出现"元开通"文字（如"12元开通"、"连续包月9元开通"）。
    处理：点击弹窗外部遮罩区域（屏幕中上方）关闭弹窗。
          不用右滑——右滑会触发 iOS 边缘返回手势把 App 切到后台。
    返回：是否检测到并执行了关闭。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 用户实测 [56,2435,1223,2676] @ 1284x2778
    # 约为 x:4.4%~95.3%, y:87.7%~96.3%，按屏幕比例动态计算
    bottom_rect = [int(w * 0.044), int(h * 0.877), int(w * 0.953), int(h * 0.963)]
    try:
        results = Ocr.paddleocr(rect=bottom_rect, pattern=r"元开通")
        if results and isinstance(results, list) and len(results) > 0:
            item = results[0]
            log(f"  [续费会员弹窗] 检测到底部 '{item.get('text','')}'，点击弹窗外部关闭")
            # 点击弹窗上方遮罩区域（y:30% 处，弹窗在 y:87% 以下）
            try:
                action.click(int(w * 0.5), int(h * 0.30))
            except Exception as e:
                log(f"  点击关闭异常: {e}")
            time.sleep(1.2)
            return True
    except Exception as e:
        log(f"  续费会员弹窗检测异常: {e}")
    return False

# 兼容旧调用名
check_and_back_from_membership_page = close_membership_popup


def check_and_close_thirdparty_download() -> bool:
    """
    检测是否跳转到了第三方应用下载页面（广告倒计时结束、出现"领取成功"后可能触发）。
    判定特征：左上角出现"完成"按钮（App Store 下载页 / 广告落地页的关闭入口）。
    处理：直接点击"完成"关闭该页面，回到汽水音乐。
    返回：是否检测到第三方下载页（True=已点击"完成"尝试关闭）。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 左上角"完成"按钮区域（用户实测 [29,211,237,315] @ 1284x2778，
    # 约为 x:2%~18%, y:7.5%~11.3%，按屏幕比例动态计算）
    rect_done = [int(w * 0.02), int(h * 0.075), int(w * 0.19), int(h * 0.115)]
    try:
        results = Ocr.paddleocr(rect=rect_done, pattern=r"完成")
        if results and isinstance(results, list) and len(results) > 0:
            item = results[0]
            cx = item.get("center_x", 0)
            cy = item.get("center_y", 0)
            if cx > 0 and cy > 0:
                log(f"  [第三方下载页] 检测到左上角 '完成'，点击关闭 ({cx},{cy})")
                safe_click(cx, cy, "'完成'按钮")
                time.sleep(1.0)
                return True
    except Exception as e:
        log(f"  第三方下载页检测异常: {e}")
    return False


def dismiss_popups(max_rounds=3) -> int:
    """
    弹窗清理（精简版）：只处理"续费会员"弹窗（底部"元开通"）。
    其他弹窗目前未发现，不做任何处理（不查 POPUP_KEYWORDS、不找关闭按钮、不点屏幕中心）。
    返回：已处理的弹窗数量
    """
    log("阶段二：弹窗清理（仅处理续费会员弹窗）")
    handled = 0
    for _ in range(max_rounds):
        if close_membership_popup():
            handled += 1
            time.sleep(1.0)
            continue
        break
    if handled == 0:
        log("  未检测到续费会员弹窗，无需清理。")
    log(f"弹窗清理结束，共处理 {handled} 个")
    return handled


# ============== 阶段三：监测"免"字按钮并进入广告 ==============


def light_background_cleanup() -> bool:
    """
    轻量级背景清理：只检测续费会员弹窗（底部"元开通"）→ 右滑关闭。
    其他弹窗不处理。paddleocr 小区域识别 ~0.6s，不阻塞主识别节奏。
    """
    return close_membership_popup()


def _detect_membership_popup(rect_pay) -> bool:
    """内部辅助：检测底部是否有'元开通'续费会员弹窗。返回 True=有弹窗。"""
    try:
        results = Ocr.paddleocr(rect=rect_pay, pattern=r"元开通")
        return bool(results and isinstance(results, list) and len(results) > 0)
    except Exception:
        return False


def wait_for_mian_button(timeout=60, allow_mian=True) -> bool:
    """
    监测进广告入口。按 allow_mian 决定是否搜索右上角"免"字：
      - allow_mian=True  (第1轮/开屏后场景) ：
          1) 先搜"立即解锁"/"立即领取"弹窗按钮 → 点击
          2) 再搜右上角"免"字 → 点击。
             点击策略：检测到有"元开通"续费会员弹窗 → 最多重试 2 次（点击+验证）；
                      没有续费会员弹窗 → 直接点 1 次就返回（不再验证/重试）。
          3) 都没有 → 每 8s 清理一次续费会员弹窗。
      - allow_mian=False (第2轮及以后/进入广告后回到播放界面)：
          只搜 1) 和 3)，**不搜"免"字**（免字只在开屏后出现，后续轮次根本没有）。

    timeout: 最长等待秒数（0 表示只检查一次不等待）
    返回: 是否成功点击进入广告
    """
    if allow_mian:
        log("阶段三：监测进广告入口（优先'立即解锁/领取'弹窗，其次'免'字）")
    else:
        log("阶段三：监测进广告入口（仅'立即解锁/领取'弹窗，不再找'免'字）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    rect_mian = [int(w * 0.65), int(h * 0.04), int(w * 0.92), int(h * 0.12)]
    rect_unlock = [int(w * 0.029), int(h * 0.52), int(w * 0.981), int(h * 0.982)]
    rect_pay = [int(w * 0.044), int(h * 0.877), int(w * 0.953), int(h * 0.963)]

    deadline = time.time() + timeout if timeout > 0 else 0
    check_count = 0
    last_err_log = 0.0
    last_cleanup = 0.0
    CLEANUP_INTERVAL = 8
    REVERIFY_WAIT = 0.7

    while True:
        check_count += 1

        # ========== 1) 最高优先："立即解锁"/"立即领取"（弹窗进广告按钮） ==========
        unlock_hit = None
        try:
            results = Ocr.paddleocr(rect=rect_unlock, pattern=r"立即(解锁|领取)")
            if results and isinstance(results, list) and len(results) > 0:
                item = results[0]
                cx = item.get("center_x", 0)
                cy = item.get("center_y", 0)
                if cx > 0 and cy > 0:
                    unlock_hit = (item, cx, cy)
        except Exception as e:
            if time.time() - last_err_log > 5:
                log(f"  paddleocr 识别异常: {e}")
                last_err_log = time.time()

        if unlock_hit is not None:
            item, cx, cy = unlock_hit
            text = item.get("text", "")
            conf = item.get("confidence", 0)
            log(f"  [扫描#{check_count} 命中] '{text}' 置信度={conf:.2f} ({cx},{cy}) → 点击进入广告")
            safe_click(cx, cy, f"'{text}'按钮")
            time.sleep(1.5)
            return True

        # ========== 2) 只有 allow_mian=True 时才搜"免"字按钮 ==========
        if allow_mian:
            mian_hit = None
            try:
                results = Ocr.paddleocr(rect=rect_mian, pattern=r"免")
                if results and isinstance(results, list) and len(results) > 0:
                    item = results[0]
                    cx = item.get("center_x", 0)
                    cy = item.get("center_y", 0)
                    if cx > 0 and cy > 0:
                        mian_hit = (item, cx, cy)
            except Exception as e:
                if time.time() - last_err_log > 5:
                    log(f"  paddleocr 识别异常: {e}")
                    last_err_log = time.time()

            if mian_hit is not None:
                item, cx, cy = mian_hit
                text = item.get("text", "")
                conf = item.get("confidence", 0)

                # 【关键策略】先看有没有续费会员弹窗，决定重试次数：
                #   有弹窗 → MAX_RETRY = 2（点击+验证，最多2次）
                #   无弹窗 → MAX_RETRY = 1（直接点一次，不再验证浪费时间）
                has_popup = _detect_membership_popup(rect_pay)
                MAX_RETRY = 2 if has_popup else 1
                log(f"  [扫描#{check_count} 命中] '免' -> '{text}' 置信度={conf:.2f} ({cx},{cy})"
                    f"  检测到续费弹窗={'是' if has_popup else '否'} → 重试上限={MAX_RETRY}")

                for attempt in range(1, MAX_RETRY + 1):
                    log(f"  [点击尝试 {attempt}/{MAX_RETRY}] '免'字按钮 ({cx},{cy})")
                    safe_click(cx, cy, f"'免'字按钮(尝试{attempt})")

                    # 只有有弹窗/MAX_RETRY>1 时才验证是否生效，否则直接成功返回
                    if MAX_RETRY == 1:
                        log(f"  [成功] 无续费会员弹窗，点击 1 次即生效，进入广告")
                        time.sleep(1.0)
                        return True

                    # MAX_RETRY>=2：验证免字是否消失
                    time.sleep(REVERIFY_WAIT)
                    verify_hit = None
                    try:
                        vr = Ocr.paddleocr(rect=rect_mian, pattern=r"免")
                        if vr and isinstance(vr, list) and len(vr) > 0:
                            vi = vr[0]
                            vx = vi.get("center_x", 0)
                            vy = vi.get("center_y", 0)
                            if vx > 0 and vy > 0:
                                verify_hit = (vx, vy, vi.get("confidence", 0))
                    except Exception:
                        verify_hit = None

                    if verify_hit is None:
                        log(f"  [成功] 点击后'免'字消失（尝试 {attempt} 次生效）")
                        time.sleep(0.8)
                        return True

                    vx, vy, vconf = verify_hit
                    log(f"  [未生效] 点击后'免'字仍在屏上 ({vx},{vy}) 置信度={vconf:.2f}，继续重试点击")

                log(f"  [重试耗尽] 连续 {MAX_RETRY} 次点击'免'字未触发跳转，本轮放弃")

        # ========== 3) 都没命中 → 每 8s 清理一次续费会员弹窗 ==========
        now = time.time()
        if now - last_cleanup >= CLEANUP_INTERVAL:
            try:
                light_background_cleanup()
            except Exception as e:
                log(f"  背景清理异常: {e}")
            last_cleanup = now

        if timeout > 0 and time.time() >= deadline:
            log(f"  等待进广告入口超时 ({timeout}s)，本轮跳过")
            return False
        if timeout == 0:
            log("  单次检查：未发现进广告入口")
            return False
        time.sleep(0.2)


# ============== 阶段四：等待广告倒计时结束 ==============

COUNTDOWN_KEYWORDS = [
    "秒后可领取", "秒后领取", "秒后关闭", "秒后获得",
   ]


def check_and_click_continue_watching() -> bool:
    """
    检测并点击"继续观看"按钮——【仅限屏幕中间显眼位置】。

    重要区分（两种"继续观看"绝不能混）：
      - 中间显眼区（y:25%~68%）：广告中途误点关闭后弹出的恢复对话框 → 该点，继续看广告
      - 屏幕底部：广告商诱导下载应用按钮（如"继续观看下载红果短剧"）→ 绝不点，会跳下载页

    所以只在中间区域检测，绝不在底部/全屏检测。
    返回 True 表示已点击中间的"继续观看"。
    """
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 中间显眼区域（用户实测 [96,706,1184,1889] @ 1284x2778，
    # 约为 x:7.5%~92%, y:25.4%~68%，按屏幕比例动态计算）
    rect_continue = [int(w * 0.07), int(h * 0.25), int(w * 0.93), int(h * 0.68)]
    item = paddle_find_first(r"继续观看", rect_continue, "继续观看(中间区)")
    if item:
        ok = safe_click(item["center_x"], item["center_y"], "继续观看(中间区)")
        if ok:
            time.sleep(2.5)
            return True
    return False


def wait_ad_countdown(timeout=30) -> bool:
    """
    阶段四：在广告界面等待倒计时结束。
    支持两种广告类型：
      1) 视频广告：倒计时结束 → 右上角出现"领取成功" → 返回，交给 claim_reward 处理
      2) 直播间广告：无倒计时，直接进入直播间 → 右上角显示"更多直播" → 
         点击关闭按钮(×) → 关闭后右上角出现"领取成功" → 返回
    轮询优先级：领取成功 > 更多直播(直播间需关闭) > 秒后可领奖励(仅打印日志)
    """
    log("阶段四：等待广告倒计时结束（支持视频广告 & 直播间广告）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 右上角"领取成功"区域（视频广告结束 或 直播间关闭后）
    rect_claim_top = [int(w * 0.55), int(h * 0.03), w, int(h * 0.14)]
    # 右上角倒计时文案区域（仅打印日志）
    rect_countdown = [int(w * 0.58), int(h * 0.045), int(w * 0.97), int(h * 0.09)]
    # 直播间底部区域（检测是否为直播间广告）
    # 用户实测 [118,1691,1170,2183] @ 1284x2778 → x:9.2%~91.1%, y:60.9%~78.6%
    rect_live_room = [int(w * 0.092), int(h * 0.609), int(w * 0.911), int(h * 0.786)]
    # 直播间右上角"更多直播"区域（检测是否在直播间内，需要关闭）
    # 用户实测 [890,274,1247,403] @ 1284x2778 → x:69.4%~97.1%, y:9.9%~14.5%
    rect_more_live = [int(w * 0.694), int(h * 0.099), int(w * 0.971), int(h * 0.145)]
    # 直播间右上角关闭按钮(×)区域（用 FindImages 匹配模板图）
    # 用户实测 [795,153,1284,277] @ 1284x2778 → x:61.9%~100%, y:5.5%~10%
    rect_close_btn = [int(w * 0.619), int(h * 0.055), w, int(h * 0.10)]

    deadline = time.time() + timeout
    last_sec = -1
    checks = 0
    is_live_room_logged = False

    while time.time() < deadline:
        checks += 1

        # ========== 1) 最高优先：检测"领取成功"是否出现 ==========
        # （视频广告倒计时结束，或 直播间关闭后 都会出现）
        hit_claim = paddle_find_first(r"领取成功", rect_claim_top, "倒计时结束标志")
        if hit_claim:
            log(f"  检测到'领取成功'出现（轮询 {checks} 次）→ 返回，交给 claim_reward 执行两步点击")
            return True

        # ========== 2) 次高优先：检测是否在直播间内（需要关闭） ==========
        # 先快速判断是否是直播间（首次发现时打印日志）
        if not is_live_room_logged:
            live_check = paddle_find_first(r"直播间", rect_live_room, "直播间检测")
            if live_check:
                log(f"  检测到直播间广告（轮询 {checks} 次）→ 将尝试关闭直播间")
                is_live_room_logged = True

        # 检测右上角是否有"更多直播"文字（确认在直播间内，需要关闭）
        more_live_hit = paddle_find_first(r"更多直播", rect_more_live, "直播间识别")
        if more_live_hit:
            log(f"  命中'更多直播' → 确认在直播间内，尝试点击关闭按钮...")
            close_clicked = False
            
            # 优先：使用 FindImages 匹配关闭按钮模板图（如果模板存在）
            if HAS_LIVE_ROOM_TEMPLATE:
                try:
                    template_path = R.img("img_zhibojian-close01.png")
                    result = FindImages.find(template_path, rect=rect_close_btn)
                    if result:
                        cx = result.get("center_x", 0)
                        cy = result.get("center_y", 0)
                        conf = result.get("confidence", 0)
                        log(f"  FindImages 匹配到关闭按钮 (置信度={conf:.2f}) @ ({cx},{cy}) → 点击")
                        safe_click(cx, cy, f"直播间关闭按钮(模板匹配,置信度={conf:.2f})")
                        time.sleep(1.5)
                        log(f"  已点击关闭按钮（模板匹配），继续等待'领取成功'出现...")
                        close_clicked = True
                except Exception as e:
                    log(f"  FindImages 匹配异常: {e}，改用 OCR 方案")
            
            # 兜底：使用 OCR 在关闭按钮区域识别 × 符号
            if not close_clicked:
                log(f"  使用 OCR 兜底识别关闭按钮...")
                close_hit = paddle_find_first(r"[×✕✖]", rect_close_btn, "关闭按钮OCR")
                if close_hit:
                    cx = close_hit.get("center_x", 0)
                    cy = close_hit.get("center_y", 0)
                    log(f"  OCR 命中关闭符号 @ ({cx},{cy}) → 点击")
                    safe_click(cx, cy, "关闭按钮(OCR)")
                    time.sleep(1.5)
                    log(f"  已点击关闭按钮（OCR），继续等待'领取成功'出现...")
                    close_clicked = True
            
            if close_clicked:
                continue  # 关闭后继续循环，等待领取成功出现
            else:
                log(f"  未找到关闭按钮，本轮跳过")

        # ========== 3) 最低优先：倒计时文案 → 仅打印日志 ==========
        cd_hit = paddle_find_first(r"秒后可领奖励", rect_countdown, "倒计时")
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

        time.sleep(0.8)

    log(f"  等待超时 ({timeout}s)，'领取成功'未出现（本轮可能没有广告可领）")
    return False


# ============== 阶段五：领取奖励 ==============

def claim_reward() -> int:
    """
    领取奖励流程（确定性两步走，用户已捋清，无多余分支）：

    确定业务链：
      倒计时结束 → 右上角出现"领取成功" → 点击它
        → **肯定会**弹出中间对话框包含"领取奖励"按钮
          → 点击"领取奖励" → **肯定会**进入新一轮广告（下一轮 wait_ad_countdown）

    所以完全不需要其他判断（继续观看、第三方下载页、立即领取…都不处理）。
    失败唯一情况：超时没找到"领取成功"或"领取奖励"。

    返回值：1=两步都成功，已进入下一轮广告；0=超时失败
    """
    log("阶段五：领取奖励（确定两步：点领取成功 → 点领取奖励 → 进入下一轮广告）")
    from ascript.ios.system import screen_size as _ss  # type: ignore
    w, h = _ss() or (1080, 1920)
    # 右上角"领取成功"专属区（倒计时结束标志）
    rect_claim_top = [int(w * 0.55), int(h * 0.03), w, int(h * 0.14)]
    # "领取奖励"弹窗按钮专属区（用户实测 [175,712,1108,1923]，超出绝不点）
    rect_reward_btn = [int(w * 0.13), int(h * 0.25), int(w * 0.87), int(h * 0.70)]

    # ========== 第一步：等并点右上角"领取成功" ==========
    log("  [步骤 1/2] 等待右上角出现'领取成功'...")
    hit_claim = None
    deadline1 = time.time() + 20  # 倒计时刚结束，领取成功按钮应该很快出现，20s 足够
    checks1 = 0
    while time.time() < deadline1:
        checks1 += 1
        hit_claim = paddle_find_first(r"领取成功", rect_claim_top, "领取成功(右上角)")
        if hit_claim:
            break
        time.sleep(0.35)
    if not hit_claim:
        log(f"  [失败] 20s 内未等到右上角'领取成功'（轮询 {checks1} 次），本轮放弃")
        return 0
    cx1 = hit_claim["center_x"]
    cy1 = hit_claim["center_y"]
    log(f"  [命中] '领取成功' @ ({cx1:.1f},{cy1:.1f}) 置信度={hit_claim.get('confidence',0):.2f} → 点击")
    safe_click(cx1, cy1, "'领取成功'(右上角)")

    # ========== 第二步：点完"领取成功"，肯定会弹"领取奖励"对话框，等它出现并点击 ==========
    log("  [步骤 2/2] 等待中间弹窗出现'领取奖励'按钮...")
    time.sleep(0.6)  # 弹窗动画留一点时间（不要上来就找，大概率第一帧还没画出来）
    hit_reward = None
    deadline2 = time.time() + 15  # 点击后弹窗 15s 内肯定出来
    checks2 = 0
    while time.time() < deadline2:
        checks2 += 1
        hit_reward = paddle_find_first(r"领取奖励", rect_reward_btn, "领取奖励(弹窗)")
        if hit_reward:
            break
        time.sleep(0.35)
    if not hit_reward:
        log(f"  [失败] 点击'领取成功'后 15s 内未等到'领取奖励'弹窗（轮询 {checks2} 次），本轮放弃")
        return 0
    cx2 = hit_reward["center_x"]
    cy2 = hit_reward["center_y"]
    log(f"  [命中] '领取奖励' @ ({cx2:.1f},{cy2:.1f}) 置信度={hit_reward.get('confidence',0):.2f} → 点击（进入下一轮广告）")
    safe_click(cx2, cy2, "'领取奖励'(弹窗)")
    time.sleep(1.5)  # 给 App 跳转新广告一点时间，下一轮 wait_ad_countdown 接着等

    log("  [成功] 两步领取完成，自动进入下一轮广告倒计时")
    return 1


# ============== 主流程 ==============

def run_ad_loop() -> int:
    """
    核心无限循环：用户手动进入广告后，脚本负责
      等广告倒计时结束 → 点"领取成功" → 点"领取奖励" → 自动进入下一轮广告 → 循环
    每次成功领取计 1 次，累计到 success_count。
    返回累计成功次数（失败时也返回已拿到的次数）。
    """
    log("\n" + "#" * 60)
    log("🎯 进入核心广告领取循环（无限循环，按 Ctrl+C 或停止项目即可退出）")
    log("#" * 60)
    log("   ⚠️  请在 App 上手动进入一个广告（点右上角'免'字或'立即解锁'弹窗），脚本会自动接管后续所有轮次")
    success_count = 0
    round_idx = 0
    MAX_IDLE_ROUNDS = 10  # 连续 10 轮没领到，自动退出（可能当天额度用完）
    idle_count = 0

    while True:
        round_idx += 1
        log(f"\n---- 第 {round_idx} 轮广告循环 ----")

        # 步骤 1：等广告倒计时结束（30s 超时）
        got_ad = wait_ad_countdown(timeout=30)
        if not got_ad:
            idle_count += 1
            log(f"  第 {round_idx} 轮：等超时，未检测到广告倒计时结束（连续 {idle_count}/{MAX_IDLE_ROUNDS} 轮无广告）")
            if idle_count >= MAX_IDLE_ROUNDS:
                log(f"  ⚠️  连续 {MAX_IDLE_ROUNDS} 轮没领到广告，可能当日额度已用完，自动退出循环")
                break
            time.sleep(3)
            continue

        # 步骤 2：两步领取（点领取成功 → 点领取奖励 → 自动进下一轮广告）
        claim_res = claim_reward()
        if claim_res == 1:
            success_count += 1
            idle_count = 0
            log(f"  ✅ 第 {round_idx} 轮领取成功！累计成功次数 = {success_count}")
        else:
            idle_count += 1
            log(f"  ⚠️  第 {round_idx} 轮领取失败（连续 {idle_count}/{MAX_IDLE_ROUNDS} 轮领取失败）")
            if idle_count >= MAX_IDLE_ROUNDS:
                log(f"  ⚠️  连续 {MAX_IDLE_ROUNDS} 轮领取失败，自动退出循环")
                break

        # 每轮结束后短暂休息，避免过快
        time.sleep(1)

    return success_count


def main():
    """脚本入口主函数 —— 精简版"""
    log("🎵 汽水音乐自动看广告脚本（精简版）启动")
    log(f"   核心功能：跳过开屏广告 → 等待用户手动进广告 → 无限循环领奖励")
    try:
        # 1. 初始化
        init_regions()
        Ocr.set_engine(OCR_ENGINE)
        # 2. 启动 App
        if not launch_app():
            log("❌ 无法启动汽水音乐 App，脚本终止")
            return
        # 3. 跳开屏广告
        skip_splash_ad(timeout=5)
        # 4. 核心循环（用户手动进广告后自动接管）
        total = run_ad_loop()
        # 5. 结束
        log("=" * 60)
        log(f"✅ 脚本运行结束，共成功领取 {total} 次奖励")
        try:
            notify(f"汽水音乐精简版完成，成功 {total} 次")
        except Exception:
            pass
    except Exception as e:
        log(f"❌ 脚本主流程异常: {e}")
        traceback.print_exc()
    finally:
        log("脚本退出")


# ============== 入口：AScript 工程约定顶层直接执行 ==============
main()
