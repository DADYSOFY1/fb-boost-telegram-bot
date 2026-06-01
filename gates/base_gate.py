import os
import re
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from aiogram.types import Message, CallbackQuery, PhotoSize, FSInputFile
from aiogram.fsm.context import FSMContext
from states import AdObjectives, GateConstants, AdGateStates

TEMP_DIR = Path('data/temp')
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# رسائل بوت جديدة في مسار الإعلان (لحذفها عند إلغاء المسار أو بدء بوابة جديدة)
FLOW_MSG_IDS_MAX = 45

BANNER_PHOTO_PATH = Path(__file__).parent.parent / 'paner.webp'

BANNER_TEXT = (
    "<b>📌 بانر ثابت</b>\n"
    "الردود تتجدد تحته فقط.\n\n"
)


async def append_flow_msg_to_state(state: FSMContext, msg: Optional[Message]) -> None:
    if msg is None:
        return
    data = await state.get_data()
    ids = list(data.get('flow_msg_ids', []))
    ids.append(msg.message_id)
    await state.update_data(flow_msg_ids=ids[-FLOW_MSG_IDS_MAX:])


class BaseGate(ABC):
    def __init__(self, gate_id: str, gate_name: str, gate_type: str):
        self.gate_id = gate_id
        self.gate_name = gate_name
        self.gate_type = gate_type

    @abstractmethod
    async def enter(self, call: CallbackQuery, state: FSMContext, config: dict):
        pass

    # ────── إرسال البانر (صورة ثابتة) ──────

    async def send_banner(self, target, state: FSMContext, caption: str = "", **kwargs) -> Optional[int]:
        """
        يرسل صورة البانر مع caption — تكون هي الرسالة الوحيدة في مسار الإعلان.
        target: CallbackQuery أو Message
        يُرجع message_id الخاص بالرسالة المرسلة.
        لو الصورة مش موجودة، يرسل رسالة نصية ويحفظها كبانر.
        """
        data = await state.get_data()
        old_banner_id = data.get('banner_msg_id')
        old_flow_ids = list(data.get('flow_msg_ids', []))
        bot = target.message.bot if isinstance(target, CallbackQuery) else target.bot

        msg = None
        if BANNER_PHOTO_PATH.exists():
            try:
                if isinstance(target, CallbackQuery):
                    msg = await target.message.answer_photo(
                        photo=FSInputFile(BANNER_PHOTO_PATH),
                        caption=caption,
                        **kwargs,
                    )
                    # نحذف رسالة الكول باك القديمة لو كانت غير رسالة البانر
                    try:
                        await target.message.delete()
                    except Exception:
                        pass
                else:
                    msg = await target.answer_photo(
                        photo=FSInputFile(BANNER_PHOTO_PATH),
                        caption=caption,
                        **kwargs,
                    )
            except Exception as e:
                print(f"⚠️ فشل إرسال صورة البانر: {e}")
                msg = None

        if msg is None:
            # Fallback: نرسل رسالة نصية
            if isinstance(target, CallbackQuery):
                try:
                    await target.message.edit_text(caption, **kwargs)
                    msg = target.message
                except Exception:
                    msg = await target.message.answer(caption, **kwargs)
            else:
                msg = await target.answer(caption, **kwargs)

        mid = msg.message_id if hasattr(msg, 'message_id') else msg.message_id
        # إذا أرسلنا بانر جديد، نحذف البانر القديم من القبول ونحاول مسحه من الدردشة.
        if old_banner_id and old_banner_id != mid:
            try:
                await bot.delete_message(target.message.chat.id, old_banner_id)
            except Exception:
                pass
            old_flow_ids = [m for m in old_flow_ids if m != old_banner_id]

        await state.update_data(
            banner_msg_id=mid,
            fixed_msg_id=mid,
            flow_msg_ids=(old_flow_ids + [mid])[-FLOW_MSG_IDS_MAX:]
        )
        return mid

    async def update_banner_caption(self, bot, chat_id: int, state: FSMContext, text: str, **kwargs) -> bool:
        """
        يعدل الكابشن بتاع رسالة البانر فقط (أو النص لو مفيش صورة).
        لو فشل، يحاول يعيد إرسال البانر ويعدله.
        """
        data = await state.get_data()
        banner_msg_id = data.get('banner_msg_id')
        if banner_msg_id:
            try:
                # نحاول نعدل الكابشن (لأنها صورة)
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=banner_msg_id,
                    caption=text,
                    **kwargs,
                )
                return True
            except Exception:
                # لو فشل (الرسالة مش صورة)، نحاول edit_message_text
                try:
                    await bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=banner_msg_id,
                        **kwargs,
                    )
                    return True
                except Exception:
                    pass
        return False

    # ────── طرق الرد — كلها تعدل البانر فقط ──────

    async def reply_step(self, message: Message, state: FSMContext, text: str, **kwargs) -> None:
        """
        يجب أن تكون هذه الدالة هي الوحيدة المستخدمة للرد على رسائل المستخدم.
        تعدل كابشن البانر فقط — لا ترسل أبداً رسالة جديدة.
        """
        data = await state.get_data()
        banner_msg_id = data.get('banner_msg_id')

        if banner_msg_id:
            # نحاول نعدل الكابشن بتاع البانر
            success = await self.update_banner_caption(
                message.bot, message.chat.id, state, text, **kwargs
            )
            if success:
                return

        # لو مفيش بانر أو فشل التعديل: نرسل البانر من جديد
        await self.send_banner(message, state, caption=text, **kwargs)

    async def edit_step(self, call: CallbackQuery, state: FSMContext, text: str, **kwargs) -> None:
        """
        يحدث رسالة البانر فقط عند اختيار أزرار (CallbackQuery).
        لا يرسل أبداً رسالة جديدة.
        """
        data = await state.get_data()
        banner_msg_id = data.get('banner_msg_id')

        if banner_msg_id:
            success = await self.update_banner_caption(
                call.message.bot, call.message.chat.id, state, text, **kwargs
            )
            if success:
                return

        # لو مفيش بانر: نرسله
        await self.send_banner(call, state, caption=text, **kwargs)

    # ────── مسح رسالة المستخدم ──────

    async def delete_user_message(self, message: Message, state: FSMContext):
        """يمسح رسالة المستخدم بعد معالجتها عشان ميبقاش في رسايل قديمة."""
        try:
            await message.delete()
        except Exception:
            pass

    # ────── تحديث البانر بعد جلب البوستات (لـ standard_ad_gate) ──────

    async def update_banner_with_buttons(self, call, state, text, reply_markup):
        """يحدث البانر ويرسل الأزرار في نفس الرسالة."""
        data = await state.get_data()
        banner_msg_id = data.get('banner_msg_id')
        if banner_msg_id:
            try:
                # نحاول نعدل الكابشن
                await call.bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=banner_msg_id,
                    caption=text,
                )
                # نضيف الـ reply_markup
                await call.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=banner_msg_id,
                    reply_markup=reply_markup,
                )
                return True
            except Exception:
                try:
                    await call.bot.edit_message_text(
                        text,
                        chat_id=call.message.chat.id,
                        message_id=banner_msg_id,
                        reply_markup=reply_markup,
                    )
                    return True
                except Exception:
                    pass
        return False

    # ────── دوال التحقق ──────

    def validate_proxy(self, proxy: str) -> Tuple[bool, Optional[str]]:
        if not proxy or proxy.strip().lower() == 'skip':
            return True, None
        proxy = proxy.strip()
        patterns = [
            r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$',
            r'^[a-zA-Z0-9._-]+:\d{2,5}$',
            r'^[a-zA-Z0-9._-]+:[a-zA-Z0-9@._-]+@[\d.a-zA-Z-]+:\d{2,5}$',
        ]
        for pattern in patterns:
            if re.match(pattern, proxy):
                return True, None
        return False, "❌ صيغة البروكسي غير صحيحة\nمثال: 1.2.3.4:8080 أو user:pass@1.2.3.4:8080"

    def validate_cookies(self, cookies: str) -> Tuple[bool, Optional[str]]:
        if not cookies or len(cookies.strip()) < 20:
            return False, "❌ الكوكيز مطلوب أو قصير جداً"
        # Accept ANY Meta cookies: Facebook, Instagram, Meta Business Suite, Workplace, etc.
        # As long as it has at least one valid Meta session indicator, accept it
        # Session indicators that mean valid Meta login: c_user, datr, sb, ps_l, ps_n, m_pixel_serva, fr, wd, spin
        session_indicators = ['c_user', 'datr', 'sb', 'ps_l', 'ps_n', 'm_pixel_serva', 'fr', 'wd', 'spin']
        found = [k for k in session_indicators if k in cookies]
        if not found:
            return False, "❌ الكوكيز لا يبدو ككوكيز ميتا صالح\n(يجب أن يحتوي على أحد هذه: c_user, datr, sb, ps_l, ps_n, m_pixel_serva, fr, wd, spin)"
        return True, None

    def validate_ad_account_id(self, account_id: str) -> Tuple[bool, Optional[str]]:
        if not account_id:
            return False, "❌ معرف الحساب الإعلاني مطلوب"
        account_id = account_id.strip().lstrip('act_')
        if not re.match(r'^\d{10,20}$', account_id):
            return False, "❌ معرف الحساب غير صحيح (10-20 رقم)\nمثال: 1234567890123"
        return True, account_id

    def validate_page_id(self, page_id: str) -> Tuple[bool, Optional[str]]:
        if not page_id:
            return False, "❌ معرف الصفحة مطلوب"
        page_id = page_id.strip()
        if not re.match(r'^\d{10,20}$', page_id):
            return False, "❌ معرف الصفحة غير صحيح (10-20 رقم)"
        return True, page_id

    def validate_post_link(self, link: str) -> Tuple[bool, Optional[str]]:
        if not link:
            return False, "❌ رابط أو معرف البوست مطلوب"
        link = link.strip()
        if 'facebook.com' in link or 'fb.watch' in link or re.match(r'^\d{10,30}$', link):
            return True, None
        return False, "❌ الرابط ليس رابط فيسبوك صحيح"

    def extract_post_id(self, text: str) -> Optional[str]:
        text = text.strip()
        if re.match(r'^\d{10,30}$', text):
            return text
        patterns = [
            r'/posts/(\d+)',
            r'story_fbid=(\d+)',
            r'pfbid(\w+)',
            r'/(\d{15,25})/?$',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                return m.group(1)
        parts = text.rstrip('/').split('/')
        for part in reversed(parts):
            part = part.split('?')[0]
            if re.match(r'^\d{10,30}$', part):
                return part
        return text.split('/')[-1].split('?')[0] or None

    def validate_budget(self, budget: str) -> Tuple[bool, any]:
        if not budget or budget.strip() in ['', 'skip']:
            return True, GateConstants.DEFAULT_BUDGET
        try:
            amount = float(budget.strip())
            if amount < GateConstants.MIN_BUDGET:
                return False, f"❌ الميزانية يجب أن تكون {GateConstants.MIN_BUDGET}$ على الأقل"
            if amount > GateConstants.MAX_BUDGET:
                return False, f"❌ الميزانية كبيرة جداً"
            return True, round(amount, 2)
        except ValueError:
            return False, "❌ الميزانية يجب أن تكون رقم مثل: 10 أو 15.5"

    def validate_days(self, days: str) -> Tuple[bool, any]:
        if not days or days.strip() in ['', 'skip']:
            return True, GateConstants.DEFAULT_DAYS
        try:
            amount = int(days.strip())
            if amount < GateConstants.MIN_DAYS:
                return False, f"❌ عدد الأيام يجب أن يكون {GateConstants.MIN_DAYS} على الأقل"
            if amount > GateConstants.MAX_DAYS:
                return False, f"❌ عدد الأيام كبير جداً"
            return True, amount
        except ValueError:
            return False, "❌ عدد الأيام يجب أن يكون رقم صحيح مثل: 7"

    def validate_audience_id(self, audience_id: str) -> Tuple[bool, Optional[str]]:
        if not audience_id or audience_id.strip().lower() in ['skip', '']:
            return True, None
        audience_id = audience_id.strip()
        if not re.match(r'^\d{10,30}$', audience_id):
            return False, "❌ معرف الأوديانس غير صحيح (أو اكتب skip)"
        return True, audience_id

    def validate_caption(self, caption: str) -> Tuple[bool, Optional[str]]:
        if not caption:
            return False, "❌ نص الإعلان مطلوب"
        caption = caption.strip()
        if len(caption) < GateConstants.MIN_CAPTION_LENGTH:
            return False, f"❌ النص قصير جداً ({GateConstants.MIN_CAPTION_LENGTH} حرف على الأقل)"
        if len(caption) > GateConstants.MAX_CAPTION_LENGTH:
            return False, f"❌ النص طويل جداً (الحد الأقصى {GateConstants.MAX_CAPTION_LENGTH} حرف)"
        return True, None

    def validate_ad_code(self, ad_code: str) -> Tuple[bool, Optional[str]]:
        if not ad_code or len(ad_code.strip()) < 5:
            return False, "❌ Ad Code مطلوب (5 أحرف على الأقل)"
        return True, None

    def validate_image_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        if not os.path.exists(file_path):
            return False, "❌ الملف غير موجود"
        ext = Path(file_path).suffix.lower()
        if ext not in GateConstants.IMAGE_EXTENSIONS:
            return False, f"❌ امتداد غير مدعوم"
        file_size = os.path.getsize(file_path)
        if file_size > GateConstants.MAX_IMAGE_SIZE:
            return False, f"❌ حجم الصورة كبير جداً (الحد 10MB)"
        return True, None

    async def save_image(self, message: Message) -> Tuple[bool, str, Optional[str]]:
        if not message.photo:
            return False, "❌ أرسل صورة وليس نص أو ملف آخر", None
        photo: PhotoSize = message.photo[-1]
        file_name = f"{self.gate_id}_{message.from_user.id}_{message.message_id}.jpg"
        file_path = TEMP_DIR / file_name
        try:
            await message.bot.download(file=photo.file_id, destination=file_path)
        except Exception as e:
            return False, f"❌ فشل تحميل الصورة: {str(e)}", None
        is_valid, error = self.validate_image_size(str(file_path))
        if not is_valid:
            if file_path.exists():
                file_path.unlink()
            return False, error, None
        return True, "✅ تم تحميل الصورة", str(file_path)

    def cleanup_temp_files(self, file_path: Optional[str]):
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    def format_summary(self, data: dict) -> str:
        lines = [
            "📋 <b>مراجعة البيانات</b>\n",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🎯 <b>البوابة:</b> {self.gate_name}",
            "",
            f"🌐 <b>البروكسي:</b> {data.get('proxy') or 'بدون'}",
            f"🍪 <b>الكوكيز:</b> {'✅ موجود' if data.get('cookies') else '❌ غير موجود'}",
            f"🔢 <b>Account ID:</b> {data.get('ad_account_id', 'غير محدد')}",
        ]
        if self.gate_type == 'standard_ad':
            lines += [
                f"📄 <b>Page ID:</b> {data.get('page_id', 'غير محدد')}",
                f"🔗 <b>Post ID:</b> {data.get('post_id', 'غير محدد')}",
            ]
        elif self.gate_type == 'dark_post':
            lines += [
                f"📄 <b>Page ID:</b> {data.get('page_id', 'غير محدد')}",
                f"🖼 <b>الصورة:</b> {'✅ موجودة' if data.get('image_path') else '❌ بدون صورة'}",
                f"📝 <b>النص:</b> {str(data.get('caption', ''))[:80]}...",
            ]
        elif self.gate_type == 'partner_ship':
            lines += [
                f"📦 <b>Ad Set ID:</b> {data.get('ad_set_id', 'غير محدد')}",
                f"📋 <b>Ad Code:</b> {data.get('ad_code', 'غير محدد')}",
            ]

        lines += [
            "",
            f"🎯 <b>الهدف:</b> {AdObjectives.get_display_name(data.get('objective', ''))}",
            f"👥 <b>Audience ID:</b> {data.get('audience_id') or 'افتراضي'}",
            f"💰 <b>الميزانية اليومية:</b> {data.get('daily_budget', GateConstants.DEFAULT_BUDGET)}$",
            f"📅 <b>عدد الأيام:</b> {data.get('days', GateConstants.DEFAULT_DAYS)}",
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "\n⚠️ هل تريد تأكيد التشغيل؟",
        ]
        return "\n".join(lines)
