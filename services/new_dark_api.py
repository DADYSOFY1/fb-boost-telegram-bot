# services/new_dark_api.py - Facebook Internal API (JAMAIKA-style)
from __future__ import annotations
import asyncio, json, re, uuid, random, time
from typing import Optional, Dict, Any
from pathlib import Path
import httpx
from services.fingerprints import DEVICE_PROFILES

FB_URL = "https://www.facebook.com"

GOAL_CONFIGS = {
    "MESSAGES":        {"ads_lwi_goal": "GET_MULTI_MESSAGES",  "objective": "MESSAGES",        "link": "msg"},
    "POST_ENGAGEMENT": {"ads_lwi_goal": "POST_ENGAGEMENT",     "objective": "POST_ENGAGEMENT", "link": "page"},
    "PAGE_LIKES":      {"ads_lwi_goal": "GET_PAGE_LIKES",      "objective": "PAGE_LIKES",      "link": "page"},
    "LINK_CLICKS":     {"ads_lwi_goal": "GET_WEBSITE_VISITORS","objective": "LINK_CLICKS",     "link": "page"},
}

GOAL_DISPLAY = {
    "MESSAGES":        "💬 رسائل ماسنجر",
    "POST_ENGAGEMENT": "📈 تفاعل مع البوست",
    "PAGE_LIKES":      "👍 إعجابات الصفحة",
    "LINK_CLICKS":     "🔗 نقرات على الرابط",
}

COUNTRY_DISPLAY = {
    "EG": "مصر",      "SA": "السعودية", "AE": "الإمارات",
    "KW": "الكويت",   "QA": "قطر",      "IQ": "العراق",
    "JO": "الأردن",   "MA": "المغرب",   "DZ": "الجزائر",
    "TN": "تونس",     "LY": "ليبيا",    "TR": "تركيا",
    "US": "أمريكا",   "GB": "بريطانيا",
}


def _parse_cookies(s):
    out = {}
    for p in s.split(";"):
        p = p.strip()
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _get_proxies(proxy):
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    return {"http://": proxy, "https://": proxy}


def _extract_dtsg(html):
    """
    يستخرج fb_dtsg من أي صفحة ميتا (فيسبوك، انستغرام، ميتا بيزنس).
    يدعم كل الصيغ المعروفة لتوكن ميتا.
    """
    # النمط 1: facebook.com -- DTSGInitialData JSON block (canonical)
    for pat in [
        r'"DTSGInitialData"[^}]{0,500}?"token":"([^"]{10,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)

    # النمط 2: facebook.com -- fb_dtsg input field
    m = re.search(r'name="fb_dtsg"\s+value="([^"]{10,})"', html)
    if m:
        return m.group(1)

    # النمط 3: Instagram/Meta -- require('DTSGInitialData')['token']
    for pat in [
        r'require\s*\(\s*["\']DTSGInitialData["\']\s*\)\s*\[\s*["\']token["\']\s*\]',
        r'require\s*\(\s*["\']DTSGInitialData["\']\s*\)\.token',
    ]:
        m = re.search(pat, html)
        if m:
            snippet = html[m.start():m.start() + 300]
            m2 = re.search(r'[\'"]([A-Za-z0-9_-]{10,})[\'"]', snippet)
            if m2:
                return m2.group(1)

    # النمط 4: Instagram internal token in JSON/JS blocks
    for pat in [
        r'"token":"(AQ[A-Za-z0-9_-]{20,})"',
        r'"dtsg":"(AQ[A-Za-z0-9_-]{20,})"',
        r'"async_dtsg":"(AQ[A-Za-z0-9_-]{20,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)

    # النمط 5: Meta Business / Business Manager
    m = re.search(
        r'DTSGInitialData["\']?\s*=\s*\{[^}]{0,1000}?token["\']?\s*[:=]\s*["\']([^"\']{10,})["\']',
        html,
    )
    if m:
        return m.group(1)

    # النمط 6: FB Lite / mobile -- Legi.token pattern
    for pat in [
        r'Legi\s*\.\s*token\s*=\s*["\']([A-Za-z0-9_-]{10,})["\']',
        r'Legi\s*\[\s*["\']token["\']\s*\]\s*=\s*["\']([A-Za-z0-9_-]{10,})["\']',
    ]:
        m = re.search(pat, html)
        if m:
            snippet = html[m.start():m.start() + 200]
            m2 = re.search(r'["\']([A-Za-z0-9_-]{10,})["\']', snippet)
            if m2:
                return m2.group(1)

    # النمط 7: Legacy fb_dtsg JSON
    for pat in [
        r'fb_dtsg["\']\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})["\']',
        r'"fb_dtsg":"([^"]{10,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)

    # النمط 8: Mobile/Lite dtsg= URL or form param
    m = re.search(r'dtsg=([A-Z0-9_-]{10,50})', html)
    if m:
        return m.group(1)

    # النمط 9: Instagram __dtsg
    m = re.search(r'__dtsg["\']\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})["\']', html)
    if m:
        return m.group(1)

    # النمط 10: window.__CONF / window.__SC token patterns
    for pat in [
        r'["\']token["\']\s*[:=]\s*["\']( AQ[A-Za-z0-9_-]{15,})["\']',
        r'token["\']\s*[:=]\s*["\']( AQ[A-Za-z0-9_-]{15,})["\']',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1).strip()

    # النمط 11: Meta internal __ModuleComponents / __bootloader
    for pat in [
        r'"clientid":["\'"]([A-Za-z0-9_-]{20,})["\']',
        r'"clientID":["\'"]([A-Za-z0-9_-]{20,})["\']',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)

    # النمط 12: __SARD pattern
    m = re.search(r'__SARD["\']\s*[:=]\s*["\']([A-Za-z0-9_-]{15,})["\']', html)
    if m:
        return m.group(1)

    return None


def _extract_lsd(html):
    """يستخرج lsd token من HTML الصفحة."""
    for pat in [
        r'"LSD"[^}]+?"token":"([^"]+)"',
        r'name="lsd"\s+value="([^"]+)"',
        r'"lsd":"([^"]{4,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


class NewDarkAPIClient:
    _DTSG_CACHE_TTL = 3600  # ثانية — نعيد الجلب بعد ساعة

    def __init__(self, cookies_str, proxy=None):
        self.cookies_dict = _parse_cookies(cookies_str)
        self.proxies = _get_proxies(proxy)
        self.user_id = self.cookies_dict.get("c_user", "")
        self._profile = random.choice(DEVICE_PROFILES)
        self._dtsg: Optional[str] = None
        self._lsd: Optional[str] = None
        self._dtsg_timestamp: float = 0

    def _hdrs(self):
        p = self._profile
        return {
            "User-Agent":      p["ua"],
            "Accept":          "*/*",
            "Accept-Language": p["accept_language"],
            "Content-Type":    "application/x-www-form-urlencoded",
            "Referer":         f"{FB_URL}/adsmanager/",
            "Origin":          FB_URL,
        }

    def _client(self):
        return httpx.AsyncClient(
            timeout=60, proxies=self.proxies, follow_redirects=True
        )

    def _parse_json(self, text):
        t = text.strip()
        if t.startswith("for(;;);"):
            t = t[8:].strip()
        return json.loads(t)

    async def fetch_dtsg(self):
        # إعادة الكاش إن كان لا يزال صالحاً
        now = time.time()
        if self._dtsg and (now - self._dtsg_timestamp < self._DTSG_CACHE_TTL):
            return {"success": True, "dtsg": self._dtsg, "user_id": self.user_id}

        if not self.user_id:
            return {"success": False, "error": "لم يتم العثور على c_user في الكوكيز"}

        try_urls = [
            f"{FB_URL}/adsmanager/manage/campaigns",
            f"{FB_URL}/",
            f"{FB_URL}/home.php",
            "https://www.instagram.com/",
            "https://www.instagram.com/accounts/manage_access/",
            "https://business.facebook.com/",
            "https://business.facebook.com/settings/business-information/",
            "https://business.facebook.com/ads/manager/",
        ]

        for try_url in try_urls:
            try:
                async with self._client() as c:
                    r = await c.get(
                        try_url,
                        headers={"User-Agent": self._profile["ua"]},
                        cookies=self.cookies_dict,
                    )
                    # الفحص على URL فقط — وليس محتوى الصفحة
                    url_str = str(r.url).lower()
                    if "login" in url_str or "checkpoint" in url_str:
                        continue
                    if r.status_code != 200:
                        continue
                    dtsg = _extract_dtsg(r.text)
                    if dtsg:
                        self._dtsg = dtsg
                        self._dtsg_timestamp = now
                        # استخراج lsd في نفس الطلب
                        lsd = _extract_lsd(r.text)
                        if lsd:
                            self._lsd = lsd
                        return {"success": True, "dtsg": dtsg, "user_id": self.user_id}
            except Exception:
                continue

        return {"success": False, "error": "الكوكيز منتهية أو غير صالحة"}

    async def _fetch_lsd(self):
        """يجلب lsd token من صفحة adsmanager."""
        if self._lsd:
            return self._lsd
        try:
            async with self._client() as c:
                r = await c.get(
                    f"{FB_URL}/adsmanager/",
                    headers={"User-Agent": self._profile["ua"]},
                    cookies=self.cookies_dict,
                    timeout=30,
                )
                lsd = _extract_lsd(r.text)
                if lsd:
                    self._lsd = lsd
                    return lsd
        except Exception:
            pass
        # fallback: أول 16 حرف من dtsg
        return self._dtsg[:16] if self._dtsg and len(self._dtsg) >= 16 else "KJmm"

    async def upload_image(self, act_id, image_bytes, filename="ad.jpg"):
        """
        يرفع صورة باستخدام React Composer endpoint الرسمي.
        
        Endpoint: /ajax/react_composer/attachments/photo/upload
        - URL params:  av, __user, __a, __aaid, fb_dtsg
        - FormData:    av, __user, __a, __aaid, fb_dtsg, lsd,
                       source, composer_session_id, farr (الملف)
        """
        if not self._dtsg:
            r = await self.fetch_dtsg()
            if not r["success"]:
                return r

        img_ext = Path(filename).suffix.lower() if filename else ".jpg"
        mime_map = {
            ".jpg":  "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png":  "image/png",
            ".gif":  "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(img_ext, "image/jpeg")

        lsd = await self._fetch_lsd()
        composer_session_id = str(uuid.uuid4())

        # ── URL params (مطلوبة على الـ endpoint نفسه) ──
        upload_url = (
            f"{FB_URL}/ajax/react_composer/attachments/photo/upload"
            f"?av={self.user_id}"
            f"&__user={self.user_id}"
            f"&__a=1"
            f"&__aaid=0"
            f"&fb_dtsg={self._dtsg}"
        )

        # ── FormData fields ──
        form_data = {
            "av":                   self.user_id,
            "__user":               self.user_id,
            "__a":                  "1",
            "__aaid":               "0",
            "fb_dtsg":              self._dtsg,
            "lsd":                  lsd,
            "source":               "composer",
            "composer_session_id":  composer_session_id,
        }

        try:
            async with self._client() as c:
                r = await c.post(
                    upload_url,
                    data=form_data,
                    files={
                        # ✅ "farr" هو اسم الحقل الصحيح في React Composer
                        "farr": (filename, image_bytes, mime),
                    },
                    headers={
                        "User-Agent": self._profile["ua"],
                        "Referer":    f"{FB_URL}/adsmanager/",
                        "Origin":     FB_URL,
                        "Accept":     "*/*",
                    },
                    cookies=self.cookies_dict,
                )

                if "login" in str(r.url).lower():
                    return {"success": False, "error": "الكوكيز انتهت أثناء رفع الصورة - جرب تحديث الكوكيز"}

                raw = r.text.strip()
                if raw.startswith("for(;;);"):
                    raw = raw[8:].strip()

                try:
                    data = json.loads(raw)
                except Exception:
                    return {
                        "success": False,
                        "error": f"رد غير صالح من سيرفر الرفع (HTTP {r.status_code}): {raw[:300]}"
                    }

                photo_id = (
                    data.get("payload", {}).get("photoID") or
                    data.get("photoID") or
                    data.get("image_hash") or
                    data.get("hash")
                )

                if photo_id and len(str(photo_id)) > 3:
                    return {"success": True, "image_hash": str(photo_id)}

                # إرجاع الرد الفعلي لتسهيل التشخيص
                return {
                    "success": False,
                    "error": f"فشل رفع الصورة - رد غير متوقع: {str(data)[:400]}"
                }

        except Exception as e:
            return {"success": False, "error": f"فشل رفع الصورة - خطأ في الشبكة: {e}"}

    async def create_and_pause(
        self,
        act_id,
        page_id,
        image_hash,
        message,
        goal,
        budget_usd,
        days,
        country,
        age_min=18,
        age_max=65,
        gender=None,          # ← جديد: None | "MALE" | "FEMALE"
    ):
        if not self._dtsg:
            r = await self.fetch_dtsg()
            if not r["success"]:
                return r

        clean_act = act_id.replace("act_", "").strip()
        cfg = GOAL_CONFIGS.get(goal, GOAL_CONFIGS["MESSAGES"])
        pl = (
            f"{FB_URL}/messages/t/{page_id}"
            if cfg["link"] == "msg"
            else f"{FB_URL}/{page_id}"
        )

        if goal == "MESSAGES":
            cta = {"type": "MESSAGE_PAGE", "value": {"app_destination": "MESSENGER", "link": pl}}
        elif goal == "LINK_CLICKS":
            cta = {"type": "LEARN_MORE", "value": {"link": pl}}
        else:
            cta = {"type": "LIKE_PAGE", "value": {"page": page_id}}

        # بناء targeting مع دعم الجنس الاختياري
        tgt_dict: Dict[str, Any] = {
            "age_min": age_min,
            "age_max": age_max,
            "geo_locations": {
                "countries":       [country],
            },
        }
        if gender in ("MALE", "FEMALE"):
            tgt_dict["genders"] = [1] if gender == "MALE" else [2]

        tgt = json.dumps(tgt_dict, separators=(",", ":"))

        creative_spec = {
            "degrees_of_freedom_spec": {
                "creative_features_spec": {
                    "product_extensions": {
                        "action_metadata": {"type": "UNKOWN"},
                        "enroll_status":   "OPT_OUT",
                    }
                },
                "degrees_of_freedom_type": "USER_ENROLLED_LWI_ACO",
            },
            "object_story_spec": {
                "page_id": page_id,
            },
        }
        
        # استخدام photo_data إذا كان هناك صورة، وإلا link_data فقط
        if image_hash:
            creative_spec["object_story_spec"]["photo_data"] = {
                "image_hash": image_hash,
                "message":    message,
            }
            creative_spec["object_story_spec"]["link_data"] = {
                "call_to_action": cta,
                "message":        message,
            }
        else:
            creative_spec["object_story_spec"]["link_data"] = {
                "call_to_action": cta,
                "message":        message,
            }

        variables = {
            "input": {
                "boost_id": None,
                "creation_spec": {
                    "ab_test_audiences": [
                        {"audience_option": "NCPP", "targeting_spec_string": tgt}
                    ],
                    "ads_lwi_goal":          cfg["ads_lwi_goal"],
                    "audience_option":       "NCPP",
                    "billing_event":         "IMPRESSIONS",
                    "budget":                int(budget_usd * 100),
                    "budget_type":           "DAILY_BUDGET",
                    "currency":              "USD",
                    "dayparting_specs":      [],
                    "dsa_beneficiary":       "",
                    "dsa_payor":             "",
                    "duration_in_days":      days,
                    "enable_clo":            False,
                    "impression_id":         str(uuid.uuid4()),
                    "is_automatic_goal":     False,
                    "is_budget_flex":        False,
                    "legacy_ad_account_id":  clean_act,
                    "legacy_entry_point":    "www_profile_plus_timeline",
                    "pacing_type":           None,
                    "pixel_id":              None,
                    "placement_spec":        {"publisher_platforms": ["FACEBOOK", "MESSENGER"]},
                    "regulated_category":    "NONE",
                    "run_continuously":      False,
                    "sabr_version":          "v1_v2",
                    "surface":               "BIZ_WEB",
                    "targeting_spec_string": tgt,
                    "adgroup_specs": [
                        {
                            "creative": creative_spec,
                        }
                    ],
                    "objective": cfg["objective"],
                },
                "flow_id":           str(uuid.uuid4()),
                "lwi_asset_id":      {"id": page_id},
                "page_id":           page_id,
                "product":           "BOOSTED_CONSOLIDATED_PRODUCT",
                "target_id":         page_id,
                "actor_id":          self.user_id,
                "client_mutation_id": "1",
            }
        }

        mutation_names = ["CreateBoostedComponent", "AdsCreationMutation", "BoostedComponentMutation"]
        cr = None
        for mut_name in mutation_names:
            cr = await self._gql(variables, mut_name)
            if cr["success"]:
                break
        
        if not cr or not cr["success"]:
            return cr if cr else {"success": False, "error": "فشل الاتصال بـ GraphQL"}

        cid = (
            cr.get("data", {}).get("create_boosted_component", {}).get("campaign", {}).get("id")
            or cr.get("data", {}).get("create_boosted_component", {}).get("id")
            or cr.get("data", {}).get("ads_creation", {}).get("campaign", {}).get("id")
        )
        if not cid:
            return {
                "success": False,
                "error": f'Campaign ID not found: {str(cr.get("data", ""))[:200]}',
            }

        await asyncio.sleep(1.5)
        pr = await self._pause(cid, clean_act)
        return {
            "success":      True,
            "campaign_id":  cid,
            "paused":       pr.get("success", False),
            "pause_error":  pr.get("error") if not pr.get("success") else None,
        }

    async def _gql(self, variables, name):
        body = {
            "fb_dtsg":                  self._dtsg,
            "av":                       self.user_id,
            "__user":                   self.user_id,
            "__a":                      "1",
            "variables":                json.dumps(variables, separators=(",", ":")),
            "fb_api_caller_class":      "RelayModern",
            "fb_api_req_friendly_name": name,
            "server_timestamps":        "true",
        }
        try:
            async with self._client() as c:
                r = await c.post(
                    f"{FB_URL}/api/graphql/",
                    data=body,
                    headers={
                        **self._hdrs(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    cookies=self.cookies_dict,
                )
                if "login" in str(r.url).lower():
                    return {"success": False, "error": "الكوكيز انتهت"}
                try:
                    data = self._parse_json(r.text)
                except Exception:
                    return {"success": False, "error": f"رد GraphQL غير صالح: {r.text[:300]}"}
                if "errors" in data and data["errors"]:
                    return {
                        "success": False,
                        "error":   f'FB Error: {data["errors"][0].get("message", "?")}',
                    }
                return {"success": True, "data": data.get("data", {})}
        except Exception as e:
            return {"success": False, "error": f"خطأ: {e}"}

    async def _pause(self, campaign_id, act_id):
        r = await self._gql(
            {
                "input": {
                    "campaigns":          [{"id": campaign_id, "status": "PAUSED"}],
                    "act_id":             act_id,
                    "client_mutation_id": "2",
                }
            },
            "AdCampaignSetStatusMutation",
        )
        if r.get("success"):
            return r
        return await self._gql(
            {
                "input": {
                    "id":            campaign_id,
                    "status":        "PAUSED",
                    "ad_account_id": act_id,
                }
            },
            "UpdateCampaignStatus",
        )
