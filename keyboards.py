"""
keyboards.py
كل لوحات مفاتيح البوت مع دعم ألوان الأزرار (style field)
style values: "success" | "danger" | "primary"
"""
from __future__ import annotations
from typing import Optional
from pydantic import ConfigDict
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from states import AdObjectives, BMToolStates


# ─────────────────────────────────────────────────────
#  StyledButton — يضيف حقل style للـ JSON النهائي
#  (Telegram يتجاهل الحقول غير المعروفة بهدوء)
# ─────────────────────────────────────────────────────

class StyledButton(InlineKeyboardButton):
    """InlineKeyboardButton مع حقل style اختياري."""
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    style: Optional[str] = None


def _btn(text: str, *,
         callback_data: Optional[str] = None,
         url: Optional[str] = None,
         style: Optional[str] = None,
         **kw) -> StyledButton:
    """اختصار لبناء زر مع style."""
    kwargs: dict = {'text': text}
    if callback_data is not None:
        kwargs['callback_data'] = callback_data
    if url is not None:
        kwargs['url'] = url
    if style is not None:
        kwargs['style'] = style
    kwargs.update(kw)
    return StyledButton(**kwargs)


# ══════════════════════════════════════════════════════
#  القائمة الرئيسية
# ══════════════════════════════════════════════════════

def main_menu(gate_names: dict, subscribed: bool,
              support_url: str = 'https://t.me/') -> InlineKeyboardMarkup:
    rows = []
    gate_styles = {
        'standard_ad':  ('🟢 إعلان رابط بوست', 'success'),
        'dark_post':    ('🔵 إعلان دارك بوست',  'primary'),
        'partner_ship': ('🟣 إعلان بارتنر شيب', 'primary'),
        'new_dark': ('⚡ New Dark Post', 'success'),
    }
    for k in gate_names:
        label, sty = gate_styles.get(k, (gate_names[k], 'primary'))
        rows.append([_btn(label, callback_data=f'gate:{k}', style=sty)])

    if subscribed:
        rows.append([_btn('📊 إحصائياتي', callback_data='my_stats', style='primary')])
    else:
        rows.append([_btn('🔒 لم تفعل الاشتراك بعد — فعّل كود Redeem', callback_data='redeem', style='danger')])

    rows.append([_btn('🛠️ الأدوات', callback_data='tools:menu', style='primary')])
    rows.append([
        _btn('🎟️ تفعيل كود Redeem', callback_data='redeem', style='success'),
        _btn('🛟 الدعم', url=support_url),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ══════════════════════════════════════════════════════
#  قوائم الأدوات
# ══════════════════════════════════════════════════════

def tools_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('📢 أدوات الإعلانات',        callback_data='tools:ads',   style='primary')],
        [_btn('🔗 أدوات ربط و تسميع',      callback_data='tools:link',  style='primary')],
        [_btn('🏠 القائمة الرئيسية',        callback_data='home',        style='danger')],
    ])


def ad_tools_menu(gate_names: dict, subscribed: bool) -> InlineKeyboardMarkup:
    rows = []
    if subscribed:
        gate_styles = {
            'standard_ad':  ('🟢 إعلان رابط بوست', 'success'),
            'dark_post':    ('🔵 إعلان دارك بوست',  'primary'),
            'partner_ship': ('🟣 إعلان بارتنر شيب', 'primary'),
            'new_dark': ('⚡ New Dark Post', 'success'),
        }
        for k in gate_names:
            label, sty = gate_styles.get(k, (gate_names[k], 'primary'))
            rows.append([_btn(label, callback_data=f'gate:{k}', style=sty)])
    else:
        rows.append([_btn('🔒 غير مشترك — فعّل كودك أولاً',
                          callback_data='redeem', style='danger')])
    rows.append([_btn('🔙 الأدوات', callback_data='tools:menu', style='primary')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def link_tools_menu(subscribed: bool) -> InlineKeyboardMarkup:
    rows = []
    if subscribed:
        rows.extend([
            [_btn('💳 تسميع البطاقات BM',       callback_data='tool:bm_cards', style='success')],
            [_btn('🔗 ربط بايبال',              callback_data='tool:paypal',   style='primary')],
        ])
    else:
        rows.append([
            _btn('🔒 هذه الأدوات للمشتركين فقط', callback_data='redeem', style='danger')
        ])
    rows.append([_btn('🔙 الأدوات', callback_data='tools:menu', style='primary')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bm_card_select_keyboard(cards: list, selected: list) -> InlineKeyboardMarkup:
    rows = []
    for i, card in enumerate(cards):
        name  = card.get('card_association_name', 'Card')
        last4 = card.get('last_four_digits', '****')
        cid   = card.get('credential_id', '')
        icon  = '✅' if cid in selected else '⬜'
        sty   = 'success' if cid in selected else 'primary'
        rows.append([_btn(f'{icon} {name} •••• {last4}',
                          callback_data=f'bm:card:{i}', style=sty)])
    rows.append([
        _btn('☑️ تحديد الكل', callback_data='bm:select_all',    style='primary'),
        _btn('✅ تأكيد',       callback_data='bm:confirm_cards',  style='success'),
    ])
    rows.append([_btn('🏠 إلغاء', callback_data='home', style='danger')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bm_proxy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('🤖 اختيار تلقائي من القائمة', callback_data='bm:proxy:auto',   style='primary')],
        [_btn('✏️ إدخال بروكسي يدوي',         callback_data='bm:proxy:custom', style='primary')],
        [_btn('⏭️ تخطي — بدون بروكسي',        callback_data='bm:proxy:skip',   style='primary')],
        [_btn('🏠 القائمة الرئيسية',           callback_data='home',            style='danger')],
    ])


# ══════════════════════════════════════════════════════
#  البروكسي
# ══════════════════════════════════════════════════════

def proxy_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('🤖 اختيار تلقائي من القائمة', callback_data='proxy:auto',   style='primary')],
        [_btn('✏️  إدخال بروكسي يدوي',        callback_data='proxy:custom', style='primary')],
        [_btn('⏭️  تخطي — بدون بروكسي',       callback_data='proxy:skip',   style='primary')],
        [_btn('🏠 القائمة الرئيسية',            callback_data='home',         style='danger')],
    ])


def back_to_proxy() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('🔙 تغيير البروكسي',   callback_data='proxy:back', style='primary')],
        [_btn('🏠 القائمة الرئيسية', callback_data='home',       style='danger')],
    ])


# ══════════════════════════════════════════════════════
#  الأهداف
# ══════════════════════════════════════════════════════

def objective_selection_keyboard() -> InlineKeyboardMarkup:
    icons = {
        'CONVERSATIONS':      '💬',
        'MESSAGES_MESSENGER': '📨',
        'MESSAGES_WHATSAPP':  '📱',
        'LINK_CLICKS':        '🔗',
        'POST_ENGAGEMENT':    '📈',
        'VIDEO_VIEWS':        '🎬',
    }
    rows = []
    objs = AdObjectives.all()
    for i in range(0, len(objs), 2):
        row = []
        for obj in objs[i:i+2]:
            icon = icons.get(obj, '🎯')
            name = AdObjectives.get_display_name(obj).split('(')[0].strip()
            row.append(_btn(f'{icon} {name}',
                            callback_data=f'objective:{obj}', style='primary'))
        rows.append(row)
    rows.append([_btn('🏠 القائمة الرئيسية', callback_data='home', style='danger')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ══════════════════════════════════════════════════════
#  تأكيد وتشغيل
# ══════════════════════════════════════════════════════

def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn('✅ تأكيد وتشغيل', callback_data='confirm:yes', style='success'),
            _btn('❌ إلغاء',         callback_data='confirm:no',  style='danger'),
        ],
        [_btn('🏠 القائمة الرئيسية', callback_data='home', style='danger')],
    ])


def activate_or_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('🟢 نشر نشط',        callback_data='activate:run',       style='success')],
        [_btn('⏸ نشر ثم إيقاف',   callback_data='activate:run_pause', style='danger')],
        [_btn('🔙 العودة للقائمة', callback_data='home',               style='primary')],
    ])


# ══════════════════════════════════════════════════════
#  اختيار البوست
# ══════════════════════════════════════════════════════

def post_selection_keyboard(posts: list) -> InlineKeyboardMarkup:
    rows = []
    for post in posts[:8]:
        pid  = post.get('id', '')
        text = post.get('message') or post.get('story') or ''
        label = text[:45].replace('\n', ' ') if text else f"📄 بوست {pid}"
        rows.append([_btn(f'📌 {label}', callback_data=f'post:{pid}', style='primary')])
    rows.append([_btn('✏️ إدخال رابط/ID يدوي', callback_data='post:manual', style='primary')])
    rows.append([_btn('🏠 القائمة الرئيسية',   callback_data='home',        style='danger')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ══════════════════════════════════════════════════════
#  الصورة
# ══════════════════════════════════════════════════════

def image_received_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn('🔄 تغيير الصورة', callback_data='image:change', style='primary'),
            _btn('⏭️ تخطي الصورة',  callback_data='image:skip',   style='primary'),
        ],
        [_btn('🏠 إلغاء', callback_data='home', style='danger')],
    ])


# ══════════════════════════════════════════════════════
#  تنقل عام
# ══════════════════════════════════════════════════════

def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('🏠 القائمة الرئيسية', callback_data='home', style='primary')],
    ])


def back_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('🔙 لوحة التحكم', callback_data='admin:panel', style='primary')],
    ])


# ══════════════════════════════════════════════════════
#  لوحة تحكم الأدمن
# ══════════════════════════════════════════════════════

def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn('🎟️ توليد كود Redeem', callback_data='admin:gen_code',    style='success'),
            _btn('📊 الإحصائيات',        callback_data='admin:stats',       style='primary'),
        ],
        [
            _btn('👤 إضافة/تمديد مشترك', callback_data='admin:set_user',    style='success'),
            _btn('🗑️  حذف مشترك',         callback_data='admin:remove_user', style='danger'),
        ],
        [
            _btn('📋 قائمة المشتركين',   callback_data='admin:list_users',  style='primary'),
            _btn('🎟️ عرض الأكواد',        callback_data='admin:list_codes',  style='primary'),
        ],
        [
            _btn('🌐 إضافة بروكسيات',    callback_data='admin:add_proxies',  style='success'),
            _btn('🗂️  عرض البروكسيات',    callback_data='admin:list_proxies', style='primary'),
        ],
        [
            _btn('📢 رسالة جماعية',      callback_data='admin:broadcast', style='primary'),
            _btn('⚙️  إعدادات البوت',     callback_data='admin:settings',  style='primary'),
        ],
        [_btn('🏠 خروج من لوحة التحكم', callback_data='home', style='danger')],
    ])


def admin_users_keyboard(users: list) -> InlineKeyboardMarkup:
    rows = []
    for u in users[:8]:
        uid  = u['user_id']
        name = u['custom_name'] or u['first_name'] or f'user_{uid}'
        sub  = '🟢' if u['subscription_until'] else '🔴'
        sty  = 'success' if u['subscription_until'] else 'danger'
        rows.append([_btn(f'{sub} {name} ({uid})',
                          callback_data=f'admin:user_info:{uid}', style=sty)])
    rows.append([_btn('🔙 لوحة التحكم', callback_data='admin:panel', style='primary')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_action_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            _btn('➕ تمديد اشتراك', callback_data=f'admin:extend:{user_id}', style='success'),
            _btn('🗑️ حذف',          callback_data=f'admin:del:{user_id}',    style='danger'),
        ],
        [_btn('🔙 قائمة المشتركين', callback_data='admin:list_users', style='primary')],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn('✏️  تغيير اسم البوت',  callback_data='admin:set_botname', style='primary')],
        [_btn('🔗 تغيير رابط الدعم', callback_data='admin:set_support', style='primary')],
        [_btn('🔙 لوحة التحكم',       callback_data='admin:panel',       style='primary')],
    ])


# == New Dark keyboards ==
def nd_country_keyboard() -> InlineKeyboardMarkup:
    rows,row=[],[]
    for code,name in [("EG","مصر 🇪🇬"),("SA","السعودية 🇸🇦"),("AE","الإمارات 🇦🇪"),("KW","الكويت 🇰🇼"),("QA","قطر 🇶🇦"),("IQ","العراق 🇮🇶"),("JO","الأردن 🇯🇴"),("MA","المغرب 🇲🇦"),("DZ","الجزائر 🇩🇿"),("TN","تونس 🇹🇳"),("LY","ليبيا 🇱🇾"),("TR","تركيا 🇹🇷"),("US","أمريكا 🇺🇸"),("GB","بريطانيا 🇬🇧")]:
        row.append(_btn(name,callback_data=f"nd:country:{code}",style="primary"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([_btn("🏠 إلغاء",callback_data="home",style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def nd_goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("💬 رسائل ماسنجر",callback_data="nd:goal:MESSAGES",style="success")],
        [_btn("📈 تفاعل مع البوست",callback_data="nd:goal:POST_ENGAGEMENT",style="primary")],
        [_btn("👍 إعجابات الصفحة",callback_data="nd:goal:PAGE_LIKES",style="primary")],
        [_btn("🔗 نقرات على الرابط",callback_data="nd:goal:LINK_CLICKS",style="primary")],
        [_btn("🏠 إلغاء",callback_data="home",style="danger")],])

def nd_age_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("18 - 24", callback_data="nd:age:18:24", style="primary"), _btn("25 - 34", callback_data="nd:age:25:34", style="primary")],
        [_btn("35 - 44", callback_data="nd:age:35:44", style="primary"), _btn("45 - 54", callback_data="nd:age:45:54", style="primary")],
        [_btn("55 - 65", callback_data="nd:age:55:65", style="primary"), _btn("18 - 65 (الكل)", callback_data="nd:age:18:65", style="success")],
        [_btn("🏠 إلغاء", callback_data="home", style="danger")],
    ])

def nd_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("👨 رجال فقط", callback_data="nd:gender:MALE", style="primary"), _btn("👩 نساء فقط", callback_data="nd:gender:FEMALE", style="primary")],
        [_btn("👥 الجميع (بدون تحديد)", callback_data="nd:gender:ALL", style="success")],
        [_btn("🏠 إلغاء", callback_data="home", style="danger")],
    ])

def nd_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("✅ نشر + إيقاف فوري", callback_data="nd:confirm:yes", style="success"), _btn("❌ إلغاء", callback_data="nd:confirm:no", style="danger")],
    ])
