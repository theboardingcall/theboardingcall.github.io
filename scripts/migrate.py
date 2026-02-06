#!/usr/bin/env python3
"""
WordPress to Jekyll migration script for theboardingcall.com.

Fetches all posts, pages, and media from the WordPress REST API,
converts HTML to Markdown with proper front matter, downloads images,
and saves to Jekyll-compatible directory structure.
"""

import os
import re
import sys
import time
import json
import html
import hashlib
import requests
from pathlib import Path
from urllib.parse import urlparse, urljoin
from datetime import datetime

from bs4 import BeautifulSoup, NavigableString
import html2text
import yaml

# Configuration
WP_BASE = "https://theboardingcall.com"
WP_API = f"{WP_BASE}/wp-json/wp/v2"
OUTPUT_DIR = Path(__file__).resolve().parent.parent
POSTS_DIR = OUTPUT_DIR / "_posts"
PAGES_DIR = OUTPUT_DIR / "_pages"
IMAGES_DIR = OUTPUT_DIR / "assets" / "images"

# WordPress size suffixes to strip for full-resolution URLs
SIZE_SUFFIX_RE = re.compile(r'-\d+x\d+(?=\.\w+$)')

# YouTube URL patterns
YOUTUBE_RE = re.compile(
    r'(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/)'
    r'([a-zA-Z0-9_-]{11})'
)

session = requests.Session()
session.headers.update({
    'User-Agent': 'TBC-Migration/1.0 (Jekyll migration script)'
})


def fetch_all_paginated(endpoint, params=None):
    """Fetch all items from a paginated WP REST API endpoint."""
    if params is None:
        params = {}
    params.setdefault('per_page', 100)
    params.setdefault('page', 1)

    all_items = []
    while True:
        print(f"  Fetching {endpoint} page {params['page']}...")
        resp = session.get(f"{WP_API}/{endpoint}", params=params)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        all_items.extend(items)
        total_pages = int(resp.headers.get('X-WP-TotalPages', 1))
        if params['page'] >= total_pages:
            break
        params['page'] += 1
        time.sleep(0.5)  # Be polite

    return all_items


def build_media_map():
    """Build a mapping of media ID -> source URL and metadata."""
    print("Fetching media library...")
    media_items = fetch_all_paginated('media')
    media_map = {}
    for item in media_items:
        media_map[item['id']] = {
            'source_url': item.get('source_url', ''),
            'alt_text': item.get('alt_text', ''),
            'caption': BeautifulSoup(
                item.get('caption', {}).get('rendered', ''), 'html.parser'
            ).get_text(strip=True),
            'title': item.get('title', {}).get('rendered', ''),
        }
    print(f"  Found {len(media_map)} media items")
    return media_map


def build_category_map():
    """Build a mapping of category ID -> category name."""
    print("Fetching categories...")
    categories = fetch_all_paginated('categories')
    cat_map = {}
    for cat in categories:
        cat_map[cat['id']] = cat['name']
    print(f"  Found {len(cat_map)} categories: {list(cat_map.values())}")
    return cat_map


def download_image(url, force_dir=None):
    """
    Download an image and return its local path relative to site root.
    Strips WordPress size suffixes to get full-resolution version.
    """
    if not url:
        return None

    # Try to get full-resolution URL by stripping size suffix
    full_url = SIZE_SUFFIX_RE.sub('', url)

    # Determine local path preserving WP upload structure
    parsed = urlparse(full_url)
    wp_path = parsed.path

    if '/wp-content/uploads/' in wp_path:
        # Extract the date-based path: YYYY/MM/filename.ext
        rel_path = wp_path.split('/wp-content/uploads/')[-1]
    else:
        # Non-WP image, use filename
        rel_path = os.path.basename(wp_path)

    local_path = IMAGES_DIR / rel_path
    site_path = f"/assets/images/{rel_path}"

    if local_path.exists():
        return site_path

    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Try full-resolution first, fall back to original URL
    for try_url in [full_url, url]:
        try:
            resp = session.get(try_url, timeout=30)
            if resp.status_code == 200:
                local_path.write_bytes(resp.content)
                size_kb = len(resp.content) / 1024
                print(f"    Downloaded: {rel_path} ({size_kb:.0f} KB)")
                return site_path
        except requests.RequestException:
            continue

    print(f"    WARNING: Failed to download {url}")
    return None


def extract_youtube_id(html_str):
    """Extract YouTube video ID from an HTML string."""
    match = YOUTUBE_RE.search(html_str)
    return match.group(1) if match else None


def process_gutenberg_gallery(gallery_tag):
    """Convert a WordPress Gutenberg gallery block to markdown images."""
    images = []
    for figure in gallery_tag.find_all('figure', class_='wp-block-image'):
        img = figure.find('img')
        if not img:
            continue

        # Prefer the parent link href (full-res) over img src
        parent_link = figure.find('a')
        src = parent_link['href'] if parent_link and parent_link.get('href') else img.get('src', '')
        alt = img.get('alt', '')
        caption_el = figure.find('figcaption')
        caption = caption_el.get_text(strip=True) if caption_el else ''

        local_path = download_image(src)
        if local_path:
            images.append((local_path, alt, caption))

    return images


def process_classic_gallery(gallery_div):
    """Convert a WordPress classic editor gallery to markdown images."""
    images = []
    for item in gallery_div.find_all(['dl', 'figure', 'div'], recursive=True):
        img = item.find('img')
        if not img:
            continue

        parent_link = item.find('a')
        src = parent_link['href'] if parent_link and parent_link.get('href') else img.get('src', '')
        alt = img.get('alt', '')
        caption_el = item.find(['dd', 'figcaption', '.gallery-caption'])
        caption = caption_el.get_text(strip=True) if caption_el else ''

        local_path = download_image(src)
        if local_path:
            images.append((local_path, alt, caption))

    return images


def images_to_markdown(images):
    """Convert a list of (path, alt, caption) tuples to markdown."""
    lines = []
    for path, alt, caption in images:
        lines.append(f"![{alt}]({path})")
        if caption:
            lines.append(f"*{caption}*")
        lines.append("")
    return "\n".join(lines)


def preprocess_html(html_content):
    """
    Pre-process WordPress HTML before html2text conversion.
    Handles galleries, YouTube embeds, individual images, and captions.
    Returns processed HTML string.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Process Gutenberg gallery blocks
    for gallery in soup.find_all('figure', class_='wp-block-gallery'):
        images = process_gutenberg_gallery(gallery)
        md = images_to_markdown(images)
        gallery.replace_with(NavigableString(f"\n\n{md}\n\n"))

    # 2. Process classic editor galleries
    for gallery in soup.find_all('div', class_=re.compile(r'gallery')):
        images = process_classic_gallery(gallery)
        if images:
            md = images_to_markdown(images)
            gallery.replace_with(NavigableString(f"\n\n{md}\n\n"))

    # 3. Process YouTube embeds (Gutenberg wp-block-embed)
    for embed in soup.find_all('figure', class_=re.compile(r'wp-block-embed')):
        embed_html = str(embed)
        yt_id = extract_youtube_id(embed_html)
        if yt_id:
            jekyll_include = f'{{% include youtube.html id="{yt_id}" %}}'
            embed.replace_with(NavigableString(f"\n\n{jekyll_include}\n\n"))

    # 4. Also catch any raw YouTube iframes not in embed blocks
    for iframe in soup.find_all('iframe'):
        src = iframe.get('src', '')
        yt_id = extract_youtube_id(src)
        if yt_id:
            jekyll_include = f'{{% include youtube.html id="{yt_id}" %}}'
            # Replace the parent figure if it exists, otherwise the iframe itself
            parent = iframe.find_parent('figure')
            target = parent if parent else iframe
            target.replace_with(NavigableString(f"\n\n{jekyll_include}\n\n"))

    # 5. Process individual images (wp-block-image and wp-caption)
    for figure in soup.find_all('figure', class_=re.compile(r'wp-block-image|wp-caption')):
        img = figure.find('img')
        if not img:
            continue

        parent_link = figure.find('a')
        src = parent_link['href'] if parent_link and parent_link.get('href') else img.get('src', '')
        alt = img.get('alt', '')
        caption_el = figure.find('figcaption')
        caption = caption_el.get_text(strip=True) if caption_el else ''

        local_path = download_image(src)
        if local_path:
            md = f"![{alt}]({local_path})"
            if caption:
                md += f"\n*{caption}*"
            figure.replace_with(NavigableString(f"\n\n{md}\n\n"))

    # 6. Process standalone images (not in figures) — classic editor
    for div in soup.find_all('div', class_=re.compile(r'wp-caption|aligncenter|alignnone|alignleft|alignright')):
        img = div.find('img')
        if not img:
            continue

        parent_link = div.find('a')
        src = parent_link['href'] if parent_link and parent_link.get('href') else img.get('src', '')
        alt = img.get('alt', '')
        caption_el = div.find('p', class_='wp-caption-text')
        caption = caption_el.get_text(strip=True) if caption_el else ''

        local_path = download_image(src)
        if local_path:
            md = f"![{alt}]({local_path})"
            if caption:
                md += f"\n*{caption}*"
            div.replace_with(NavigableString(f"\n\n{md}\n\n"))

    # 7. Process any remaining bare <img> tags
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if not src:
            continue

        # Check if parent is <a> with full-res link
        parent_link = img.find_parent('a')
        if parent_link and parent_link.get('href', '').startswith('http'):
            link_href = parent_link['href']
            # Only use parent link if it points to an image
            if any(link_href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                src = link_href

        alt = img.get('alt', '')
        local_path = download_image(src)
        if local_path:
            md = f"![{alt}]({local_path})"
            # Replace the parent <a> if it wraps the image, else just the img
            if parent_link and parent_link.find('img') == img:
                parent_link.replace_with(NavigableString(f"\n\n{md}\n\n"))
            else:
                img.replace_with(NavigableString(f"\n\n{md}\n\n"))

    return str(soup)


def html_to_markdown(html_content):
    """Convert preprocessed HTML to clean Markdown."""
    h = html2text.HTML2Text()
    h.body_width = 0  # Don't wrap lines
    h.protect_links = True
    h.wrap_links = False
    h.unicode_snob = True
    h.skip_internal_links = False
    h.inline_links = True
    h.ignore_images = False
    h.ignore_emphasis = False

    md = h.handle(html_content)

    # Clean up excessive whitespace
    md = re.sub(r'\n{4,}', '\n\n\n', md)
    md = md.strip()

    return md


def generate_front_matter(item, item_type, category_map, media_map):
    """Generate Jekyll front matter for a post or page."""
    title = html.unescape(item['title']['rendered'])
    slug = item['slug']

    fm = {
        'title': title,
        'permalink': f"/{slug}/",
        'layout': 'single',
    }

    if item_type == 'post':
        date_str = item['date']
        fm['date'] = date_str

        # Categories
        cat_ids = item.get('categories', [])
        cats = [category_map.get(cid, '') for cid in cat_ids if category_map.get(cid)]
        # Filter out Uncategorized
        cats = [c for c in cats if c != 'Uncategorized']
        if cats:
            fm['categories'] = cats

        # Featured image / header
        featured_id = item.get('featured_media', 0)
        if featured_id and featured_id in media_map:
            featured_url = media_map[featured_id]['source_url']
            local_path = download_image(featured_url)
            if local_path:
                fm['header'] = {
                    'image': local_path,
                }

    return fm


def process_post(post, category_map, media_map):
    """Process a single post and save as Jekyll markdown file."""
    title = html.unescape(post['title']['rendered'])
    slug = post['slug']
    date_str = post['date'][:10]  # YYYY-MM-DD
    content_html = post['content']['rendered']

    print(f"\nProcessing post: {title}")

    # Generate front matter
    fm = generate_front_matter(post, 'post', category_map, media_map)

    # Pre-process and convert HTML to markdown
    processed_html = preprocess_html(content_html)
    markdown = html_to_markdown(processed_html)

    # Build the file content
    front_matter_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    file_content = f"---\n{front_matter_str}---\n\n{markdown}\n"

    # Save to _posts/YYYY-MM-DD-slug.md
    filename = f"{date_str}-{slug}.md"
    filepath = POSTS_DIR / filename
    filepath.write_text(file_content, encoding='utf-8')
    print(f"  Saved: {filepath.name}")


def process_page(page, media_map):
    """Process a single page and save as Jekyll markdown file."""
    title = html.unescape(page['title']['rendered'])
    slug = page['slug']
    content_html = page['content']['rendered']

    print(f"\nProcessing page: {title}")

    fm = generate_front_matter(page, 'page', {}, media_map)

    processed_html = preprocess_html(content_html)
    markdown = html_to_markdown(processed_html)

    front_matter_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    file_content = f"---\n{front_matter_str}---\n\n{markdown}\n"

    filepath = PAGES_DIR / f"{slug}.md"
    filepath.write_text(file_content, encoding='utf-8')
    print(f"  Saved: {filepath.name}")


def main():
    print("=" * 60)
    print("WordPress to Jekyll Migration — theboardingcall.com")
    print("=" * 60)

    # Create output directories
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Build lookup maps
    media_map = build_media_map()
    category_map = build_category_map()

    # Fetch all posts
    print("\nFetching posts...")
    posts = fetch_all_paginated('posts', {'_embed': '1'})
    print(f"  Found {len(posts)} posts")

    # Fetch all pages
    print("\nFetching pages...")
    pages = fetch_all_paginated('pages')
    print(f"  Found {len(pages)} pages")

    # Process posts (sorted by date)
    posts.sort(key=lambda p: p['date'])
    for post in posts:
        process_post(post, category_map, media_map)

    # Process pages
    for page in pages:
        process_page(page, media_map)

    # Summary
    print("\n" + "=" * 60)
    print("Migration complete!")
    print(f"  Posts: {len(posts)}")
    print(f"  Pages: {len(pages)}")

    # Count downloaded images
    image_count = sum(1 for _ in IMAGES_DIR.rglob('*') if _.is_file())
    print(f"  Images downloaded: {image_count}")
    print("=" * 60)


if __name__ == '__main__':
    main()
