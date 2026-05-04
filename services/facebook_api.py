"""
Facebook Graph API Client
يتعامل مع Facebook Ads API لإنشاء الحملات الإعلانية
"""
import httpx
import asyncio
from typing import Optional, Dict, Any
from states import AdObjectives


FB_API_VERSION = 'v18.0'
FB_GRAPH_API = 'https://graph.facebook.com'

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]


def get_random_ua():
    import random
    return random.choice(USER_AGENTS)


def parse_cookies(cookies_str: str) -> dict:
    cookies = {}
    for part in cookies_str.split(';'):
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies


def get_proxies(proxy: Optional[str]) -> Optional[dict]:
    if not proxy:
        return None
    if '://' not in proxy:
        proxy = f'http://{proxy}'
    return {'http://': proxy, 'https://': proxy}


class FacebookAPIClient:
    """عميل Facebook Graph API - يعمل بالكوكيز"""

    def __init__(self, cookies: str, proxy: Optional[str] = None):
        self.cookies_str = cookies
        self.cookies_dict = parse_cookies(cookies)
        self.proxy = proxy
        self.proxies = get_proxies(proxy)
        self.base_url = f'{FB_GRAPH_API}/{FB_API_VERSION}'

    def _get_headers(self) -> dict:
        return {
            'User-Agent': get_random_ua(),
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.facebook.com/',
        }

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f'{self.base_url}/{endpoint}'
        headers = self._get_headers()

        async with httpx.AsyncClient(
            timeout=60,
            proxies=self.proxies,
            follow_redirects=True
        ) as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                cookies=self.cookies_dict,
                **kwargs
            )
            data = resp.json()

            if resp.status_code != 200:
                error_msg = data.get('error', {}).get('message', f'HTTP {resp.status_code}')
                return {'success': False, 'error': error_msg, 'raw': data}

            return {'success': True, 'data': data}

    async def create_campaign(self, ad_account_id: str, name: str, objective: str) -> Dict[str, Any]:
        """إنشاء حملة إعلانية"""
        fb_objective = AdObjectives.get_fb_objective(objective)
        result = await self._request(
            'POST',
            f'act_{ad_account_id}/campaigns',
            json={
                'name': name,
                'objective': fb_objective,
                'special_ad_categories': [],
                'status': 'PAUSED',
            }
        )
        if result['success']:
            result['campaign_id'] = result['data'].get('id')
        return result

    async def create_ad_set(
        self,
        ad_account_id: str,
        campaign_id: str,
        page_id: str,
        name: str,
        objective: str,
        daily_budget_usd: float,
        days: int,
        audience_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """إنشاء Ad Set"""
        import time
        optimization_goal = AdObjectives.get_optimization_goal(objective)

        targeting = {
            'geo_locations': {'countries': ['EG']},
            'age_min': 18,
            'age_max': 65,
        }
        if audience_id:
            targeting['custom_audiences'] = [{'id': audience_id}]

        promoted_object = {'page_id': page_id}
        if objective in [AdObjectives.MESSAGES_WHATSAPP]:
            promoted_object['whatsapp_phone_number'] = ''

        payload = {
            'name': name,
            'campaign_id': campaign_id,
            'optimization_goal': optimization_goal,
            'billing_event': 'IMPRESSIONS',
            'daily_budget': int(daily_budget_usd * 100),
            'start_time': int(time.time()),
            'end_time': int(time.time()) + (days * 86400),
            'targeting': targeting,
            'promoted_object': promoted_object,
            'status': 'PAUSED',
        }

        result = await self._request(
            'POST',
            f'act_{ad_account_id}/adsets',
            json=payload
        )
        if result['success']:
            result['ad_set_id'] = result['data'].get('id')
        return result

    async def upload_photo(self, page_id: str, image_path: str, caption: str) -> Dict[str, Any]:
        """رفع صورة للـ Dark Post"""
        with open(image_path, 'rb') as f:
            image_data = f.read()

        async with httpx.AsyncClient(
            timeout=120,
            proxies=self.proxies,
            follow_redirects=True
        ) as client:
            resp = await client.post(
                f'{self.base_url}/{page_id}/photos',
                headers=self._get_headers(),
                cookies=self.cookies_dict,
                data={
                    'caption': caption,
                    'published': 'false',
                },
                files={'source': ('image.jpg', image_data, 'image/jpeg')}
            )
            data = resp.json()
            if resp.status_code == 200 and 'id' in data:
                return {'success': True, 'photo_id': data['id'], 'data': data}
            error_msg = data.get('error', {}).get('message', f'HTTP {resp.status_code}')
            return {'success': False, 'error': error_msg}

    async def create_ad_creative_post(
        self,
        ad_account_id: str,
        page_id: str,
        post_id: str,
        objective: str
    ) -> Dict[str, Any]:
        """إنشاء Creative من بوست موجود"""
        cta_type = AdObjectives.get_cta_type(objective)

        result = await self._request(
            'POST',
            f'act_{ad_account_id}/adcreatives',
            json={
                'name': 'Creative - Post Boost',
                'object_story_id': f'{page_id}_{post_id}',
                'call_to_action': {'type': cta_type},
            }
        )
        if result['success']:
            result['creative_id'] = result['data'].get('id')
        return result

    async def create_ad_creative_dark_post(
        self,
        ad_account_id: str,
        page_id: str,
        photo_id: str,
        caption: str,
        objective: str
    ) -> Dict[str, Any]:
        """إنشاء Creative للـ Dark Post"""
        cta_type = AdObjectives.get_cta_type(objective)

        result = await self._request(
            'POST',
            f'act_{ad_account_id}/adcreatives',
            json={
                'name': 'Creative - Dark Post',
                'object_story_spec': {
                    'page_id': page_id,
                    'photo_data': {
                        'photo_id': photo_id,
                        'message': caption,
                        'call_to_action': {'type': cta_type},
                    }
                }
            }
        )
        if result['success']:
            result['creative_id'] = result['data'].get('id')
        return result

    async def create_ad_creative_partner(
        self,
        ad_account_id: str,
        ad_set_id: str,
        ad_code: str,
        objective: str
    ) -> Dict[str, Any]:
        """إنشاء Creative للـ Partner Ship"""
        result = await self._request(
            'POST',
            f'act_{ad_account_id}/adcreatives',
            json={
                'name': 'Creative - Partner Ship',
                'object_type': 'SHARE',
                'call_to_action': {'type': AdObjectives.get_cta_type(objective)},
            }
        )
        if result['success']:
            result['creative_id'] = result['data'].get('id')
        return result

    async def create_ad(
        self,
        ad_account_id: str,
        ad_set_id: str,
        creative_id: str,
        name: str
    ) -> Dict[str, Any]:
        """إنشاء الإعلان النهائي"""
        result = await self._request(
            'POST',
            f'act_{ad_account_id}/ads',
            json={
                'name': name,
                'adset_id': ad_set_id,
                'creative': {'creative_id': creative_id},
                'status': 'ACTIVE',
            }
        )
        if result['success']:
            result['ad_id'] = result['data'].get('id')
        return result

    async def activate_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """تفعيل الحملة"""
        return await self._request('POST', campaign_id, json={'status': 'ACTIVE'})

    async def activate_ad_set(self, ad_set_id: str) -> Dict[str, Any]:
        """تفعيل Ad Set"""
        return await self._request('POST', ad_set_id, json={'status': 'ACTIVE'})

    async def pause_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """إيقاف الحملة عبر Marketing API"""
        return await self._request('POST', campaign_id, json={'status': 'PAUSED'})

    async def pause_ad_set(self, ad_set_id: str) -> Dict[str, Any]:
        """إيقاف Ad Set عبر Marketing API"""
        return await self._request('POST', ad_set_id, json={'status': 'PAUSED'})

    async def pause_ad(self, ad_id: str) -> Dict[str, Any]:
        """إيقاف الإعلان عبر Marketing API"""
        return await self._request('POST', ad_id, json={'status': 'PAUSED'})

    async def get_page_posts(self, page_id: str, limit: int = 10) -> Dict[str, Any]:
        """جلب أحدث بوستات الصفحة"""
        result = await self._request(
            'GET',
            f'{page_id}/posts',
            params={
                'fields': 'id,message,story,created_time',
                'limit': limit,
            }
        )
        if result['success']:
            posts = result['data'].get('data', [])
            result['posts'] = posts
        return result


async def fetch_page_posts(cookies: str, page_id: str, proxy: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """جلب أحدث بوستات الصفحة للاختيار منها"""
    client = FacebookAPIClient(cookies, proxy)
    return await client.get_page_posts(page_id, limit)


async def _run_ad_core(client: 'FacebookAPIClient', data: dict, campaign_name: str,
                       page_id: str, objective: str, photo_id: Optional[str] = None) -> Dict[str, Any]:
    """النواة المشتركة لبناء الإعلان — Campaign + AdSet + Creative + Ad + تفعيل"""
    step = "إنشاء الحملة"
    campaign = await client.create_campaign(data['ad_account_id'], campaign_name, objective)
    if not campaign['success']:
        return {'success': False, 'step': step, 'error': campaign['error']}
    campaign_id = campaign['campaign_id']

    step = "إنشاء Ad Set"
    ad_set = await client.create_ad_set(
        data['ad_account_id'], campaign_id, page_id,
        f"AdSet - {campaign_name}", objective,
        data.get('daily_budget', 10.0),
        data.get('days', 7),
        data.get('audience_id')
    )
    if not ad_set['success']:
        return {'success': False, 'step': step, 'error': ad_set['error']}
    ad_set_id = ad_set['ad_set_id']

    step = "إنشاء Creative"
    if photo_id:
        creative = await client.create_ad_creative_dark_post(
            data['ad_account_id'], page_id, photo_id, data.get('caption', ''), objective)
    elif data.get('ad_code'):
        creative = await client.create_ad_creative_partner(
            data['ad_account_id'], data.get('ad_set_id') or ad_set_id, data['ad_code'], objective)
    else:
        creative = await client.create_ad_creative_post(
            data['ad_account_id'], page_id, data.get('post_id', ''), objective)
    if not creative['success']:
        return {'success': False, 'step': step, 'error': creative['error']}
    creative_id = creative['creative_id']

    step = "إنشاء الإعلان"
    ad = await client.create_ad(data['ad_account_id'], ad_set_id, creative_id, f"Ad - {campaign_name}")
    if not ad['success']:
        return {'success': False, 'step': step, 'error': ad['error']}
    ad_id = ad['ad_id']

    # تفعيل
    await client.activate_campaign(campaign_id)
    await client.activate_ad_set(ad_set_id)

    return {
        'success': True,
        'campaign_id': campaign_id,
        'ad_set_id': ad_set_id,
        'creative_id': creative_id,
        'ad_id': ad_id,
    }


async def _pause_all(client: 'FacebookAPIClient', campaign_id: str, ad_set_id: str, ad_id: str):
    """إيقاف الحملة والـ Ad Set والإعلان عبر Marketing API"""
    await asyncio.sleep(1)
    await client.pause_ad(ad_id)
    await client.pause_ad_set(ad_set_id)
    await client.pause_campaign(campaign_id)


async def run_standard_ad(data: dict) -> Dict[str, Any]:
    """تشغيل إعلان رابط بوست — نشر نشط"""
    client = FacebookAPIClient(data['cookies'], data.get('proxy'))
    post_id = data['post_id']
    campaign_name = f"Boost - {post_id[:8]}"
    return await _run_ad_core(client, data, campaign_name, data['page_id'], data['objective'])


async def run_standard_ad_then_pause(data: dict) -> Dict[str, Any]:
    """تشغيل إعلان رابط بوست — نشر ثم إيقاف فوري عبر Marketing API"""
    client = FacebookAPIClient(data['cookies'], data.get('proxy'))
    post_id = data['post_id']
    campaign_name = f"Boost - {post_id[:8]}"
    result = await _run_ad_core(client, data, campaign_name, data['page_id'], data['objective'])
    if result['success']:
        await _pause_all(client, result['campaign_id'], result['ad_set_id'], result['ad_id'])
        result['paused'] = True
    return result


async def run_dark_post_ad(data: dict) -> Dict[str, Any]:
    """تشغيل Dark Post — نشر نشط"""
    client = FacebookAPIClient(data['cookies'], data.get('proxy'))
    page_id = data['page_id']
    campaign_name = f"DarkPost - {page_id[:8]}"
    photo_id = None
    if data.get('image_path'):
        step = "رفع الصورة"
        photo = await client.upload_photo(page_id, data['image_path'], data.get('caption', ''))
        if not photo['success']:
            return {'success': False, 'step': step, 'error': photo['error']}
        photo_id = photo['photo_id']
    result = await _run_ad_core(client, data, campaign_name, page_id, data['objective'], photo_id=photo_id)
    if result['success']:
        result['photo_id'] = photo_id
    return result


async def run_dark_post_ad_then_pause(data: dict) -> Dict[str, Any]:
    """تشغيل Dark Post — نشر ثم إيقاف فوري عبر Marketing API"""
    client = FacebookAPIClient(data['cookies'], data.get('proxy'))
    page_id = data['page_id']
    campaign_name = f"DarkPost - {page_id[:8]}"
    photo_id = None
    if data.get('image_path'):
        step = "رفع الصورة"
        photo = await client.upload_photo(page_id, data['image_path'], data.get('caption', ''))
        if not photo['success']:
            return {'success': False, 'step': step, 'error': photo['error']}
        photo_id = photo['photo_id']
    result = await _run_ad_core(client, data, campaign_name, page_id, data['objective'], photo_id=photo_id)
    if result['success']:
        result['photo_id'] = photo_id
        await _pause_all(client, result['campaign_id'], result['ad_set_id'], result['ad_id'])
        result['paused'] = True
    return result


async def run_partner_ship_ad(data: dict) -> Dict[str, Any]:
    """تشغيل Partner Ship Ad — نشر نشط"""
    client = FacebookAPIClient(data['cookies'], data.get('proxy'))
    campaign_name = f"PartnerShip - {data['ad_account_id'][:8]}"
    return await _run_ad_core(
        client, data, campaign_name,
        data.get('page_id', ''), data['objective']
    )


async def run_partner_ship_ad_then_pause(data: dict) -> Dict[str, Any]:
    """تشغيل Partner Ship Ad — نشر ثم إيقاف فوري عبر Marketing API"""
    client = FacebookAPIClient(data['cookies'], data.get('proxy'))
    campaign_name = f"PartnerShip - {data['ad_account_id'][:8]}"
    result = await _run_ad_core(
        client, data, campaign_name,
        data.get('page_id', ''), data['objective']
    )
    if result['success']:
        await _pause_all(client, result['campaign_id'], result['ad_set_id'], result['ad_id'])
        result['paused'] = True
    return result

    return {
        'success': True,
        'campaign_id': campaign_id,
        'ad_set_id': ad_set_id,
        'creative_id': creative_id,
        'ad_id': ad['ad_id'],
    }
