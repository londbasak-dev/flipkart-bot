import os
import json
import re
import logging
from bs4 import BeautifulSoup
from curl_cffi import requests

logger = logging.getLogger(__name__)

class FlipkartScraper:
    def __init__(self, pincode: str = "110091"):
        self.pincode = pincode

    def fetch_product_details(self, url: str, pincode: str = None) -> dict:
        """
        Fetches a Flipkart product URL with strict Pincode check.
        Notify Me / Out of stock / Not available at pincode -> is_in_stock = False.
        Buy Now / Add to Cart without out-of-stock indicators -> is_in_stock = True.
        """
        pin = pincode or self.pincode
        try:
            sep = '&' if '?' in url else '?'
            fetch_url = f"{url}{sep}pincode={pin}"
            cookies = {'pincode': str(pin)}

            proxy_url = os.getenv("PROXY_URL")
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

            response = requests.get(
                fetch_url,
                cookies=cookies,
                proxies=proxies,
                impersonate="chrome120",
                timeout=12
            )
            
            if response.status_code != 200:
                logger.error(f"HTTP error {response.status_code} fetching {url}")
                return {"success": False, "error": f"HTTP {response.status_code}"}

            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            # 1. Extract Product Title
            h1 = soup.find('h1') or soup.find('span', {'class': 'VU-ZEz'})
            if h1:
                title = h1.text.strip()
            else:
                og_title = soup.find('meta', property='og:title')
                title = og_title['content'].strip() if og_title else (soup.title.string.strip() if soup.title else "Unknown Product")
            
            title = re.sub(r'\s*Online at Best Price.*$', '', title, flags=re.I)
            title = re.sub(r'\s*Price in India.*$', '', title, flags=re.I)

            # 2. Extract Price
            price = None
            m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\}\s*);</script>', html)
            if not m:
                m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html)

            if m:
                try:
                    data = json.loads(m.group(1))
                    def find_keys(d, key_name):
                        res = []
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if k == key_name:
                                    res.append(v)
                                res.extend(find_keys(v, key_name))
                        elif isinstance(d, list):
                            for item in d:
                                res.extend(find_keys(item, key_name))
                        return res

                    prices = find_keys(data, 'finalPrice')
                    if prices:
                        price = int(prices[0])
                except Exception as e:
                    logger.warning(f"Error parsing price from INITIAL_STATE: {e}")

            if price is None:
                matches = re.findall(r'₹\s*([\d,]+)', html)
                if matches:
                    try:
                        clean_price = matches[0].replace(',', '')
                        price = int(clean_price)
                    except ValueError:
                        pass

            # 3. Strict Stock Status Determination for Pincode
            has_notify_me = bool(re.search(r'notify\s*me', html, re.I))
            has_pincode_unavailable = bool(re.search(r'not available at this pincode', html, re.I))
            has_out_of_stock = bool(re.search(r'out of stock|temporarily unavailable|currently unavailable|sold out', html, re.I))
            has_coming_soon = bool(re.search(r'coming\s*soon', html, re.I))
            
            # Action button checks
            has_buy_now = bool(re.search(r'>\s*buy\s*now\s*<', html, re.I))
            has_add_to_cart = bool(re.search(r'>\s*add\s*to\s*cart\s*<', html, re.I))

            if has_notify_me or has_pincode_unavailable:
                is_in_stock = False
                status = "NOTIFY_ME"
            elif has_out_of_stock:
                is_in_stock = False
                status = "OUT_OF_STOCK"
            elif has_coming_soon:
                is_in_stock = False
                status = "COMING_SOON"
            elif has_buy_now or has_add_to_cart:
                is_in_stock = True
                status = "IN_STOCK"
            else:
                is_in_stock = False
                status = "OUT_OF_STOCK"

            return {
                "success": True,
                "title": title,
                "price": price,
                "status": status,
                "is_in_stock": is_in_stock,
                "pincode": pin,
                "url": url
            }

        except Exception as e:
            logger.exception(f"Unexpected error scraping {url}: {e}")
            return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    scraper = FlipkartScraper(pincode="110091")
    test_url = "https://www.flipkart.com/apple-iphone-17-mist-blue-256-gb/p/itm1834df7ee2812?pid=MOBHFN6YWTXZD8SG"
    print("Testing scraper for Pincode 110091 on:", test_url)
    res = scraper.fetch_product_details(test_url)
    print("Result:", res)
