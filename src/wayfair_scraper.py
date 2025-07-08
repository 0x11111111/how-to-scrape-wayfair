#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from pathlib import Path
import csv
import json
import re
import sys

import requests
from bs4 import BeautifulSoup


def parse_card(html: str) -> dict:
    """Parse one Wayfair ListingCard <div> and return a dict."""
    soup = BeautifulSoup(html, "html.parser")

    name = soup.select_one('img[alt]')['alt'].strip()

    cur_tag = soup.select_one(
        '[data-test-id="StandardPricingPrice-PRIMARY"] [data-test-id="PriceDisplay"]'
    )
    cur_price = cur_tag.text.strip() if cur_tag else ""

    old_tag = soup.select_one(
        '[data-test-id="StandardPricingPrice-PREVIOUS"] [data-test-id="PriceDisplay"]'
    )
    old_price = old_tag.text.strip() if old_tag else ""

    # rating
    rating = ""
    bar = soup.select_one('._1a7ukst7')
    if bar and "width:" in bar.get("style", ""):
        pct = int(re.search(r"width:\s*(\d+)%", bar["style"]).group(1))
        rating = round(pct * 5 / 100, 1)

    # review count
    rev_tag = soup.select_one('._1a7uksta')
    reviews = int(rev_tag.text.strip("()")) if rev_tag else ""

    # links
    a_tag = soup.find("a", href=True)
    product_url = a_tag["href"] if a_tag else ""

    img_tag = soup.find("img", src=True)
    image_url = img_tag["src"] if img_tag else ""

    return {
        "name": name,
        "current_price": cur_price,
        "original_price": old_price,
        "rating": rating,
        "review_count": reviews,
        "product_url": product_url,
        "image_url": image_url,
    }


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"[ERROR] info.json not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_page(product_url: str, username: str, password: str) -> str:
    """Use Oxylabs Realtime API to render the page and return HTML."""
    payload = {
        "source": "universal_ecommerce",
        "url": product_url,
        "user_agent_type": "desktop_safari",
        "geo_location": "United States",
        "render": "html",
        "browser_instructions": [
            {
                "type": "wait_for_element",
                "selector": {"type": "css", "value": "div.SFPrice span.oakhm64z_6112"},
                "timeout_s": 10,
            }
        ],
    }

    resp = requests.post(
        "https://realtime.oxylabs.io/v1/queries",
        auth=(username, password),
        json=payload,
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["results"][0]["content"]


def main() -> None:
    """Entry point."""
    # 0. 读取配置
    cfg = load_config(Path(__file__).with_name("info.json"))
    product_url, username, password = cfg["product_url"], cfg["username"], cfg["password"]

    # 1. 获取渲染后的 HTML
    html_content = fetch_page(product_url, username, password)

    # 2. 解析 ListingCard 列表
    soup = BeautifulSoup(html_content, "html.parser")
    cards = soup.find_all("div", attrs={"data-test-id": "ListingCard"})

    # 3. 创建时间戳文件夹
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = Path(f"ListingCards_{ts}")
    folder.mkdir(exist_ok=True)

    # 保存整页 HTML
    (folder / f"product_page_{ts}.html").write_text(html_content, encoding="utf-8")

    print(f"[INFO] Found {len(cards)} ListingCards, saving to {folder}")

    # 4. 提取 & 保存
    results = []
    for idx, card in enumerate(cards, 1):
        html_snippet = str(card)
        # 保存原始 <div>
        (folder / f"card_{idx}.txt").write_text(html_snippet, encoding="utf-8")
        # 解析字段
        results.append(parse_card(html_snippet))

    # 5. 输出 CSV
    csv_path = folder / "cards_data.csv"
    fieldnames = [
        "name",
        "current_price",
        "original_price",
        "rating",
        "review_count",
        "product_url",
        "image_url",
    ]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"[DONE] Data written to {csv_path}")


if __name__ == "__main__":
    main()
