# gates/new_dark_gate.py - New Dark Gate (محسن بالكامل)
from __future__ import annotations
from pathlib import Path
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from keyboards import (
    back_home, proxy_selection_keyboard, back_to_proxy,
    nd_country_keyboard, nd_goal_keyboard, nd_age_keyboard, nd_gender_keyboard,
    image_received_keyboard, cancel_keyboard, nd_confirm_keyboard
)
from states import NewDarkStates, GateConstants
from gates.base_gate import BaseGate
from services.new_dark_api import NewDarkAPIClient, GOAL_DISPLAY, COUNTRY_DISPLAY
from services.proxy_manager import ProxyManager
proxy_manager = ProxyManager('proxies.txt')


class NewDarkGate(BaseGate):
    def __init__(self):
        super().__init__("new_dark", "⚡ New Dark Post", "new_dark")

    async def enter(self, call: CallbackQuery, state: FSMContext, config: dict):
        await state.update_data(gate_id=self.gate_id, gate_type=self.gate_type, gate_name=self.gate_name)
        await state.set_state(NewDarkStates.waiting_proxy)
        await self.send_banner(call, state,
            caption=(
                f"🚪 <b>{self.gate_name}</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "بروكسي → كوكيز → Account → Page → دولة → هدف → عمر → جنس → صورة (اختياري) → نص → ميزانية → تشغيل\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔽 <b>الخطوة 1:</b> اختر البروكسي"
            ),
            reply_markup=proxy_selection_keyboard())

    async def _upd(self, target, state, text, kb=None):
        if isinstance(target, CallbackQuery):
            await self.edit_step(target, state, text, reply_markup=kb)
        else:
            await self.delete_user_message(target, state)
            await self.update_banner_caption(target.bot, target.chat.id, state, text, reply_markup=kb, parse_mode="HTML")

    # ────── Cancel Handler ──────
    async def handle_cancel(self, call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        self.cleanup_temp_files(data.get("image_path"))
        await state.clear()
        await self.edit_step(call, state, "❌ <b>تم إلغاء العملية</b>", reply_markup=back_home())
        await call.answer("تم الإلغاء")

    # ────── Proxy Steps ──────
    async def handle_proxy_auto(self, call, state, proxy=None):
        if proxy is None:
            proxy_val = proxy_manager.choose() if proxy_manager else None
        else:
            proxy_val = proxy
        await state.update_data(proxy=proxy_val)
        await state.set_state(NewDarkStates.waiting_cookies)
        await self._upd(call, state, "✅ <b>البروكسي:</b> تم اختياره\n\n━━━━━━━━━━━━━━━━━━━━\n🔽 <b>الخطوة 2:</b> أرسل الكوكيز", kb=back_to_proxy())

    async def handle_proxy_skip(self, call, state):
        await state.update_data(proxy=None)
        await state.set_state(NewDarkStates.waiting_cookies)
        await self._upd(call, state, "⏭ <b>بدون بروكسي</b>\n\n━━━━━━━━━━━━━━━━━━━━\n🔽 <b>الخطوة 2:</b> أرسل الكوكيز", kb=back_to_proxy())

    async def handle_proxy_custom(self, message, state):
        ok, err = self.validate_proxy(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {err}", kb=proxy_selection_keyboard())
            return
        proxy = message.text.strip() if message.text.strip().lower() != "skip" else None
        await state.update_data(proxy=proxy)
        await state.set_state(NewDarkStates.waiting_cookies)
        await self._upd(message, state, f"✅ <b>البروكسي:</b> {proxy or 'بدون'}", kb=back_to_proxy())

    async def handle_proxy_back(self, call, state):
        await state.set_state(NewDarkStates.waiting_proxy)
        await self._upd(call, state, "🔽 <b>اختر البروكسي</b>", kb=proxy_selection_keyboard())

    # ────── Cookies & Account ──────
    async def handle_cookies(self, message, state):
        ok, err = self.validate_cookies(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {err}", kb=back_home())
            return
        await state.update_data(cookies=message.text.strip())
        await state.set_state(NewDarkStates.waiting_ad_account_id)
        await self._upd(message, state, "✅ <b>تم حفظ الكوكيز</b>\n\n🔽 <b>الخطوة 3:</b> أدخل Ad Account ID", kb=back_home())

    async def handle_ad_account_id(self, message, state):
        ok, result = self.validate_ad_account_id(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {result}", kb=back_home())
            return
        await state.update_data(ad_account_id=result)
        await state.set_state(NewDarkStates.waiting_page_id)
        await self._upd(message, state, f"✅ <b>Account ID:</b> <code>{result}</code>\n\n🔽 <b>الخطوة 4:</b> أدخل Page ID", kb=back_home())

    async def handle_page_id(self, message, state):
        ok, result = self.validate_page_id(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {result}", kb=back_home())
            return
        await state.update_data(page_id=result)
        await state.set_state(NewDarkStates.waiting_country)
        await self._upd(message, state, f"✅ <b>Page ID:</b> <code>{result}</code>\n\n🔽 <b>الخطوة 5:</b> اختر الدولة", kb=nd_country_keyboard())

    # ────── Targeting (Country → Goal → Age → Gender) ──────
    async def handle_country(self, call, state, country):
        await state.update_data(country=country)
        await state.set_state(NewDarkStates.waiting_goal)
        await self._upd(call, state, f"✅ <b>الدولة:</b> {COUNTRY_DISPLAY.get(country, country)}\n\n🔽 <b>الخطوة 6:</b> اختر الهدف", kb=nd_goal_keyboard())

    async def handle_goal(self, call, state, goal):
        await state.update_data(goal=goal)
        await state.set_state(NewDarkStates.waiting_age)
        gname = GOAL_DISPLAY.get(goal, goal)
        await self._upd(
            call,
            state,
            f"✅ <b>الهدف:</b> {gname}\n\n🔽 <b>الخطوة 7:</b> اختر نطاق العمر\nيمكنك كتابة مثال: <code>18-45</code>",
            kb=nd_age_keyboard()
        )

    async def handle_age(self, message_or_call, state):
        if isinstance(message_or_call, CallbackQuery):
            age_range = ':'.join(message_or_call.data.split(':')[2:])
        else:
            age_range = message_or_call.text.strip()

        try:
            if '-' in age_range:
                min_age, max_age = map(int, age_range.split('-'))
            else:
                min_age = max_age = int(age_range)
            await state.update_data(age_min=min_age, age_max=max_age)
        except Exception:
            await self._upd(message_or_call, state, "❌ صيغة خاطئة. مثال: 18-45", kb=cancel_keyboard())
            return

        await state.set_state(NewDarkStates.waiting_gender)
        await self._upd(message_or_call, state, "🔽 <b>الخطوة 8:</b> اختر الجنس", kb=nd_gender_keyboard())

    async def handle_gender(self, call, state, gender):
        await state.update_data(gender=gender)
        await state.set_state(NewDarkStates.waiting_image)
        await self._upd(call, state,
            "✅ تم حفظ الاستهداف\n\n"
            "🔽 <b>الخطوة 9:</b> أرسل صورة الإعلان (اختياري)\n"
            "أو اضغط ⏭️ تخطي الصورة",
            kb=image_received_keyboard())

    # ────── Image Back (re-upload) ──────
    async def handle_image_back(self, call, state):
        data = await state.get_data()
        self.cleanup_temp_files(data.get("image_path"))
        await state.update_data(image_path=None)
        await state.set_state(NewDarkStates.waiting_image)
        await self._upd(call, state,
            "🔄 <b>أعد إرسال الصورة</b>\nأو اضغط ⏭️ تخطي الصورة",
            kb=image_received_keyboard())

    # ────── Image (Optional) ──────
    async def handle_image(self, message, state):
        ok, err, path = await self.save_image(message)
        if not ok:
            await self._upd(message, state, f"❌ {err}", kb=cancel_keyboard())
            return
        await state.update_data(image_path=path)
        await state.set_state(NewDarkStates.waiting_caption)
        await self._upd(message, state, "✅ <b>تم حفظ الصورة</b>\n\n🔽 <b>الخطوة 10:</b> أدخل نص الإعلان", kb=cancel_keyboard())

    async def handle_image_skip(self, call, state):
        await state.update_data(image_path=None)
        await state.set_state(NewDarkStates.waiting_caption)
        await self._upd(call, state, "⏭ <b>تم تخطي الصورة</b>\n\n🔽 <b>الخطوة 10:</b> أدخل نص الإعلان", kb=cancel_keyboard())

    async def handle_caption(self, message, state):
        ok, err = self.validate_caption(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {err}", kb=cancel_keyboard())
            return
        await state.update_data(caption=message.text.strip())
        await state.set_state(NewDarkStates.waiting_daily_budget)
        await self._upd(message, state, f"✅ <b>تم حفظ النص</b>\n\n🔽 <b>الخطوة 11:</b> أدخل الميزانية اليومية ($)", kb=cancel_keyboard())

    # ────── Budget & Days & Confirm ──────
    async def handle_daily_budget(self, message, state):
        ok, result = self.validate_budget(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {result}", kb=cancel_keyboard())
            return
        await state.update_data(daily_budget=result)
        await state.set_state(NewDarkStates.waiting_days)
        await self._upd(message, state, f"✅ <b>الميزانية:</b> {result}$\n\n🔽 <b>الخطوة 12:</b> أدخل عدد الأيام", kb=cancel_keyboard())

    async def handle_days(self, message, state):
        ok, result = self.validate_days(message.text)
        if not ok:
            await self._upd(message, state, f"❌ {result}", kb=cancel_keyboard())
            return
        await state.update_data(days=result)
        await state.set_state(NewDarkStates.waiting_confirm)
        data = await state.get_data()
        summary = self.format_new_dark_summary(data)
        await self._upd(message, state, summary, kb=nd_confirm_keyboard())

    def format_new_dark_summary(self, data):
        return (
            "📋 <b>مراجعة New Dark Post</b>\n\n"
            f"🏦 Account: <code>{data.get('ad_account_id')}</code>\n"
            f"📄 Page: <code>{data.get('page_id')}</code>\n"
            f"🌍 الدولة: {COUNTRY_DISPLAY.get(data.get('country'))}\n"
            f"🎯 الهدف: {GOAL_DISPLAY.get(data.get('goal'))}\n"
            f"👤 العمر: {data.get('age_min')}-{data.get('age_max')}\n"
            f"⚤ الجنس: {data.get('gender','الكل')}\n"
            f"💬 النص: {data.get('caption','')[:60]}...\n"
            f"💰 الميزانية: {data.get('daily_budget')}$ يومياً\n"
            f"📅 المدة: {data.get('days')} أيام\n"
            f"🖼 الصورة: {'موجودة' if data.get('image_path') else 'بدون'}\n\n"
            "هل تريد المتابعة؟"
        )

    async def handle_confirm(self, call, state):
        if "no" in call.data:
            data = await state.get_data()
            self.cleanup_temp_files(data.get("image_path"))
            await state.clear()
            await self.edit_step(call, state, "❌ تم الإلغاء", reply_markup=back_home())
            return

        await self.edit_step(call, state, 
            "⏳ <b>جاري إنشاء New Dark Post...</b>\n\n"
            "1️⃣ جلب fb_dtsg ⏳\n"
            "2️⃣ رفع الصورة ⏳\n"
            "3️⃣ إنشاء الحملة ⏳\n\nيرجى الانتظار...", 
            kb=cancel_keyboard())

        try:
            data = await state.get_data()
            client = NewDarkAPIClient(data.get("cookies"), data.get("proxy"))
            
            r1 = await client.fetch_dtsg()
            if not r1["success"]:
                await self.edit_step(call, state, f"❌ {r1['error']}", reply_markup=back_home())
                return

            img_path = data.get("image_path")
            image_hash = None
            if img_path:
                with open(img_path, "rb") as f:
                    img_bytes = f.read()
                r2 = await client.upload_image(data.get("ad_account_id"), img_bytes, Path(img_path).name)
                if not r2["success"]:
                    await self.edit_step(call, state, f"❌ {r2['error']}", reply_markup=back_home())
                    return
                image_hash = r2["image_hash"]

            r3 = await client.create_and_pause(
                act_id=data.get("ad_account_id"),
                page_id=data.get("page_id"),
                image_hash=image_hash,
                message=data.get("caption",""),
                goal=data.get("goal"),
                budget_usd=float(data.get("daily_budget", 5)),
                days=int(data.get("days", 4)),
                country=data.get("country","EG"),
                age_min=data.get("age_min",18),
                age_max=data.get("age_max",65),
                gender=data.get("gender") if data.get("gender") != "all" else None
            )

            self.cleanup_temp_files(img_path)
            if r3["success"]:
                await self.edit_step(call, state, 
                    f"✅ <b>تم إنشاء New Dark Post بنجاح!</b>\n\n"
                    f"📊 Campaign ID: <code>{r3.get('campaign_id')}</code>\n"
                    "⏸ تم الإيقاف تلقائياً", reply_markup=back_home())
            else:
                await self.edit_step(call, state, f"❌ {r3.get('error')}", reply_markup=back_home())

        except Exception as e:
            await self.edit_step(call, state, f"❌ خطأ: {str(e)[:200]}", reply_markup=back_home())
