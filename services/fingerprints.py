# fingerprints.py - shared device profiles
from __future__ import annotations
import random
from typing import Dict, Any

DEVICE_PROFILES = [
    {"ua":"Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36","platform":"Android","accept_language":"ar-EG,ar;q=0.9","sec_ch_ua_mobile":"?1"},
    {"ua":"Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/123.0.0.0 Mobile Safari/537.36","platform":"Android","accept_language":"en-US,en;q=0.9","sec_ch_ua_mobile":"?1"},
    {"ua":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile/15E148 Safari/604.1","platform":"iOS","accept_language":"ar-SA,ar;q=0.9","sec_ch_ua_mobile":"?1"},
    {"ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36","platform":"Windows","accept_language":"en-US,en;q=0.9","sec_ch_ua_mobile":"?0"},
    {"ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15","platform":"macOS","accept_language":"en-US,en;q=0.9","sec_ch_ua_mobile":"?0"},
]

def random_profile() -> Dict[str, Any]:
    return random.choice(DEVICE_PROFILES)
