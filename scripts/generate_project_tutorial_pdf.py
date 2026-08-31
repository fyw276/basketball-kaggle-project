from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
OUTPUT = DOCS / 'smart_outfit_project_tutorial.pdf'
TMP_DIR = DOCS / '_tutorial_assets'
CN_FONT_NAME = 'TutorialCN'


def register_chinese_font() -> str:
    font_candidates = [
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/msyh.ttf',
        'C:/Windows/Fonts/NotoSansSC-VF.ttf',
        'C:/Windows/Fonts/simsun.ttc',
    ]
    for font_path in font_candidates:
        if Path(font_path).exists():
            pdfmetrics.registerFont(TTFont(CN_FONT_NAME, font_path))
            return CN_FONT_NAME
    raise FileNotFoundError('No usable Chinese font found in C:/Windows/Fonts')


def font(size: int, bold: bool = False):
    candidates = [
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/arialbd.ttf',
    ]
    names = [candidates[1], candidates[0]] if bold else [candidates[0], candidates[2]]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default()


def make_canvas(size=(1600, 900), bg='#F6F8FB'):
    return PILImage.new('RGB', size, bg)


def centered_text(draw, box, text, fill='#111827', size=40, bold=False):
    f = font(size, bold=bold)
    bbox = draw.multiline_textbbox((0, 0), text, font=f, spacing=8, align='center')
    x = box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) / 2
    y = box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) / 2
    draw.multiline_text((x, y), text, font=f, fill=fill, spacing=8, align='center')


def round_rect(draw, box, radius=28, fill='#FFFFFF', outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def create_login_mockup(path: Path):
    img = make_canvas()
    draw = ImageDraw.Draw(img)
    draw.ellipse((640, 60, 960, 380), fill='#E8F1F0')
    draw.ellipse((690, 110, 910, 330), outline='#A3C5C1', width=5)
    draw.line((690, 220, 910, 220), fill='#A3C5C1', width=4)
    draw.line((800, 110, 800, 330), fill='#A3C5C1', width=4)
    for x in range(720, 881, 30):
        draw.line((x, 115, x, 325), fill='#BFD7D4', width=2)
    for y in range(145, 296, 30):
        draw.line((705, y, 895, y), fill='#BFD7D4', width=2)

    centered_text(draw, (0, 380, 1600, 520), 'AI 穿搭，自由表达', size=54, bold=True)
    centered_text(draw, (0, 520, 1600, 590), '智能衣橱 · 虚拟试衣 · 风格自由', fill='#6B7280', size=30)

    round_rect(draw, (330, 620, 1270, 712), radius=44, fill='#FFFFFF', outline='#E5E7EB', width=3)
    round_rect(draw, (342, 630, 668, 702), radius=36, fill='#77AAA4')
    centered_text(draw, (342, 630, 668, 702), '登录', fill='#FFFFFF', size=30, bold=True)
    centered_text(draw, (668, 630, 1270, 702), '注册', fill='#9CA3AF', size=30, bold=True)

    round_rect(draw, (330, 760, 1270, 842), radius=32, fill='#FFFFFF', outline='#E5E7EB', width=2)
    draw.text((385, 786), '用户名 / 手机号', font=font(28), fill='#6B7280')
    round_rect(draw, (330, 870, 1270, 952), radius=32, fill='#FFFFFF', outline='#E5E7EB', width=2)
    draw.text((385, 896), '密码', font=font(28), fill='#6B7280')

    round_rect(draw, (330, 1040, 1270, 1140), radius=50, fill='#77AAA4')
    centered_text(draw, (330, 1040, 1270, 1140), '登录', fill='#FFFFFF', size=40, bold=True)

    draw.text((100, 85), '登录页示意', font=font(32, True), fill='#374151')
    img.save(path)


def create_home_mockup(path: Path):
    img = make_canvas(bg='#F2F7F6')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (60, 40, 1540, 860), radius=34, fill='#FFFFFF', outline='#D8E2E0', width=3)
    draw.text((100, 80), '首页', font=font(30, True), fill='#374151')
    draw.text((100, 135), '杭州 · 26°C · 晴', font=font(48, True), fill='#0F766E')
    draw.text((100, 205), '今日推荐：轻松通勤 · 评分 92 · 3 条理由', font=font(30), fill='#6B7280')

    round_rect(draw, (100, 285, 720, 800), radius=28, fill='#F8FBFA', outline='#DCE6E3', width=2)
    draw.text((140, 325), '今日推荐', font=font(30, True), fill='#111827')
    draw.text((140, 380), '• 风格：简洁通勤', font=font(28), fill='#4B5563')
    draw.text((140, 435), '• 评分：92 / 100', font=font(28), fill='#4B5563')
    draw.text((140, 490), '• 理由：颜色协调、层次清晰、适合当前天气', font=font(28), fill='#4B5563')
    round_rect(draw, (140, 610, 400, 690), radius=20, fill='#77AAA4')
    centered_text(draw, (140, 610, 400, 690), '查看详情', fill='#FFFFFF', size=28, bold=True)

    round_rect(draw, (780, 285, 1460, 800), radius=28, fill='#F8FBFA', outline='#DCE6E3', width=2)
    draw.text((820, 325), '智能穿搭入口', font=font(30, True), fill='#111827')
    draw.text((820, 380), '1. 点击一键生成', font=font(28), fill='#4B5563')
    draw.text((820, 435), '2. 选择参考图', font=font(28), fill='#4B5563')
    draw.text((820, 490), '3. 自动补天气并生成搭配', font=font(28), fill='#4B5563')
    draw.text((820, 545), '4. 查看 AI 解释与推荐理由', font=font(28), fill='#4B5563')
    round_rect(draw, (820, 620, 1140, 690), radius=20, fill='#0F766E')
    centered_text(draw, (820, 620, 1140, 690), '一键生成', fill='#FFFFFF', size=28, bold=True)
    round_rect(draw, (1170, 620, 1420, 690), radius=20, fill='#EEF2FF')
    centered_text(draw, (1170, 620, 1420, 690), '衣橱管理', fill='#4C1D95', size=24, bold=True)
    img.save(path)


def create_features_mockup(path: Path):
    img = make_canvas(bg='#F5F7F8')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=30, fill='#FFFFFF', outline='#D6DEE2', width=2)
    draw.text((90, 70), '功能总览', font=font(32, True), fill='#111827')
    items = [
        ('登录 / 注册', '先登录再进入系统'),
        ('首页推荐', '天气 + 今日推荐'),
        ('衣橱管理', '上传、筛选、编辑'),
        ('智能穿搭', '参考图生成多套搭配'),
        ('情绪穿搭', '按心情生成风格'),
        ('虚拟试衣', '正侧背三视角'),
        ('适合度分析', '场景 / 体型 / 风格'),
        ('相似度分析', '重复购买预警'),
    ]
    positions = [
        (100, 160, 460, 330), (530, 160, 890, 330), (960, 160, 1320, 330), (1390, 160, 1470, 330),
        (100, 430, 460, 600), (530, 430, 890, 600), (960, 430, 1320, 600), (1390, 430, 1470, 600),
    ]
    # custom layout for 4x2 grid
    positions = [
        (100, 160, 410, 340), (455, 160, 765, 340), (810, 160, 1120, 340), (1165, 160, 1475, 340),
        (100, 400, 410, 580), (455, 400, 765, 580), (810, 400, 1120, 580), (1165, 400, 1475, 580),
    ]
    for (title, desc), box in zip(items, positions):
        round_rect(draw, box, radius=24, fill='#F8FAFC', outline='#DCE3E8', width=2)
        draw.text((box[0] + 24, box[1] + 22), title, font=font(26, True), fill='#0F4C5C')
        for i, line in enumerate(wrap(desc, 16)):
            draw.text((box[0] + 24, box[1] + 72 + i * 34), line, font=font(24), fill='#4B5563')
    draw.text((90, 760), '建议按这个顺序使用：登录 → 首页 → 衣橱 → 智能穿搭 → 结果解释 → 虚拟试衣', font=font(28), fill='#374151')
    img.save(path)


def create_wardrobe_mockup(path: Path):
    img = make_canvas(bg='#F6F7FB')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=32, fill='#FFFFFF', outline='#D7DEE8', width=2)
    draw.text((90, 70), '衣橱管理', font=font(32, True), fill='#111827')
    draw.text((90, 120), '上传后可以按类别、颜色、季节筛选，并补充标签', font=font(26), fill='#6B7280')

    round_rect(draw, (90, 180, 430, 790), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((125, 215), '上传区', font=font(28, True), fill='#0F4C5C')
    draw.text((125, 280), '1. 选择图片', font=font(24), fill='#374151')
    draw.text((125, 335), '2. 自动识别品类', font=font(24), fill='#374151')
    draw.text((125, 390), '3. 补充颜色和季节', font=font(24), fill='#374151')
    round_rect(draw, (125, 470, 395, 555), radius=18, fill='#77AAA4')
    centered_text(draw, (125, 470, 395, 555), '上传衣物', fill='#FFFFFF', size=26, bold=True)

    round_rect(draw, (470, 180, 1490, 790), radius=24, fill='#FAFAFB', outline='#E2E8F0', width=2)
    draw.text((505, 215), '衣物列表', font=font(28, True), fill='#111827')
    items = [
        ('白色衬衫', '上衣 · 春秋 · 通勤'),
        ('牛仔裤', '下装 · 四季 · 日常'),
        ('黑色短外套', '外套 · 冬季 · 百搭'),
        ('白色运动鞋', '鞋子 · 春夏 · 休闲'),
    ]
    y = 280
    for title, desc in items:
        round_rect(draw, (505, y, 1450, y + 100), radius=18, fill='#FFFFFF', outline='#E5E7EB', width=2)
        round_rect(draw, (530, y + 20, 590, y + 80), radius=16, fill='#E2E8F0')
        draw.text((620, y + 26), title, font=font(26, True), fill='#111827')
        draw.text((620, y + 62), desc, font=font(22), fill='#6B7280')
        draw.text((1290, y + 36), '编辑  删除', font=font(22), fill='#0F4C5C')
        y += 120
    img.save(path)


def create_outfit_mockup(path: Path):
    img = make_canvas(bg='#F3F8F7')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=32, fill='#FFFFFF', outline='#D7DEE8', width=2)
    draw.text((90, 70), '智能穿搭', font=font(32, True), fill='#111827')
    draw.text((90, 120), '先选参考图，再点击生成，系统会返回多套结果', font=font(26), fill='#6B7280')

    round_rect(draw, (90, 180, 490, 790), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((125, 215), '输入', font=font(28, True), fill='#0F4C5C')
    draw.text((125, 275), '参考图', font=font(24), fill='#374151')
    round_rect(draw, (125, 320, 455, 470), radius=18, fill='#E5F4F1', outline='#B7D6D0', width=2)
    centered_text(draw, (125, 320, 455, 470), '参考\n图片', fill='#0F766E', size=30, bold=True)
    draw.text((125, 520), '天气：晴 / 26°C', font=font(24), fill='#374151')
    draw.text((125, 570), '场景：通勤 / 约会', font=font(24), fill='#374151')
    round_rect(draw, (125, 650, 455, 730), radius=18, fill='#0F766E')
    centered_text(draw, (125, 650, 455, 730), '开始生成', fill='#FFFFFF', size=26, bold=True)

    round_rect(draw, (530, 180, 1490, 790), radius=24, fill='#FAFAFB', outline='#E2E8F0', width=2)
    draw.text((565, 215), '生成结果', font=font(28, True), fill='#111827')
    result_boxes = [
        (565, 280, 1430, 390, '方案 A', '简洁通勤 · 评分 92 · 颜色稳重'),
        (565, 425, 1430, 535, '方案 B', '轻松休闲 · 评分 89 · 层次更明显'),
        (565, 570, 1430, 680, '方案 C', '偏正式 · 评分 85 · 适合会议场景'),
    ]
    for x1, y1, x2, y2, title, desc in result_boxes:
        round_rect(draw, (x1, y1, x2, y2), radius=18, fill='#FFFFFF', outline='#E5E7EB', width=2)
        draw.text((x1 + 24, y1 + 22), title, font=font(26, True), fill='#0F4C5C')
        draw.text((x1 + 24, y1 + 60), desc, font=font(22), fill='#6B7280')
        draw.text((x2 - 180, y1 + 38), '收藏  详情', font=font(22), fill='#4C1D95')
    img.save(path)


def create_mood_mockup(path: Path):
    img = make_canvas(bg='#FAF7F2')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=32, fill='#FFFFFF', outline='#E5DED2', width=2)
    draw.text((90, 70), '情绪穿搭', font=font(32, True), fill='#111827')
    draw.text((90, 120), '按今天的心情选风格，而不是只看天气', font=font(26), fill='#6B7280')

    moods = [('放松', '#EADBC8'), ('元气', '#C7E9D7'), ('安静', '#DCE6F8'), ('正式', '#F0D9D9')]
    x = 90
    for label, color in moods:
        round_rect(draw, (x, 200, x + 280, 280), radius=22, fill=color)
        centered_text(draw, (x, 200, x + 280, 280), label, fill='#111827', size=28, bold=True)
        x += 320

    round_rect(draw, (90, 340, 690, 770), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((125, 375), '选择后系统会给出', font=font(26, True), fill='#0F4C5C')
    draw.text((125, 430), '• 推荐色系', font=font(24), fill='#374151')
    draw.text((125, 485), '• 推荐单品', font=font(24), fill='#374151')
    draw.text((125, 540), '• 风格关键词', font=font(24), fill='#374151')
    draw.text((125, 595), '• 可直接收藏的搭配', font=font(24), fill='#374151')

    round_rect(draw, (750, 340, 1490, 770), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((785, 375), '示例输出', font=font(26, True), fill='#111827')
    draw.text((785, 440), '风格：轻松、干净、柔和', font=font(24), fill='#374151')
    draw.text((785, 495), '单品：宽松上衣、浅色下装、轻便鞋', font=font(24), fill='#374151')
    draw.text((785, 550), '理由：符合“想放松一点”的心情', font=font(24), fill='#374151')
    round_rect(draw, (785, 625, 1060, 700), radius=18, fill='#77AAA4')
    centered_text(draw, (785, 625, 1060, 700), '生成搭配', fill='#FFFFFF', size=24, bold=True)
    img.save(path)


def create_tryon_mockup(path: Path):
    img = make_canvas(bg='#F4F7F9')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=32, fill='#FFFFFF', outline='#D7DEE8', width=2)
    draw.text((90, 70), '虚拟试衣', font=font(32, True), fill='#111827')
    draw.text((90, 120), '上传人物图和衣服图后，系统生成试穿效果', font=font(26), fill='#6B7280')

    round_rect(draw, (90, 180, 450, 790), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((125, 215), '输入', font=font(28, True), fill='#0F4C5C')
    draw.text((125, 280), '人物图', font=font(24), fill='#374151')
    round_rect(draw, (125, 315, 405, 460), radius=18, fill='#EEF2FF', outline='#C7D2FE', width=2)
    centered_text(draw, (125, 315, 405, 460), '人物\n图片', fill='#4C1D95', size=30, bold=True)
    draw.text((125, 510), '衣服图', font=font(24), fill='#374151')
    round_rect(draw, (125, 545, 405, 680), radius=18, fill='#E5F4F1', outline='#B7D6D0', width=2)
    centered_text(draw, (125, 545, 405, 680), '衣服\n图片', fill='#0F766E', size=30, bold=True)

    round_rect(draw, (495, 180, 1490, 790), radius=24, fill='#FAFAFB', outline='#E2E8F0', width=2)
    draw.text((530, 215), '输出预览', font=font(28, True), fill='#111827')
    round_rect(draw, (530, 275, 930, 720), radius=22, fill='#EDE9FE', outline='#C4B5FD', width=2)
    centered_text(draw, (530, 275, 930, 720), '正面\n预览', fill='#4C1D95', size=40, bold=True)
    round_rect(draw, (975, 275, 1430, 720), radius=22, fill='#E5F4F1', outline='#B7D6D0', width=2)
    centered_text(draw, (975, 275, 1430, 720), '侧面 / 背面\n预览', fill='#0F766E', size=36, bold=True)
    img.save(path)


def create_analysis_mockup(path: Path):
    img = make_canvas(bg='#F7F8FB')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=32, fill='#FFFFFF', outline='#D7DEE8', width=2)
    draw.text((90, 70), '适合度 / 相似度分析', font=font(32, True), fill='#111827')
    draw.text((90, 120), '一个看合不合适，一个看会不会重复买', font=font(26), fill='#6B7280')

    round_rect(draw, (90, 180, 730, 790), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((125, 215), '适合度分析', font=font(28, True), fill='#0F4C5C')
    draw.text((125, 285), '总分：88', font=font(30, True), fill='#111827')
    draw.text((125, 345), '场景：合适', font=font(24), fill='#374151')
    draw.text((125, 400), '体型：友好', font=font(24), fill='#374151')
    draw.text((125, 455), '风格：一致', font=font(24), fill='#374151')
    round_rect(draw, (125, 560, 410, 640), radius=18, fill='#77AAA4')
    centered_text(draw, (125, 560, 410, 640), '查看理由', fill='#FFFFFF', size=24, bold=True)

    round_rect(draw, (810, 180, 1490, 790), radius=24, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.text((845, 215), '相似度分析', font=font(28, True), fill='#111827')
    bars = [('已有白衬衫', 86), ('已有直筒牛仔裤', 74), ('已有黑外套', 41)]
    y = 285
    for label, score in bars:
        draw.text((845, y), label, font=font(23), fill='#374151')
        round_rect(draw, (1090, y + 8, 1410, y + 34), radius=12, fill='#E5E7EB')
        round_rect(draw, (1090, y + 8, 1090 + int(score * 3.2), y + 34), radius=12, fill='#0F766E')
        draw.text((1425, y), f'{score}%', font=font(23, True), fill='#0F4C5C')
        y += 110
    draw.text((845, 645), '如果分数太高，系统会提示你可能已经有类似款。', font=font(22), fill='#6B7280')
    img.save(path)


def create_logs_mockup(path: Path):
    img = make_canvas((1600, 900), '#111827')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (45, 40, 1555, 860), radius=34, fill='#0F172A', outline='#334155', width=3)
    draw.text((95, 75), 'backend console output', font=font(28), fill='#A1A1AA')
    for x, color in zip([90, 130, 170], ['#FB7185', '#FBBF24', '#34D399']):
        draw.ellipse((x, 120, x + 18, 138), fill=color)

    lines = [
        '2026-04-11 12:10:59 | INFO | Uvicorn running on http://127.0.0.1:8010',
        '2026-04-11 12:10:59 | INFO | Application startup complete.',
        '2026-04-11 12:34:15 | INFO | SELECT users ...',
        '2026-04-11 12:34:15 | INFO | INSERT INTO users (...) VALUES (...)',
        '2026-04-11 12:34:15 | INFO | "POST /api/v1/auth/register HTTP/1.1" 201',
        '2026-04-11 12:36:02 | INFO | "POST /api/v1/auth/login HTTP/1.1" 200',
        '2026-04-11 12:36:15 | INFO | "GET /api/v1/smart-outfit/weather HTTP/1.1" 200',
        '2026-04-11 12:36:18 | INFO | "POST /api/v1/smart-outfit/generate HTTP/1.1" 200',
    ]
    y = 180
    for line in lines:
        draw.text((90, y), line, font=font(25), fill='#E5E7EB')
        y += 86
    img.save(path)


def create_feature_detail_mockup(path: Path, title: str, subtitle: str, bullets: list[str], action: str, accent='#0F766E'):
    img = make_canvas(bg='#F6F8FB')
    draw = ImageDraw.Draw(img)
    round_rect(draw, (50, 40, 1550, 860), radius=32, fill='#FFFFFF', outline='#D7DEE8', width=2)
    draw.text((90, 75), title, font=font(34, True), fill='#111827')
    draw.text((90, 132), subtitle, font=font(26), fill='#6B7280')

    round_rect(draw, (90, 210, 610, 760), radius=26, fill='#F8FAFC', outline='#E2E8F0', width=2)
    draw.ellipse((235, 280, 465, 510), fill='#E5F4F1', outline=accent, width=5)
    centered_text(draw, (160, 525, 540, 610), title, fill=accent, size=30, bold=True)
    round_rect(draw, (185, 650, 515, 725), radius=20, fill=accent)
    centered_text(draw, (185, 650, 515, 725), action, fill='#FFFFFF', size=25, bold=True)

    round_rect(draw, (680, 210, 1490, 760), radius=26, fill='#FAFAFB', outline='#E2E8F0', width=2)
    draw.text((720, 250), '用户会看到', font=font(28, True), fill='#0F4C5C')
    y = 325
    for item in bullets:
        draw.ellipse((725, y + 10, 743, y + 28), fill=accent)
        for i, line in enumerate(wrap(item, 30)):
            draw.text((765, y + i * 34), line, font=font(24), fill='#374151')
        y += 86
    img.save(path)


def ensure_assets():
    TMP_DIR.mkdir(exist_ok=True)
    create_login_mockup(TMP_DIR / 'login_mockup.png')
    create_home_mockup(TMP_DIR / 'home_mockup.png')
    create_features_mockup(TMP_DIR / 'feature_map.png')
    create_wardrobe_mockup(TMP_DIR / 'wardrobe_mockup.png')
    create_outfit_mockup(TMP_DIR / 'outfit_mockup.png')
    create_mood_mockup(TMP_DIR / 'mood_mockup.png')
    create_tryon_mockup(TMP_DIR / 'tryon_mockup.png')
    create_analysis_mockup(TMP_DIR / 'analysis_mockup.png')
    create_logs_mockup(TMP_DIR / 'logs_mockup.png')
    create_feature_detail_mockup(
        TMP_DIR / 'profile_mockup.png',
        '个人设置',
        '维护身高、体型、肤色、风格偏好与性别表达指数',
        ['填写基础资料后，推荐更贴合个人情况。', '性别表达指数会影响主题配色和推荐倾向。', '修改后建议重新生成智能穿搭或适合度分析。'],
        '保存设置',
        '#7C3AED',
    )
    create_feature_detail_mockup(
        TMP_DIR / 'body_shape_mockup.png',
        '体型洞察',
        '基于用户画像生成体型友好的穿搭建议',
        ['读取个人设置中的身高、体型和偏好。', '输出 3 套体型专属搭配方向。', '解释哪些版型更修饰身形或更适合当前场景。'],
        '生成建议',
        '#2563EB',
    )
    create_feature_detail_mockup(
        TMP_DIR / 'agent_mockup.png',
        'AI Agent',
        '用自然语言提出复杂穿搭需求，系统流式执行工具',
        ['可以同时结合天气、衣橱、记忆和场景。', '页面会展示执行步骤、工具调用和最终答案。', '适合不知道从哪个功能开始的用户。'],
        '发送问题',
        '#059669',
    )
    create_feature_detail_mockup(
        TMP_DIR / 'style_score_mockup.png',
        '风格打分',
        '输入上衣、下装、颜色和场景，查看搭配分数',
        ['返回风格分、Top3 推荐和中文解释。', '适合快速比较不同单品组合。', '可作为运营演示中的轻量 AI 评分入口。'],
        '开始评分',
        '#D97706',
    )


def add_para(story, styles, text, style='TTBody'):
    story.append(Paragraph(text, styles[style]))


def add_section(story, styles, title):
    story.append(Paragraph(title, styles['TTHeading1']))
    story.append(Spacer(1, 0.15 * cm))


def add_subsection(story, styles, title, body):
    story.append(Paragraph(title, styles['TTHeading2']))
    add_para(story, styles, body)
    story.append(Spacer(1, 0.12 * cm))


def add_step_detail(story, styles, step_title: str, input_data: str, actions: str, output_data: str, log_hint: str):
    story.append(Paragraph(step_title, styles['TTHeading2']))
    add_para(story, styles, f'<b>输入：</b>{input_data}')
    add_para(story, styles, f'<b>操作：</b>{actions}')
    add_para(story, styles, f'<b>输出：</b>{output_data}')
    add_para(story, styles, f'<b>日志：</b>{log_hint}')
    story.append(Spacer(1, 0.15 * cm))


def add_image(story, source: Path, caption: str, max_width: float = 16.7 * cm):
    if not source.exists():
        return
    img = Image(str(source))
    img._restrictSize(max_width, 9.8 * cm)
    story.append(img)
    story.append(Spacer(1, 0.12 * cm))
    story.append(Paragraph(caption, CAPTION_STYLE))
    story.append(Spacer(1, 0.25 * cm))


def choose_asset(real_name: str, fallback_name: str) -> Path:
    real_path = TMP_DIR / real_name
    if real_path.exists():
        return real_path
    return TMP_DIR / fallback_name


def build_pdf():
    ensure_assets()

    styles = getSampleStyleSheet()
    cn_font = register_chinese_font()
    styles.add(
        ParagraphStyle(
            name='TTBody',
            parent=styles['Normal'],
            fontName=cn_font,
            fontSize=10.2,
            leading=13.6,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name='TTHeading1',
            parent=styles['Heading1'],
            fontName=cn_font,
            fontSize=16,
            leading=20,
            spaceAfter=8,
            textColor=colors.HexColor('#163A3D'),
        )
    )
    styles.add(
        ParagraphStyle(
            name='TTHeading2',
            parent=styles['Heading2'],
            fontName=cn_font,
            fontSize=12.4,
            leading=15.5,
            spaceAfter=4,
            textColor=colors.HexColor('#0F4C5C'),
        )
    )
    styles.add(
        ParagraphStyle(
            name='TTCaption',
            parent=styles['Italic'],
            fontName=cn_font,
            fontSize=8.8,
            leading=11,
            textColor=colors.HexColor('#4B5563'),
            alignment=TA_CENTER,
        )
    )
    global CAPTION_STYLE
    CAPTION_STYLE = styles['TTCaption']

    story = []
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph('智能穿搭助手使用教程', styles['Title']))
    story.append(Spacer(1, 0.18 * cm))
    add_para(
        story,
        styles,
        '这份教程从用户登录开始，按真实使用顺序讲解首页、衣橱、智能穿搭、情绪穿搭、虚拟试衣、适合度分析与相似度分析的操作方法，并配有前端示意截图和后端日志截图。',
    )
    story.append(Spacer(1, 0.25 * cm))

    intro = Table(
        [
            ['你会看到什么', '说明'],
            ['截图', '登录页、首页、功能总览、日志面板'],
            ['日志', '注册、登录、天气、穿搭生成、接口返回'],
            ['目标', '看完后可以独立完成一次完整使用流程'],
        ],
        colWidths=[4.0 * cm, 12.2 * cm],
        repeatRows=1,
    )
    intro.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F4C5C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, -1), cn_font),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor('#F8FAFC')]),
                ('FONTSIZE', (0, 0), (-1, -1), 9.4),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ]
        )
    )
    story.append(intro)
    story.append(Spacer(1, 0.28 * cm))

    add_section(story, styles, '1. 先启动，再登录')
    add_subsection(
        story,
        styles,
        '步骤 1：启动后端',
        '先启动 FastAPI 后端，默认地址是 http://127.0.0.1:8010。只有后端可用，登录、天气和推荐接口才会正常工作。',
    )
    add_subsection(
        story,
        styles,
        '步骤 2：启动 Flutter Web',
        '再启动 Flutter Web 前端，默认地址是 http://127.0.0.1:8081。打开后会先进入登录页 /#/auth。',
    )
    add_subsection(
        story,
        styles,
        '步骤 3：注册并登录',
        '如果是第一次使用，先切到“注册”输入用户名、邮箱和密码，然后再回到“登录”输入同一账号登录。',
    )
    add_image(story, TMP_DIR / 'login_mockup.png', '图 1：登录页示意图，先注册再登录')

    story.append(Paragraph('2. 首页是你的入口', styles['TTHeading1']))
    add_para(
        story,
        styles,
        '登录成功后会进入首页。首页的核心作用是把天气、城市和今日推荐聚合在一起，让你先知道“今天适不适合穿什么”，再进入具体功能。',
    )
    add_para(
        story,
        styles,
        '首页上通常会看到城市、天气、温度，以及一张“今日推荐”卡。你可以先查看推荐分数和风格，再点“查看详情”回到具体搭配。',
    )
    add_image(story, choose_asset('real_home.png', 'home_mockup.png'), '图 2：首页真实截图，先看天气和今日推荐')

    add_section(story, styles, '3. 首页之后，先看功能总览')
    add_para(
        story,
        styles,
        '如果你是第一次上手，建议先把功能路径记成一条线：登录 → 首页 → 衣橱管理 → 智能穿搭 → 结果解释 → 虚拟试衣。情绪穿搭、适合度分析和相似度分析属于辅助路径，可以按需要再进入。',
    )
    add_image(story, TMP_DIR / 'feature_map.png', '图 3：功能总览示意图，理解各模块入口')

    add_section(story, styles, '4. 衣橱管理怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 4.1：进入衣橱并检查现有单品',
        '无（登录后直接进入“衣橱”页）。',
        '点击底部“衣橱”标签，确认页面显示“我的衣橱”“添加单品”“搜索品类”。',
        '页面展示已有单品列表（例如：鞋子、外套、上衣等），可继续新增。',
        '前端成功标志：页面无报错并出现单品卡片；后端常见日志：GET /api/v1/wardrobe... 200。',
    )
    add_image(story, choose_asset('real_shell.png', 'wardrobe_mockup.png'), '图 4：衣橱管理真实截图，先上传，再整理标签')
    add_step_detail(
        story,
        styles,
        '步骤 4.2：新增与整理（建议）',
        '输入：衣服照片 1~N 张（清晰、单品、背景简单）。',
        '点击“添加单品”上传图片，补齐类别/颜色/季节标签；再用搜索框筛选核对。',
        '衣橱中的标签更完整，后续推荐准确率明显提升。',
        '后端常见日志：POST /api/v1/wardrobe... 201；失败时看 400/422 字段报错。',
    )

    add_section(story, styles, '5. 智能穿搭怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 5.1：进入“穿搭推荐”页面',
        '输入：场景（例如日常休闲 / 职场商务）+ 1~5 张参考图。',
        '在首页点击“穿搭推荐”，选择场景，上传参考图。',
        '页面显示“0/5 张图片”变化为已选数量，并可点击“生成推荐结果”。',
        '后端常见日志：POST /api/v1/smart-outfit/generate... 200。',
    )
    add_image(story, choose_asset('real_outfit.png', 'outfit_mockup.png'), '图 5：穿搭推荐真实截图，先放参考图，再点生成')
    add_step_detail(
        story,
        styles,
        '步骤 5.2：查看输出与解释',
        '输入：点击“生成推荐结果”。',
        '等待推荐完成后，按方案逐条查看分数与理由。',
        '输出包含风格方向、评分与推荐理由（可用于是否收藏的决策）。',
        '若失败，先看前端提示，再查后端日志中的状态码与错误字段。',
    )

    add_section(story, styles, '6. 搭配推荐 / 风格打分怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 6.1：输入单品组合并评分',
        '输入：上衣、下装、颜色、季节和场景。',
        '进入“搭配推荐”或风格打分入口，填写单品组合后点击生成。',
        '输出：风格分、Top3 推荐和中文解释，用于快速比较不同搭配。',
        '后端常见日志：POST /predict... 200。',
    )
    add_image(story, TMP_DIR / 'style_score_mockup.png', '图 6：风格打分示意截图，用于快速比较搭配组合')

    add_section(story, styles, '7. 情绪穿搭怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 7.1：情绪输入与建议生成',
        '输入：选择当前心情标签（如“开心/放松/疲惫/压力大”）。',
        '点击“生成情绪穿搭建议”。',
        '输出：系统给出颜色方向、风格关键词及衣橱匹配建议。',
        '后端常见日志：POST /api/v1/analysis/mood-outfit... 200。',
    )
    add_image(story, choose_asset('real_mood.jpg', 'mood_mockup.png'), '图 7：情绪穿搭真实截图，先选心情，再看推荐方向')

    add_section(story, styles, '8. 适合度分析怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 8.1：上传图片并读取总分',
        '输入：一张待分析服饰图。',
        '进入“适合度评分”页面，点击“选择服饰图片”。',
        '输出：返回总分与维度解释（场景/体型/风格）。',
        '后端常见日志：POST /api/v1/analysis/suitability... 200。',
    )
    add_image(story, choose_asset('real_suitability.png', 'analysis_mockup.png'), '图 8：适合度分析真实截图，先看说明，再选图分析')

    add_section(story, styles, '9. 相似度分析怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 9.1：上传新衣服做相似度比对',
        '输入：一张计划购买/新拍的衣服图，或一张整身 Look 图。',
        '进入“相似度分析”，选择“单品”或“Look”模式后点击“选择图片”。',
        '输出：单品模式返回相似候选与相似度分数；Look 模式返回整体匹配、部件匹配、缺失品类和试衣候选。',
        '后端常见日志：POST /api/v1/analysis/similarity... 200；POST /api/v1/analysis/look-similarity... 200。',
    )
    add_image(story, choose_asset('real_similarity.png', 'analysis_mockup.png'), '图 9：相似度分析真实截图，避免重复购买')

    add_section(story, styles, '10. 虚拟试衣怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 10.1：上传衣服图 + 人物图生成试衣',
        '输入：衣服图（建议无模特）+ 人物正面照（必填，建议白底）；从 Look 候选进入时衣服图会自动带入。',
        '进入“虚拟试衣”，按提示上传图片，点击生成。',
        '输出：返回试穿图；移动端可保存到相册，Web 端可打开结果图下载。',
        '后端常见日志：POST /tryon/garment... 200；若 400 通常是输入图不符合要求。',
    )
    add_image(story, choose_asset('real_tryon.png', 'tryon_mockup.png'), '图 10：虚拟试衣步骤截图（点击入口后按提示上传衣服图与人物图）')

    add_section(story, styles, '11. 个人设置怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 11.1：补充画像并保存',
        '输入：身高、体型、肤色、风格偏好和性别表达指数。',
        '进入底部“设置”，填写资料后点击保存。',
        '输出：后续推荐、适合度分析和体型洞察会读取这些资料。',
        '前端成功标志：页面保存成功提示；后端常见日志：PUT /api/v1/profile... 200。',
    )
    add_image(story, TMP_DIR / 'profile_mockup.png', '图 11：个人设置示意截图，先补画像再做推荐')

    add_section(story, styles, '12. 体型洞察怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 12.1：生成体型友好穿搭',
        '输入：已保存的用户画像。',
        '进入“体型洞察”，点击生成建议。',
        '输出：3 套体型专属搭配方向和版型解释。',
        '前端成功标志：页面展示搭配卡片和原因说明。',
    )
    add_image(story, TMP_DIR / 'body_shape_mockup.png', '图 12：体型洞察示意截图，读取画像后生成建议')

    add_section(story, styles, '13. AI Agent 对话怎么用')
    add_step_detail(
        story,
        styles,
        '步骤 13.1：用自然语言提出穿搭需求',
        '输入：一句完整需求，例如“明天面试，20 度，帮我从衣橱选一套”。',
        '进入 AI Agent 对话页，发送问题并等待流式步骤完成。',
        '输出：执行步骤、工具调用结果和最终穿搭建议。',
        '后端常见日志：POST /api/v1/agent/chat-stream... 200。',
    )
    add_image(story, TMP_DIR / 'agent_mockup.png', '图 13：AI Agent 示意截图，适合复杂自然语言需求')

    add_section(story, styles, '14. 日志怎么看')
    add_step_detail(
        story,
        styles,
        '步骤 14.1：按“时间点 + 接口 + 状态码”排查',
        '输入：页面报错时间、当前操作（例如登录/生成/试衣）。',
        '在后端控制台按时间找到对应接口，确认返回码。',
        '输出：快速定位是前端参数问题、鉴权问题还是后端服务问题。',
        '示例：POST /api/v1/auth/login 200；POST /api/v1/smart-outfit/generate 200。',
    )
    add_image(story, TMP_DIR / 'logs_mockup.png', '图 14：后端日志示意图，能快速判断注册、登录和生成是否成功')

    add_section(story, styles, '15. 推荐的实际使用顺序')
    sequence = Table(
        [
            ['顺序', '你要做什么', '目的'],
            ['1', '注册 / 登录', '拿到登录态'],
            ['2', '先看首页天气与今日推荐', '了解当天主线'],
            ['3', '整理衣橱', '让推荐有数据基础'],
            ['4', '生成智能穿搭', '得到多套搭配与解释'],
            ['5', '必要时看情绪穿搭 / 适合度 / 相似度', '做补充决策'],
            ['6', '需要试上身时进入虚拟试衣', '确认最终效果'],
        ],
        colWidths=[1.3 * cm, 7.4 * cm, 8.1 * cm],
        repeatRows=1,
    )
    sequence.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F4C5C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, -1), cn_font),
                ('FONTSIZE', (0, 0), (-1, -1), 9.2),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor('#F8FAFC')]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ]
        )
    )
    story.append(sequence)
    story.append(Spacer(1, 0.25 * cm))

    add_section(story, styles, '16. 常见问题')
    add_subsection(
        story,
        styles,
        '页面空白或打不开',
        '先确认后端 8010 和前端 8081 都已启动。如果浏览器报连接失败，通常是服务没起来或端口没对上。',
    )
    add_subsection(
        story,
        styles,
        '登录后又掉回登录页',
        '检查 token 是否保存成功；如果是 Web，通常需要先完成登录再刷新一次，或者重新进入首页。',
    )
    add_subsection(
        story,
        styles,
        '没有推荐结果',
        '先确认衣橱里有可用图片，再检查天气和接口日志；空衣橱时系统不会给虚拟推荐。',
    )

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=1.45 * cm,
        leftMargin=1.45 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    doc.build(story)


if __name__ == '__main__':
    build_pdf()
