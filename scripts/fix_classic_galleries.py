#!/usr/bin/env python3
"""
Fix classic editor gallery posts where images weren't downloaded correctly.
The issue: classic gallery <a> tags link to attachment pages, not image files.
Fix: use <img src> instead and strip size suffixes to get full-res URLs.
"""

import os
import re
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import html2text
import html as html_mod
import yaml

WP_API = "https://theboardingcall.com/wp-json/wp/v2"
OUTPUT_DIR = Path(__file__).resolve().parent.parent
POSTS_DIR = OUTPUT_DIR / "_posts"
IMAGES_DIR = OUTPUT_DIR / "assets" / "images"

SIZE_SUFFIX_RE = re.compile(r'-\d+x\d+(?=\.\w+$)')

session = requests.Session()
session.headers.update({
    'User-Agent': 'TBC-Migration/1.0 (Jekyll migration script)'
})

# Posts to fix
SLUGS_TO_FIX = [
    "48-hours-seoul-hong-kong",
    "quick-overview-united-airlines-premium-cabins",
    "48-hours-in-fukuoka",
]


def download_image(url):
    """Download image, stripping size suffix for full-res."""
    if not url:
        return None

    full_url = SIZE_SUFFIX_RE.sub('', url)
    parsed = urlparse(full_url)
    wp_path = parsed.path

    if '/wp-content/uploads/' in wp_path:
        rel_path = wp_path.split('/wp-content/uploads/')[-1]
    else:
        rel_path = os.path.basename(wp_path)

    if not rel_path or rel_path == '/':
        return None

    local_path = IMAGES_DIR / rel_path
    site_path = f"/assets/images/{rel_path}"

    if local_path.exists():
        return site_path

    local_path.parent.mkdir(parents=True, exist_ok=True)

    for try_url in [full_url, url]:
        try:
            resp = session.get(try_url, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 100:
                local_path.write_bytes(resp.content)
                size_kb = len(resp.content) / 1024
                print(f"    Downloaded: {rel_path} ({size_kb:.0f} KB)")
                return site_path
        except requests.RequestException:
            continue

    print(f"    WARNING: Failed to download {url}")
    return None


def is_image_url(url):
    """Check if a URL points to an image file."""
    if not url:
        return False
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp'])


def is_wp_attachment_page(url):
    """Check if URL is a WordPress attachment page (not an image file)."""
    if not url:
        return False
    return not is_image_url(url) and 'theboardingcall.com' in url


def process_html(html_content):
    """Process HTML with fixed classic gallery handling."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Process classic galleries - use img src, NOT parent <a> href
    for gallery in soup.find_all('div', id=re.compile(r'^gallery-')):
        images = []
        for item in gallery.find_all('figure', class_='gallery-item'):
            img = item.find('img')
            if not img:
                continue

            # Use the img src directly (NOT the parent <a> which is an attachment page)
            src = img.get('src', '')
            alt = img.get('alt', '')
            caption_el = item.find('figcaption')
            caption = caption_el.get_text(strip=True) if caption_el else ''

            if src and '/wp-content/uploads/' in src:
                local_path = download_image(src)
                if local_path:
                    images.append((local_path, alt, caption))

        if images:
            md_lines = []
            for path, alt, caption in images:
                md_lines.append(f"![{alt}]({path})")
                if caption:
                    md_lines.append(f"*{caption}*")
                md_lines.append("")
            md = "\n".join(md_lines)
            gallery.replace_with(BeautifulSoup(f"<p>{md}</p>", 'html.parser'))

    # 2. Process wp-caption figures (individual images with captions)
    for figure in soup.find_all('figure', class_=re.compile(r'wp-caption')):
        img = figure.find('img')
        if not img:
            continue

        # Prefer <a href> only if it points to an actual image file
        parent_link = figure.find('a')
        if parent_link and is_image_url(parent_link.get('href', '')):
            src = parent_link['href']
        else:
            src = img.get('src', '')

        alt = img.get('alt', '')
        caption_el = figure.find('figcaption')
        caption = caption_el.get_text(strip=True) if caption_el else ''

        if src:
            local_path = download_image(src)
            if local_path:
                md = f"![{alt}]({local_path})"
                if caption:
                    md += f"\n*{caption}*"
                figure.replace_with(BeautifulSoup(f"<p>{md}</p>", 'html.parser'))

    # 3. Process standalone images (not in figures)
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src:
            continue

        # Check parent link
        parent_link = img.find_parent('a')
        if parent_link and is_image_url(parent_link.get('href', '')):
            src = parent_link['href']

        alt = img.get('alt', '')
        local_path = download_image(src)
        if local_path:
            md = f"![{alt}]({local_path})"
            target = parent_link if parent_link and parent_link.find('img') == img else img
            target.replace_with(BeautifulSoup(f"<p>{md}</p>", 'html.parser'))

    return str(soup)


def html_to_markdown(html_content):
    """Convert HTML to markdown."""
    h = html2text.HTML2Text()
    h.body_width = 0
    h.protect_links = True
    h.wrap_links = False
    h.unicode_snob = True
    h.skip_internal_links = False
    h.inline_links = True
    h.ignore_images = False
    h.ignore_emphasis = False

    md = h.handle(html_content)
    md = re.sub(r'\n{4,}', '\n\n\n', md)
    return md.strip()


def fetch_categories():
    """Fetch category map."""
    resp = session.get(f"{WP_API}/categories", params={'per_page': 100})
    cats = resp.json()
    return {c['id']: c['name'] for c in cats}


def fetch_media_map():
    """Fetch media map."""
    media_map = {}
    page = 1
    while True:
        resp = session.get(f"{WP_API}/media", params={'per_page': 100, 'page': page})
        items = resp.json()
        if not items:
            break
        for item in items:
            media_map[item['id']] = {
                'source_url': item.get('source_url', ''),
            }
        total_pages = int(resp.headers.get('X-WP-TotalPages', 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)
    return media_map


def main():
    print("Fixing classic gallery posts...")

    category_map = fetch_categories()
    media_map = fetch_media_map()

    for slug in SLUGS_TO_FIX:
        print(f"\n=== Fixing: {slug} ===")

        resp = session.get(f"{WP_API}/posts", params={'slug': slug, '_embed': '1'})
        posts = resp.json()
        if not posts:
            print(f"  Post not found!")
            continue

        post = posts[0]
        title = html_mod.unescape(post['title']['rendered'])
        date_str = post['date'][:10]
        content_html = post['content']['rendered']

        # Build front matter
        fm = {
            'title': title,
            'permalink': f"/{slug}/",
            'layout': 'single',
            'date': post['date'],
        }

        cat_ids = post.get('categories', [])
        cats = [category_map.get(cid, '') for cid in cat_ids if category_map.get(cid)]
        cats = [c for c in cats if c != 'Uncategorized']
        if cats:
            fm['categories'] = cats

        featured_id = post.get('featured_media', 0)
        if featured_id and featured_id in media_map:
            featured_url = media_map[featured_id]['source_url']
            local_path = download_image(featured_url)
            if local_path:
                fm['header'] = {'image': local_path}

        # Process content
        processed_html = process_html(content_html)
        markdown = html_to_markdown(processed_html)

        # Save
        front_matter_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
        file_content = f"---\n{front_matter_str}---\n\n{markdown}\n"

        filename = f"{date_str}-{slug}.md"
        filepath = POSTS_DIR / filename
        filepath.write_text(file_content, encoding='utf-8')
        print(f"  Saved: {filepath.name}")

    print("\nDone fixing classic gallery posts!")


if __name__ == '__main__':
    main()
