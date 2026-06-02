"""
默沙东诊疗手册爬虫 v2 - Middle 层数据准备
通过 sitemap.xml 获取所有专业版话题 URL，提取 LeftMenuNavigation 内容。
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import httpx

SITEMAP_URL = "https://www.msdmanuals.cn/sitemap.xml"
BASE_URL = "https://www.msdmanuals.cn"
OUTPUT_DIR = Path("data/middle")
DELAY = 3  # robots.txt: Crawl-delay: 5
MAX_WORKERS = 2
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 重点抓取的诊断相关分类
PRIORITY_CATEGORIES = {
    "cardiovascular-disorders",
    "pulmonary-disorders",
    "gastrointestinal-disorders",
    "hepatic-and-biliary-disorders",
    "musculoskeletal-and-connective-tissue-disorders",
    "endocrine-and-metabolic-disorders",
    "hematology-and-oncology",
    "neurologic-disorders",
    "psychiatric-disorders",
    "renal-and-urologic-disorders",
    "gynecology-and-obstetrics",
    "pediatrics",
    "infectious-diseases",
    "dermatologic-disorders",
    "eye-disorders",
    "ear-nose-and-throat-disorders",
    "genitourinary-disorders",
    "injuries-poisoning",
    "critical-care-medicine",
}


def fetch_url(url: str) -> str | None:
    try:
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url, headers=HEADERS)
            resp.raise_for_status()
            return resp.text
    except Exception:
        return None


def parse_sitemap(xml: str) -> list[str]:
    """从 sitemap XML 中提取所有 professional 话题 URL"""
    urls = re.findall(
        r"https://www\.msdmanuals\.cn/professional/[a-z][a-z-]+/[a-z][a-z-]+/[a-z][a-z-]+",
        xml,
    )
    return sorted(set(urls))


def extract_article(html: str) -> str | None:
    """从页面 __NEXT_DATA__ 中提取 LeftMenuNavigation 内容"""
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
    )
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        fields = data["props"]["pageProps"]["layoutData"]["sitecore"]["route"]["fields"]
    except (KeyError, json.JSONDecodeError):
        return None

    # 优先: LeftMenuNavigation (文章正文)
    nav_value = fields.get("LeftMenuNavigation", {}).get("value", "[]")
    try:
        sections = json.loads(nav_value)
    except json.JSONDecodeError:
        sections = []

    lines = []
    for sec in sections:
        title = sec.get("Title", "")
        html_content = sec.get("Summary", "")
        clean = re.sub(r"<[^>]+>", " ", html_content)
        clean = re.sub(r"&nbsp;", " ", clean)
        clean = re.sub(r"&amp;", "&", clean)
        clean = re.sub(r"&lt;", "<", clean)
        clean = re.sub(r"&gt;", ">", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if title:
            lines.append(f"## {title}")
        if clean:
            lines.append(clean)

    # 追加 Summary
    summary = fields.get("Summary", {}).get("value", "")
    if summary:
        clean_summary = re.sub(r"<[^>]+>", " ", summary)
        clean_summary = re.sub(r"\s+", " ", clean_summary).strip()
        if clean_summary:
            lines.append(f"\n[摘要] {clean_summary}")

    text = "\n\n".join(lines).strip()
    return text if len(text) >= 100 else None


def url_to_path(url: str) -> Path:
    """将 MSD URL 转为本地文件路径: /professional/a/b/c -> data/middle/a/b_c.txt"""
    path = url.replace("https://www.msdmanuals.cn/professional/", "")
    parts = path.split("/")
    if len(parts) >= 3:
        category = parts[0]
        subcategory = parts[1]
        topic = parts[2]
        filename = f"{subcategory}__{topic}.txt"
        return OUTPUT_DIR / category / filename
    return OUTPUT_DIR / f"{path.replace('/', '_')}.txt"


def scrape_topic(url: str) -> tuple[str, bool]:
    """抓取单篇话题，返回 (url, success)"""
    filepath = url_to_path(url)
    if filepath.exists() and filepath.stat().st_size > 200:
        return url, True  # 已存在

    html = fetch_url(url)
    if not html:
        return url, False

    text = extract_article(html)
    if not text:
        return url, False

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(text, encoding="utf-8")
    return url, True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[输出目录] {OUTPUT_DIR.resolve()}")

    # 1. 获取 sitemap
    print(f"\n[下载] sitemap: {SITEMAP_URL}")
    xml = fetch_url(SITEMAP_URL)
    if not xml:
        print("❌ 无法获取 sitemap")
        return

    all_urls = parse_sitemap(xml)
    print(f"[解析] 共 {len(all_urls)} 个专业版话题 URL")

    # 2. 按分类分组
    by_category: dict[str, list[str]] = {}
    for url in all_urls:
        path = url.replace("https://www.msdmanuals.cn/professional/", "")
        category = path.split("/")[0]
        by_category.setdefault(category, []).append(url)

    print(f"[分类] {len(by_category)} 个类别")

    # 3. 优先抓取重点分类
    priority_urls = []
    other_urls = []
    for cat, urls in sorted(by_category.items()):
        if cat in PRIORITY_CATEGORIES:
            priority_urls.extend(urls)
            print(f"  ✅ {cat}: {len(urls)} topics")
        else:
            other_urls.extend(urls)
            print(f"  ⬜ {cat}: {len(urls)} topics")

    all_to_scrape = priority_urls + other_urls
    print(f"\n[总计] 待抓取: {len(all_to_scrape)} 篇")

    # 4. 并发抓取
    success = 0
    fail = 0
    total = len(all_to_scrape)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_topic, url): url for url in all_to_scrape}
        for i, future in enumerate(as_completed(futures), 1):
            url, ok = future.result()
            if ok:
                success += 1
            else:
                fail += 1
            if i % 50 == 0:
                pct = i * 100 // total
                print(f"  [{i}/{total}] {pct}% OK={success} FAIL={fail}")
            time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"[完成] 成功: {success}, 失败: {fail}")
    print(f"[目录] {OUTPUT_DIR.resolve()}")
    print(f"后续:")
    print(f"  source ../../backend/.env")
    print(f"  export OPENAI_API_KEY OPENAI_API_BASE_URL NEO4J_URI NEO4J_USERNAME NEO4J_PASSWORD")
    print(f"  python three_layer_import.py --middle {OUTPUT_DIR} --clear")


if __name__ == "__main__":
    main()
