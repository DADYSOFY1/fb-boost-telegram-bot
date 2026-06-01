"""
bm_card_service.py
خدمة تسميع البطاقات من Business Manager
منطق مطابق تماماً للـ Bookmarklet المرجعي
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from services.fingerprints import DEVICE_PROFILES

BM_BASE  = 'https://business.facebook.com'
GRAPHQL  = f'{BM_BASE}/api/graphql/'


def _parse_cookies(s: str) -> dict:
    out = {}
    for part in s.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def _get_proxies(proxy: Optional[str]) -> Optional[dict]:
    if not proxy:
        return None
    if '://' not in proxy:
        proxy = f'http://{proxy}'
    return {'http://': proxy, 'https://': proxy}


def _extract_dtsg(html: str) -> Optional[str]:
    """
    يستخرج fb_dtsg من أي صفحة ميتا (فيسبوك، انستغرام، ميتا بيزنس).
    يدعم كل الصيغ المعروفة لتوكن ميتا.
    """
    patterns = [
        # 1. facebook.com -- DTSGInitialData JSON block (canonical)
        (r'"DTSGInitialData"[^}]{0,500}?"token":"([^"]{10,})"', 1),
        # 2. facebook.com -- fb_dtsg input field
        (r'name="fb_dtsg"\s+value="([^"]{10,})"', 1),
        # 3. Instagram/Meta -- require('DTSGInitialData')['token'] or .token
        (r'require\s*\(\s*["\']DTSGInitialData["\']\s*\)\s*[\[\."\'](token)["\']?\s*[\]:]?', 0),
        # 4. Instagram internal token
        (r'"token":"(AQ[A-Za-z0-9_-]{20,})"', 1),
        (r'"dtsg":"(AQ[A-Za-z0-9_-]{20,})"', 1),
        # 5. Meta Business Suite
        (r'DTSGInitialData["\']?\s*=\s*\{[^}]{0,1000}?token["\']?\s*[:=]\s*["\']([^"\']{10,})["\']', 1),
        # 6. FB Lite / mobile -- Legi.token
        (r'Legi\s*\.\s*token\s*=\s*["\']([A-Za-z0-9_-]{10,})["\']', 1),
        # 7. Legacy fb_dtsg JSON
        (r'"fb_dtsg":"([^"]{10,})"', 1),
        (r'fb_dtsg["\']?\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})["\']', 1),
        # 8. Mobile/Lite dtsg= URL or form param
        (r'dtsg=([A-Z0-9_-]{10,50})', 1),
        # 9. Instagram __dtsg
        (r'__dtsg["\']?\s*[:=]\s*["\']([A-Za-z0-9_-]{10,})["\']', 1),
        # 10. Generic AQ token
        (r'"token"\s*:\s*"(AQ[A-Za-z0-9_-]{15,})"', 1),
    ]
    for pat, group_idx in patterns:
        m = re.search(pat, html)
        if m:
            if group_idx == 0:
                snippet = html[m.start():m.start() + 300]
                m2 = re.search(r'["\']([A-Za-z0-9_-]{10,})["\']', snippet)
                if m2:
                    return m2.group(1)
            else:
                return m.group(1)
    return None


class BMCardService:
    def __init__(self, cookies_str: str, proxy: Optional[str] = None):
        self.cookies_str  = cookies_str
        self.cookies_dict = _parse_cookies(cookies_str)
        self.proxies      = _get_proxies(proxy)
        self._dtsg: Optional[str] = None
        self._user_id: str = self.cookies_dict.get('c_user', '')
        self._profile = random.choice(DEVICE_PROFILES)

    def _headers(self) -> dict:
        return {
            'User-Agent':       self._profile['ua'],
            'Accept':           '*/*',
            'Accept-Language':  self._profile.get('accept_language', self._profile.get('lang', 'ar,en;q=0.9')),
            'Content-Type':     'application/x-www-form-urlencoded',
            'Origin':           BM_BASE,
            'Referer':          f'{BM_BASE}/billing/',
            'X-Requested-With': 'XMLHttpRequest',
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=30,
            proxies=self.proxies,
            follow_redirects=True,
        )

    async def fetch_dtsg(self) -> Dict[str, Any]:
        """يستخرج DTSG من أي صفحة ميتا ممكنة."""
        try_urls = [
            f'{BM_BASE}/',
            f'{BM_BASE}/billing/',
            f'{BM_BASE}/settings/business-information/',
            f'{BM_BASE}/ads/manager/',
            'https://www.facebook.com/adsmanager/manage/campaigns',
            'https://www.facebook.com/',
        ]
        for url in try_urls:
            try:
                async with self._client() as c:
                    resp = await c.get(url, headers=self._headers(),
                                       cookies=self.cookies_dict)
                    text = resp.text
                    url_lower = str(resp.url).lower()
                    if 'login' in url_lower or 'checkpoint' in text.lower():
                        continue
                    tok = _extract_dtsg(text)
                    if tok:
                        self._dtsg = tok
                        return {'success': True}
            except Exception:
                continue
        return {'success': False, 'error': 'الكوكيز منتهية أو غير صالحة — تحقق منها'}

    # ─────────────────────────────────────────────────────────────────────
    #  الطلب الأول: جلب billing account id
    #  الـ Bookmarklet يرسل لـ URL مع ?_callFlowletID=0&_triggerFlowletID=2596
    #  و variables بدون encode (سلسلة JSON خام) — نفس المنطق هنا
    # ─────────────────────────────────────────────────────────────────────
    async def get_billing_account_id(self, bm_id: str, ad_id: str) -> Dict[str, Any]:
        url = f'{GRAPHQL}?_callFlowletID=0&_triggerFlowletID=2596'

        # variables بدون encode — نفس الـ Bookmarklet:
        # variables={"businessID":"${bm}"}
        variables_raw = json.dumps({'businessID': bm_id}, separators=(',', ':'))

        body = '&'.join([
            f'av={self._user_id}',
            f'__aaid={ad_id}',
            f'__bid={bm_id}',
            f'__user={self._user_id}',
            '__a=1',
            f'fb_dtsg={self._dtsg}',
            'fb_api_caller_class=RelayModern',
            'fb_api_req_friendly_name=BillingHubPaymentMethodsViewQuery',
            f'variables={variables_raw}',
            'doc_id=23945721255021756',
        ])

        try:
            async with self._client() as c:
                resp = await c.post(url, headers=self._headers(),
                                    cookies=self.cookies_dict, content=body)
                try:
                    data = resp.json()
                except Exception:
                    return {'success': False, 'error': f'رد غير JSON ({resp.status_code}): {resp.text[:200]}'}

            bm_ad_id = (data.get('data', {})
                            .get('business', {})
                            .get('billing_payment_account', {})
                            .get('id'))
            if not bm_ad_id:
                return {'success': False, 'error': 'لم يتم العثور على حساب الدفع في البيزنس'}
            return {'success': True, 'bm_ad_id': bm_ad_id}
        except Exception as e:
            return {'success': False, 'error': f'خطأ شبكة: {e}'}

    # ─────────────────────────────────────────────────────────────────────
    #  الطلب الثاني: جلب البطاقات
    #  الـ Bookmarklet يرسل لـ URL مع ?_callFlowletID=0&_triggerFlowletID=1
    #  و variables بدون encode — نفس المنطق هنا
    # ─────────────────────────────────────────────────────────────────────
    async def get_payment_methods(self, bm_id: str, ad_id: str,
                                   bm_ad_id: str) -> Dict[str, Any]:
        url = f'{GRAPHQL}?_callFlowletID=0&_triggerFlowletID=1'

        # variables بدون encode — نفس الـ Bookmarklet
        variables_raw = json.dumps({
            'paymentAccountID':           bm_ad_id,
            'billable_account_types':     ['FB_ADS', 'WHATSAPP'],
            'connected_asset_limit':      26,
            'connected_asset_detail_limit': 5,
        }, separators=(',', ':'))

        body = '&'.join([
            f'av={self._user_id}',
            f'__aaid={ad_id}',
            f'__bid={bm_id}',
            f'__user={self._user_id}',
            f'fb_dtsg={self._dtsg}',
            'fb_api_caller_class=RelayModern',
            'fb_api_req_friendly_name=BillingHubPaymentMethodsBusinessSectionQuery',
            f'variables={variables_raw}',
            'doc_id=24585166657733775',
        ])

        try:
            async with self._client() as c:
                resp = await c.post(url, headers=self._headers(),
                                    cookies=self.cookies_dict, content=body)
                try:
                    data = resp.json()
                except Exception:
                    return {'success': False, 'error': f'رد غير JSON ({resp.status_code}): {resp.text[:200]}'}

            try:
                methods = (data['data']['payment_account']['billing_payment_methods'])
                cards = [m['credential'] for m in methods]
                if not cards:
                    return {'success': False, 'error': 'لا توجد بطاقات في الحافظة'}
                return {'success': True, 'cards': cards}
            except Exception as e:
                return {'success': False, 'error': f'خطأ في تحليل البطاقات: {e}'}
        except Exception as e:
            return {'success': False, 'error': f'خطأ شبكة: {e}'}

    # ─────────────────────────────────────────────────────────────────────
    #  الطلب الثالث: make_default
    #  الـ Bookmarklet يرسل لـ /api/graphql/ العادي (بدون params)
    #  و fb_dtsg مُشفَّر بـ encodeURIComponent
    #  و variables مُشفَّرة بـ encodeURIComponent(JSON.stringify(vars))
    # ─────────────────────────────────────────────────────────────────────
    async def make_default(self, bm_id: str, ad_id: str,
                            credential_id: str) -> Dict[str, Any]:
        def _rnd() -> str:
            ts = int(time.time() * 1000)
            rnd = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=9))
            return f'upl_{ts}_{rnd}'

        variables = {
            'input': {
                'payment_legacy_account_id': ad_id,
                'shared_biz_credential_id':  credential_id,
                'upl_logging_data': {
                    'context':            'billingaddpm',
                    'credential_id':      credential_id,
                    'credential_type':    'CREDIT_CARD',
                    'entry_point':        'BILLING_HUB',
                    'external_flow_id':   _rnd(),
                    'target_name':        'BillingSaveSharedBizCardStateMutation',
                    'user_session_id':    _rnd(),
                    'wizard_config_name': 'SELECT_PAYMENT_METHOD',
                    'wizard_name':        'ADD_PM_PUX_EP',
                    'wizard_session_id':  f'upl_wizard_{_rnd()}',
                },
                'actor_id':           self._user_id,
                'client_mutation_id': str(int(time.time() * 1000)),
            },
            'includeCreateNewFromOldFragment': False,
        }

        # ← الفرق الجوهري: fb_dtsg و variables مُشفَّرَين بـ quote()
        #   تماماً كما يفعل الـ Bookmarklet بـ encodeURIComponent
        body = '&'.join([
            f'av={self._user_id}',
            f'__aaid={ad_id}',
            f'__bid={bm_id}',
            f'__user={self._user_id}',
            f'fb_dtsg={quote(self._dtsg, safe="")}',
            'fb_api_caller_class=RelayModern',
            'fb_api_req_friendly_name=BillingSaveSharedBizCardStateMutation',
            f'variables={quote(json.dumps(variables, separators=(",", ":")), safe="")}',
            'doc_id=25126279877041501',
        ])

        try:
            async with self._client() as c:
                resp = await c.post(GRAPHQL, headers=self._headers(),
                                    cookies=self.cookies_dict, content=body)
                try:
                    data = resp.json()
                except Exception:
                    return {'success': False, 'error': f'رد غير JSON ({resp.status_code}): {resp.text[:200]}'}

            if 'errors' in data and data['errors']:
                msg = data['errors'][0].get('message', 'خطأ غير معروف')
                return {'success': False, 'error': msg}
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': f'خطأ شبكة: {e}'}


# ═══════════════════════════════════════════════════════════════════════════
#  دوال الواجهة العامة
# ═══════════════════════════════════════════════════════════════════════════

async def get_bm_cards(cookies: str, bm_id: str, ad_id: str,
                       proxy: Optional[str] = None) -> Dict[str, Any]:
    svc = BMCardService(cookies, proxy)
    r = await svc.fetch_dtsg()
    if not r['success']:
        return r
    r = await svc.get_billing_account_id(bm_id, ad_id)
    if not r['success']:
        return r
    return await svc.get_payment_methods(bm_id, ad_id, r['bm_ad_id'])


async def warm_bm_cards(cookies: str, bm_id: str, ad_id: str,
                         cards: List[dict], card_ids: List[str],
                         interval_secs: int,
                         proxy: Optional[str] = None) -> Dict[str, Any]:
    svc = BMCardService(cookies, proxy)
    r = await svc.fetch_dtsg()
    if not r['success']:
        return r

    id_to_card = {c.get('credential_id', ''): c for c in cards}
    results = []
    for cid in card_ids:
        card  = id_to_card.get(cid, {})
        name  = card.get('card_association_name', 'Card')
        last4 = card.get('last_four_digits', '****')
        label = f'{name} •••• {last4}'

        res = await svc.make_default(bm_id, ad_id, cid)
        results.append({
            'label':   label,
            'success': res['success'],
            'error':   res.get('error', ''),
        })
        if interval_secs > 0 and cid != card_ids[-1]:
            await asyncio.sleep(interval_secs)

    success_count = sum(1 for r in results if r['success'])
    fail_count    = len(results) - success_count
    return {
        'success':       True,
        'results':       results,
        'success_count': success_count,
        'fail_count':    fail_count,
    }
