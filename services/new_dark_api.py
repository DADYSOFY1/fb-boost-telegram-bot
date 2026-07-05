# services/new_dark_api.py
from __future__ import annotations
import asyncio, json, re, uuid, random, time
from typing import Optional, Dict, Any
from pathlib import Path
import httpx
from services.fingerprints import DEVICE_PROFILES

FB_URL = "https://www.facebook.com"

GOAL_CONFIGS = {
    "MESSAGES":        {"ads_lwi_goal": "GET_MULTI_MESSAGES",   "objective": "MESSAGES",        "link": "msg"},
    "POST_ENGAGEMENT": {"ads_lwi_goal": "POST_ENGAGEMENT",      "objective": "POST_ENGAGEMENT", "link": "page"},
    "PAGE_LIKES":      {"ads_lwi_goal": "GET_PAGE_LIKES",       "objective": "PAGE_LIKES",      "link": "page"},
    "LINK_CLICKS":     {"ads_lwi_goal": "GET_WEBSITE_VISITORS", "objective": "LINK_CLICKS",     "link": "page"},
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
    for pat in [
        r'"DTSGInitialData"[^}]{0,500}?"token":"([^"]{10,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    m = re.search(r'name="fb_dtsg"\s+value="([^"]{10,})"', html)
    if m:
        return m.group(1)
    for pat in [
        r'"token":"(AQ[A-Za-z0-9_-]{20,})"',
        r'"dtsg":"(AQ[A-Za-z0-9_-]{20,})"',
        r'"async_dtsg":"(AQ[A-Za-z0-9_-]{20,})"',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    m = re.search(
        r'DTSGInitialData["\']?\s*=\s*\{[^}]{0,1000}?token["\']?\s*[:=]\s*["\']([^"\']{10,})["\']',
        html,
    )
    if m:
        return m.group(1)
    for pat in [
        r'"fb_dtsg":"([^"]{10,})"',
        r'fb_dtsg["\']?\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})["\']',
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    m = re.search(r'__dtsg["\']?\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})["\']', html)
    if m:
        return m.group(1)
    return None


class NewDarkAPIClient:
    _DTSG_CACHE_TTL = 3600

    def __init__(self, cookies_str, proxy=None):
        self.cookies_dict = _parse_cookies(cookies_str)
        self.proxies = _get_proxies(proxy)
        self.user_id = self.cookies_dict.get("c_user", "")
        self._profile = random.choice(DEVICE_PROFILES)
        self._dtsg: Optional[str] = None
        self._dtsg_timestamp: float = 0

    def _hdrs(self):
        p = self._profile
        return {
            "User-Agent":      p["ua"],
            "Accept":          "*/*",
            "Accept-Language": p.get("accept_language", p.get("lang", "ar,en;q=0.9")),
            "Content-Type":    "application/x-www-form-urlencoded",
            "Referer":         f"{FB_URL}/adsmanager/",
            "Origin":          FB_URL,
        }

    def _client(self):
        return httpx.AsyncClient(timeout=60, proxies=self.proxies, follow_redirects=True)

    def _parse_json(self, text):
        t = text.strip()
        if t.startswith("for(;;);"):
            t = t[8:].strip()
        return json.loads(t)

    async def fetch_dtsg(self):
        now = time.time()
        if self._dtsg and (now - self._dtsg_timestamp < self._DTSG_CACHE_TTL):
            return {"success": True, "dtsg": self._dtsg, "user_id": self.user_id}

        if not self.user_id:
            return {"success": False, "error": "لم يتم العثور على c_user في الكوكيز"}

        try_urls = [
            f"{FB_URL}/adsmanager/manage/campaigns",
            f"{FB_URL}/",
            f"{FB_URL}/home.php",
            "https://business.facebook.com/",
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
                    url_str = str(r.url).lower()
                    if "login" in url_str or "checkpoint" in url_str:
                        continue
                    dtsg = _extract_dtsg(r.text)
                    if dtsg:
                        self._dtsg = dtsg
                        self._dtsg_timestamp = now
                        return {"success": True, "dtsg": dtsg, "user_id": self.user_id}
            except Exception:
                continue

        return {"success": False, "error": "الكوكيز منتهية أو غير صالحة"}

    async def upload_image(self, act_id, image_bytes, filename="ad.jpg"):
        if not self._dtsg:
            r = await self.fetch_dtsg()
            if not r["success"]:
                return r

        clean_act = act_id.replace("act_", "").strip()
        img_ext = Path(filename).suffix.lower() if filename else ".jpg"
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png",  ".gif":  "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(img_ext, "image/jpeg")

        endpoints = [
            f"{FB_URL}/ajax/ads/upload_partner_creative_image/",
            f"{FB_URL}/ads/creative/upload/",
            f"{FB_URL}/ajax/ads/async_image_upload.php",
        ]

        for url in endpoints:
            try:
                async with self._client() as c:
                    r = await c.post(
                        url,
                        files={
                            "fb_dtsg": (None, self._dtsg),
                            "av":      (None, self.user_id),
                            "act":     (None, clean_act),
                            "__a":     (None, "1"),
                            "file":    (filename, image_bytes, mime),
                        },
                        headers={
                            "User-Agent": self._profile["ua"],
                            "Referer":    f"{FB_URL}/adsmanager/",
                            "Origin":     FB_URL,
                        },
                        cookies=self.cookies_dict,
                    )
                    if "login" in str(r.url).lower():
                        return {"success": False, "error": "الكوكيز انتهت"}

                    raw = r.text.strip()
                    if raw.startswith("for(;;);"):
                        raw = raw[8:].strip()
                    if not raw or raw[0] not in ('{', '['):
                        continue

                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue

                    def extract_hash(d):
                        return (d.get("hash") or d.get("image_hash") or
                                d.get("id") or d.get("upload_id"))

                    imgs = (data.get("images") or
                            data.get("payload", {}).get("images") or
                            data.get("data", {}).get("images"))

                    if isinstance(imgs, dict) and imgs:
                        for k, v in imgs.items():
                            h = extract_hash(v) if isinstance(v, dict) else (v if isinstance(v, str) else None)
                            if h and len(str(h)) > 3:
                                return {"success": True, "image_hash": h}

                    if isinstance(data, dict):
                        h = extract_hash(data)
                        if not h and isinstance(data.get("result"), dict):
                            h = extract_hash(data["result"])
                        if h:
                            return {"success": True, "image_hash": h}
            except Exception:
                continue

        return {"success": False, "error": "❌ فشل رفع الصورة - جرب JPG أو PNG"}

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
        gender=None,   # None | "MALE" | "FEMALE"
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

        tgt_dict: Dict[str, Any] = {
            "age_min": age_min,
            "age_max": age_max,
            "geo_locations": {
                "countries":      [country],
                "location_types": ["home", "recent"],
            },
            "targeting_optimization": "expansion_all",
            "targeting_automation":   {"advantage_audience": 1},
        }
        if gender in ("MALE", "FEMALE"):
            tgt_dict["genders"] = [1] if gender == "MALE" else [2]

        tgt = json.dumps(tgt_dict, separators=(",", ":"))

        variables = {
            "input": {
                "boost_id": None,
                "creation_spec": {
                    "ab_test_audiences": [
                        {"audience_option": "NCPP", "targeting_spec_string": tgt}
                    ],
                    "ads_lwi_goal":         cfg["ads_lwi_goal"],
                    "audience_option":      "NCPP",
                    "billing_event":        "IMPRESSIONS",
                    "budget":               int(budget_usd * 100),
                    "budget_type":          "DAILY_BUDGET",
                    "currency":             "USD",
                    "dayparting_specs":     [],
                    "dsa_beneficiary":      "",
                    "dsa_payor":            "",
                    "duration_in_days":     days,
                    "enable_clo":           False,
                    "impression_id":        str(uuid.uuid4()),
                    "is_automatic_goal":    False,
                    "is_budget_flex":       False,
                    "legacy_ad_account_id": clean_act,
                    "legacy_entry_point":   "www_profile_plus_timeline",
                    "pacing_type":          None,
                    "pixel_id":             None,
                    "placement_spec":       {"publisher_platforms": ["FACEBOOK", "MESSENGER"]},
                    "regulated_category":   "NONE",
                    "run_continuously":     False,
                    "sabr_version":         "v1_v2",
                    "surface":              "BIZ_WEB",
                    "targeting_spec_string": tgt,
                    "adgroup_specs": [
                        {
                            "creative": {
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
                                    "link_data": {
                                        "call_to_action": cta,
                                        "image_hash":     image_hash,
                                        "link":           pl,
                                        "message":        message,
                                    },
                                    "page_id": page_id,
                                },
                            }
                        }
                    ],
                    "objective": cfg["objective"],
                },
                "flow_id":            str(uuid.uuid4()),
                "lwi_asset_id":       {"id": page_id},
                "page_id":            page_id,
                "product":            "BOOSTED_CONSOLIDATED_PRODUCT",
                "target_id":          page_id,
                "actor_id":           self.user_id,
                "client_mutation_id": "1",
            }
        }

        cr = await self._gql(variables, "CreateBoostedComponent")
        if not cr["success"]:
            return cr

        cid = (
            cr.get("data", {}).get("create_boosted_component", {}).get("campaign", {}).get("id")
            or cr.get("data", {}).get("create_boosted_component", {}).get("id")
        )
        if not cid:
            return {"success": False, "error": f'Campaign ID not found: {str(cr.get("data",""))[:200]}'}

        await asyncio.sleep(1.5)
        pr = await self._pause(cid, clean_act)
        return {
            "success":     True,
            "campaign_id": cid,
            "paused":      pr.get("success", False),
            "pause_error": pr.get("error") if not pr.get("success") else None,
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
                    headers=self._hdrs(),
                    cookies=self.cookies_dict,
                )
                if "login" in str(r.url).lower():
                    return {"success": False, "error": "الكوكيز انتهت"}
                try:
                    data = self._parse_json(r.text)
                except Exception:
                    return {"success": False, "error": f"رد GraphQL غير صالح: {r.text[:300]}"}
                if "errors" in data and data["errors"]:
                    return {"success": False, "error": f'FB Error: {data["errors"][0].get("message","?")}'}
                return {"success": True, "data": data.get("data", {})}
        except Exception as e:
            return {"success": False, "error": f"خطأ: {e}"}

    async def _pause(self, campaign_id, act_id):
        r = await self._gql(
            {"input": {"campaigns": [{"id": campaign_id, "status": "PAUSED"}], "act_id": act_id, "client_mutation_id": "2"}},
            "AdCampaignSetStatusMutation",
        )
        if r.get("success"):
            return r
        return await self._gql(
            {"input": {"id": campaign_id, "status": "PAUSED", "ad_account_id": act_id}},
            "UpdateCampaignStatus",
        )
