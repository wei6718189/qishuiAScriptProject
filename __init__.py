# 导入系统资源模
from ascript.ios.system import R,device
# 导入动作模块
from ascript.ios.action import click,slide,home
# 导入节点检索模块
from ascript.ios.node import Selector,Node
# 导入图色检索模块
from ascript.ios import screen

print("Hello AS")


# 1. 导入找图功能模块
from ascript.ios.screen import FindImages
# 2. 导入资源管理模块，用于方便地引用本地图片
from ascript.ios.system import R
# 3. 导入动作模块，用于执行点击操作
from ascript.ios import action

# --- 核心逻辑开始 ---

# 4. 使用 FindImages.find 方法在屏幕上查找图片
#    - R.img("douyin.png"): 指定你本地保存的抖音图标文件名
#    - confidence=0.85: 设置匹配度阈值为 85%
qishuiyinyue_icon_position = FindImages.find(R.img("qishuiyinyue.png"), confidence=0.85)

# 5. 判断是否找到了图标
if qishuiyinyue_icon_position:
    # 6. 如果找到了，就使用 action.click 方法点击该坐标
    # 取出字典里的坐标
    pos = qishuiyinyue_icon_position
    action.click(pos["center_x"], pos["center_y"])
    print("成功找到并点击了汽水音乐图标！")
else:
    # 7. 如果没找到，可以在控制台打印信息，方便调试
    print("未找到汽水音乐图标，请检查图片或屏幕内容。")


