# -*- coding: utf-8 -*-
# og-cover 合成：AI 背景（无字） + PIL 中文 → 1200×630 标准分享卡
from PIL import Image, ImageDraw, ImageFont

SRC = "og-cover-source.png"
OUT = "../docs/niuxiong-zijiantai/assets/img/og-cover.png"
W, H = 1200, 630

base = Image.open(SRC).convert("RGB")  # 1536×1024
# 裁 1200:630 比例（保留温度计所在的横向中段），再缩放
crop = base.crop((168, 197, 168 + 1200, 197 + 630)).resize((W, H), Image.LANCZOS)

d = ImageDraw.Draw(crop)
def font(sz, bold=True):
    p = "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"
    return ImageFont.truetype(p, sz)

# 顶部主标题区（背景留白区）
d.text((72, 74), "恒福丨水木清华", font=font(96), fill="#ffffff")
d.text((76, 196), "每日牛熊温度与今日建议仓位", font=font(40, bold=False), fill="#c9d1d9")
d.text((76, 252), "A股 / 港股 / 美股 · 四维打分 · 公式全部公开", font=font(30, bold=False), fill="#8b949e")

# 细分割线
d.rectangle([76, 330, 320, 334], fill="#d29922")

# 底部小字（免责+署名）
foot = "主理人 萧沐川（临沂润泽配货站） · 个人投资研究公开分享 · 仅供参考，不是投资建议"
d.text((76, H - 44), foot, font=font(21, bold=False), fill="#7d8590")

crop.save(OUT, "PNG")
print("saved", OUT, crop.size)
