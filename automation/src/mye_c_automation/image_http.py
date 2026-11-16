"""Shared image request profile, matching the existing Site download client."""

IMAGE_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36'


def image_headers():
    return {
        'User-Agent': IMAGE_USER_AGENT,
        'Accept': 'image/jpeg,image/png,image/webp,image/*;q=0.8',
        'Referer': 'https://www.aliexpress.com/',
    }
