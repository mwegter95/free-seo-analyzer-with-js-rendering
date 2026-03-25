"""
SEO Analyzer App — Local SEO analysis tool with JS rendering support.
Uses Playwright for headless browser rendering and BeautifulSoup for HTML parsing.
"""

import re
import json
import math
import time
import asyncio
import queue
import threading
import xml.etree.ElementTree as ET
import urllib.request
from urllib.parse import urlparse, urljoin
from collections import Counter
from datetime import datetime
from pathlib import Path
import os

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from bs4 import BeautifulSoup, Comment
import textstat

app = Flask(__name__, static_folder="static")
CORS(app)

# Outputs folder for auto-saved reports
OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_text(soup: BeautifulSoup) -> str:
    """Extract visible text from rendered HTML."""
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _word_list(text: str):
    return re.findall(r"[a-zA-Z''-]+", text.lower())


def _extract_keywords(words, top_n=20):
    """Return top‑N single‑word keywords by frequency (stop‑words removed)."""
    stop = set(
        "a an the and or but in on at to for of is it this that was were be "
        "been being have has had do does did will would shall should may might "
        "can could i me my we our you your he him his she her they them their "
        "its not no nor so if then else when where how what which who whom why "
        "with from by as into through during before after above below between "
        "out off over under again further once here there all each every both "
        "few more most other some such only own same than too very just about "
        "up also back still even new now old well way because thing things "
        "much get got go going know like make us am are".split()
    )
    filtered = [w for w in words if w not in stop and len(w) > 2]
    return Counter(filtered).most_common(top_n)


def _extract_ngrams(words, n=2, top_k=10):
    """Return top‑k n‑grams."""
    stop = set(
        "a an the and or but in on at to for of is it this that was were be "
        "been being have has had do does did will would shall should may might "
        "can could i me my we our you your he him his she her they them their "
        "its not no nor so if then else".split()
    )
    ngrams = []
    for i in range(len(words) - n + 1):
        gram = words[i : i + n]
        if not any(w in stop for w in gram) and all(len(w) > 2 for w in gram):
            ngrams.append(" ".join(gram))
    return Counter(ngrams).most_common(top_k)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze_html(html: str, url: str, timing: dict) -> dict:
    """Run all SEO checks on rendered HTML. Return structured report."""
    soup = BeautifulSoup(html, "lxml")
    parsed = urlparse(url)
    report: dict = {"url": url, "timing": timing, "scores": {}, "sections": {}}

    # --- Title ---
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    title_len = len(title)
    title_issues = []
    if not title:
        title_issues.append("Missing <title> tag.")
    elif title_len < 30:
        title_issues.append(f"Title too short ({title_len} chars). Aim for 50‑60.")
    elif title_len > 60:
        title_issues.append(f"Title too long ({title_len} chars). Aim for 50‑60.")
    report["sections"]["title"] = {
        "value": title,
        "length": title_len,
        "issues": title_issues,
        "pass": len(title_issues) == 0,
    }

    # --- Meta Description ---
    meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    meta_desc = meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.get("content") else ""
    md_len = len(meta_desc)
    md_issues = []
    if not meta_desc:
        md_issues.append("Missing meta description.")
    elif md_len < 120:
        md_issues.append(f"Meta description short ({md_len} chars). Aim for 150‑160.")
    elif md_len > 160:
        md_issues.append(f"Meta description too long ({md_len} chars). Aim for 150‑160.")
    report["sections"]["meta_description"] = {
        "value": meta_desc,
        "length": md_len,
        "issues": md_issues,
        "pass": len(md_issues) == 0,
    }

    # --- Meta Keywords (legacy but still checked) ---
    meta_kw_tag = soup.find("meta", attrs={"name": re.compile(r"keywords", re.I)})
    meta_kw = meta_kw_tag["content"].strip() if meta_kw_tag and meta_kw_tag.get("content") else ""

    # --- Canonical ---
    canon = soup.find("link", rel="canonical")
    canon_href = canon["href"] if canon and canon.get("href") else ""
    canon_issues = []
    if not canon_href:
        canon_issues.append("No canonical URL set.")
    report["sections"]["canonical"] = {"value": canon_href, "issues": canon_issues, "pass": len(canon_issues) == 0}

    # --- Robots meta ---
    robots_tag = soup.find("meta", attrs={"name": re.compile(r"robots", re.I)})
    robots = robots_tag["content"] if robots_tag and robots_tag.get("content") else ""
    robots_issues = []
    if robots and ("noindex" in robots.lower()):
        robots_issues.append("Page is set to noindex!")
    report["sections"]["robots"] = {"value": robots, "issues": robots_issues, "pass": len(robots_issues) == 0}

    # --- Viewport ---
    vp = soup.find("meta", attrs={"name": "viewport"})
    vp_content = vp["content"] if vp and vp.get("content") else ""
    vp_issues = []
    if not vp_content:
        vp_issues.append("Missing viewport meta tag — bad for mobile.")
    report["sections"]["viewport"] = {"value": vp_content, "issues": vp_issues, "pass": len(vp_issues) == 0}

    # --- Charset ---
    charset_tag = soup.find("meta", charset=True)
    charset = charset_tag.get("charset", "") if charset_tag else ""
    if not charset:
        http_equiv = soup.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
        if http_equiv and http_equiv.get("content"):
            m = re.search(r"charset=([\w-]+)", http_equiv["content"], re.I)
            charset = m.group(1) if m else ""
    report["sections"]["charset"] = {"value": charset, "issues": [] if charset else ["No charset declared."], "pass": bool(charset)}

    # --- Language ---
    html_tag = soup.find("html")
    lang = html_tag.get("lang", "") if html_tag else ""
    report["sections"]["language"] = {"value": lang, "issues": [] if lang else ["No lang attribute on <html>."], "pass": bool(lang)}

    # --- Headings ---
    headings = {}
    heading_issues = []
    for level in range(1, 7):
        tags = soup.find_all(f"h{level}")
        headings[f"h{level}"] = [t.get_text(strip=True) for t in tags]
    if len(headings["h1"]) == 0:
        heading_issues.append("Missing H1 tag.")
    elif len(headings["h1"]) > 1:
        heading_issues.append(f"Multiple H1 tags found ({len(headings['h1'])}). Use exactly one.")
    if headings["h1"] and headings["h1"][0] and len(headings["h1"][0]) > 70:
        heading_issues.append("H1 is very long (>70 chars). Keep it concise.")
    report["sections"]["headings"] = {"counts": {k: len(v) for k, v in headings.items()}, "h1": headings["h1"], "h2": headings["h2"], "issues": heading_issues, "pass": len(heading_issues) == 0}

    # --- Images ---
    images = soup.find_all("img")
    imgs_missing_alt = []
    imgs_empty_alt = []
    for img in images:
        src = img.get("src", img.get("data-src", ""))
        alt = img.get("alt")
        if alt is None:
            imgs_missing_alt.append(src[:120])
        elif alt.strip() == "":
            imgs_empty_alt.append(src[:120])
    img_issues = []
    if imgs_missing_alt:
        img_issues.append(f"{len(imgs_missing_alt)} image(s) missing alt attribute.")
    if imgs_empty_alt:
        img_issues.append(f"{len(imgs_empty_alt)} image(s) with empty alt text.")
    report["sections"]["images"] = {
        "total": len(images),
        "missing_alt": imgs_missing_alt[:20],
        "empty_alt": imgs_empty_alt[:20],
        "issues": img_issues,
        "pass": len(img_issues) == 0,
    }

    # --- Links ---
    anchors = soup.find_all("a", href=True)
    internal_links = []
    external_links = []
    nofollow_links = []
    broken_anchors = []
    for a in anchors:
        href = a["href"].strip()
        rel = a.get("rel", [])
        if isinstance(rel, str):
            rel = rel.split()
        if "nofollow" in [r.lower() for r in rel]:
            nofollow_links.append(href)
        if href.startswith("#"):
            continue
        if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        full = urljoin(url, href)
        lp = urlparse(full)
        if lp.netloc == parsed.netloc:
            internal_links.append(full)
        else:
            external_links.append(full)
    link_issues = []
    if len(internal_links) == 0:
        link_issues.append("No internal links found.")
    report["sections"]["links"] = {
        "internal": len(internal_links),
        "external": len(external_links),
        "nofollow": len(nofollow_links),
        "issues": link_issues,
        "pass": len(link_issues) == 0,
    }

    # --- Open Graph ---
    og_tags = {}
    for meta in soup.find_all("meta", property=re.compile(r"^og:", re.I)):
        og_tags[meta["property"]] = meta.get("content", "")
    og_issues = []
    for required in ["og:title", "og:description", "og:image", "og:url"]:
        if required not in og_tags:
            og_issues.append(f"Missing {required}.")
    report["sections"]["open_graph"] = {"tags": og_tags, "issues": og_issues, "pass": len(og_issues) == 0}

    # --- Twitter Card ---
    tw_tags = {}
    for meta in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:", re.I)}):
        tw_tags[meta["name"]] = meta.get("content", "")
    # Also look for property-based twitter tags
    for meta in soup.find_all("meta", property=re.compile(r"^twitter:", re.I)):
        tw_tags[meta["property"]] = meta.get("content", "")
    tw_issues = []
    if "twitter:card" not in tw_tags:
        tw_issues.append("Missing twitter:card meta tag.")
    report["sections"]["twitter_card"] = {"tags": tw_tags, "issues": tw_issues, "pass": len(tw_issues) == 0}

    # --- Structured Data / JSON-LD ---
    jsonld_scripts = soup.find_all("script", type="application/ld+json")
    schemas = []
    for s in jsonld_scripts:
        try:
            data = json.loads(s.string)
            schemas.append(data)
        except Exception:
            pass
    sd_issues = []
    if not schemas:
        sd_issues.append("No JSON-LD structured data found.")
    report["sections"]["structured_data"] = {
        "count": len(schemas),
        "types": [s.get("@type", "unknown") for s in schemas if isinstance(s, dict)],
        "issues": sd_issues,
        "pass": len(sd_issues) == 0,
    }

    # --- Content / Keywords ---
    visible_text = _clean_text(BeautifulSoup(html, "lxml"))
    words = _word_list(visible_text)
    word_count = len(words)
    content_issues = []
    if word_count < 300:
        content_issues.append(f"Thin content ({word_count} words). Aim for 300+ words.")

    top_keywords = _extract_keywords(words, top_n=20)
    bigrams = _extract_ngrams(words, n=2, top_k=10)
    trigrams = _extract_ngrams(words, n=3, top_k=10)

    # Keyword in title / meta-desc / H1
    keyword_placement = {}
    if top_keywords:
        primary = top_keywords[0][0]
        keyword_placement["primary_keyword"] = primary
        keyword_placement["in_title"] = primary in title.lower()
        keyword_placement["in_meta_desc"] = primary in meta_desc.lower()
        keyword_placement["in_h1"] = any(primary in h.lower() for h in headings["h1"])
        keyword_placement["in_url"] = primary in url.lower()
        if not keyword_placement["in_title"]:
            content_issues.append(f"Primary keyword '{primary}' not in title tag.")
        if not keyword_placement["in_meta_desc"]:
            content_issues.append(f"Primary keyword '{primary}' not in meta description.")
        if not keyword_placement["in_h1"]:
            content_issues.append(f"Primary keyword '{primary}' not in H1.")

    # Readability
    readability = {}
    if visible_text and word_count > 50:
        try:
            readability["flesch_reading_ease"] = round(textstat.flesch_reading_ease(visible_text), 1)
            readability["flesch_kincaid_grade"] = round(textstat.flesch_kincaid_grade(visible_text), 1)
            readability["gunning_fog"] = round(textstat.gunning_fog(visible_text), 1)
            readability["avg_sentence_length"] = round(textstat.avg_sentence_length(visible_text), 1)
        except Exception:
            pass

    report["sections"]["content"] = {
        "word_count": word_count,
        "top_keywords": [{"word": w, "count": c, "density": round(c / word_count * 100, 2)} for w, c in top_keywords],
        "bigrams": [{"phrase": p, "count": c} for p, c in bigrams],
        "trigrams": [{"phrase": p, "count": c} for p, c in trigrams],
        "keyword_placement": keyword_placement,
        "readability": readability,
        "issues": content_issues,
        "pass": len(content_issues) == 0,
    }

    # --- URL Structure ---
    url_issues = []
    path = parsed.path
    if len(url) > 75:
        url_issues.append("URL is quite long (>75 chars).")
    if re.search(r"[A-Z]", path):
        url_issues.append("URL path contains uppercase letters.")
    if "_" in path:
        url_issues.append("URL uses underscores; prefer hyphens.")
    if re.search(r"[?&]", url) and re.search(r"[?&]\w+=\w+", url):
        url_issues.append("URL has query parameters — may cause duplicate content.")
    report["sections"]["url_structure"] = {"url": url, "path": path, "issues": url_issues, "pass": len(url_issues) == 0}

    # --- HTTPS ---
    https_ok = parsed.scheme == "https"
    report["sections"]["https"] = {"secure": https_ok, "issues": [] if https_ok else ["Site not using HTTPS!"], "pass": https_ok}

    # --- Hreflang ---
    hreflangs = []
    for link in soup.find_all("link", rel="alternate", hreflang=True):
        hreflangs.append({"lang": link["hreflang"], "href": link.get("href", "")})
    report["sections"]["hreflang"] = {"tags": hreflangs, "issues": [], "pass": True}

    # --- Performance hints ---
    perf_issues = []
    inline_styles = soup.find_all("style")
    if len(inline_styles) > 5:
        perf_issues.append(f"{len(inline_styles)} inline <style> blocks — consider external CSS.")
    scripts = soup.find_all("script", src=True)
    render_blocking = [s for s in scripts if not s.get("async") and not s.get("defer")]
    if render_blocking:
        perf_issues.append(f"{len(render_blocking)} render-blocking scripts (no async/defer).")
    report["sections"]["performance_hints"] = {"inline_styles": len(inline_styles), "total_scripts": len(scripts), "render_blocking_scripts": len(render_blocking), "issues": perf_issues, "pass": len(perf_issues) == 0}

    # --- Overall score ---
    scored_sections = [
        "title", "meta_description", "canonical", "robots", "viewport",
        "headings", "images", "links", "open_graph", "twitter_card",
        "structured_data", "content", "url_structure", "https", "performance_hints",
        "charset", "language",
    ]
    passed = sum(1 for s in scored_sections if report["sections"].get(s, {}).get("pass", False))
    total = len(scored_sections)
    report["scores"]["passed"] = passed
    report["scores"]["total"] = total
    report["scores"]["percentage"] = round(passed / total * 100)

    # Collect all issues
    all_issues = []
    for s in scored_sections:
        sec = report["sections"].get(s, {})
        for issue in sec.get("issues", []):
            all_issues.append({"section": s, "issue": issue})
    report["all_issues"] = all_issues

    return report


# ---------------------------------------------------------------------------
# Playwright fetch
# ---------------------------------------------------------------------------

async def fetch_rendered_html(url: str, page) -> tuple[str, dict]:
    """Navigate an existing Playwright page to *url* and return rendered HTML."""
    timing = {}
    t0 = time.time()

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        timing["status_code"] = response.status if response else None
        # After DOM is loaded, wait briefly for JS frameworks to hydrate
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass  # Timeout is fine — page is likely already usable
    except Exception as exc:
        timing["status_code"] = None
        timing["error"] = str(exc)[:200]

    # Brief wait for late client-side rendering
    await page.wait_for_timeout(500)
    html = await page.content()
    timing["total_ms"] = round((time.time() - t0) * 1000)
    return html, timing


def _normalise_url(url: str) -> str:
    """Normalise a URL: drop fragment, strip trailing slash (except root), lowercase scheme+host."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    clean = parsed._replace(fragment="", path=path)
    return clean.geturl()


def _same_site(netloc_a: str, netloc_b: str) -> bool:
    """Check if two netlocs belong to the same site (handles www vs non-www)."""
    def strip_www(n):
        return n.lower().removeprefix("www.")
    return strip_www(netloc_a) == strip_www(netloc_b)


def _discover_internal_links(html: str, base_url: str, root_netloc: str) -> set[str]:
    """Extract internal links from rendered HTML."""
    soup = BeautifulSoup(html, "lxml")
    found: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        # Same domain only (handles www vs non-www)
        if not _same_site(parsed.netloc, root_netloc):
            continue
        # Normalise
        clean = _normalise_url(full)
        # Skip non-page resources
        last_segment = parsed.path.split("/")[-1]
        ext = last_segment.rsplit(".", 1)[-1].lower() if "." in last_segment else ""
        if ext in ("jpg", "jpeg", "png", "gif", "svg", "webp", "pdf", "zip",
                    "mp3", "mp4", "wav", "css", "js", "ico", "woff", "woff2", "ttf",
                    "eot", "xml", "json", "txt", "map"):
            continue
        found.add(clean)
    return found


# ---------------------------------------------------------------------------
# Sitemap fetching
# ---------------------------------------------------------------------------

def _fetch_sitemap_urls(start_url: str, root_netloc: str) -> list[str]:
    """Fetch URLs from sitemap.xml (supports sitemap index files)."""
    urls: list[str] = []
    parsed = urlparse(start_url)
    # Try common sitemap locations
    base = f"{parsed.scheme}://{parsed.netloc}"
    # Also try www variant
    www_base = f"{parsed.scheme}://www.{parsed.netloc}" if not parsed.netloc.startswith("www.") else base

    sitemap_candidates = []

    # First: check robots.txt for sitemap declarations
    for b in [base, www_base]:
        try:
            robots_url = f"{b}/robots.txt"
            req = urllib.request.Request(robots_url, headers={"User-Agent": "SEO-Analyzer/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                robots_text = resp.read().decode("utf-8", errors="ignore")
                for line in robots_text.splitlines():
                    if line.strip().lower().startswith("sitemap:"):
                        sm_url = line.split(":", 1)[1].strip()
                        if sm_url.startswith("http"):
                            sitemap_candidates.append(sm_url)
        except Exception:
            pass

    # Fallback: try common locations
    if not sitemap_candidates:
        for b in [base, www_base]:
            sitemap_candidates.extend([
                f"{b}/sitemap.xml",
                f"{b}/sitemap_index.xml",
                f"{b}/wp-sitemap.xml",
            ])

    visited_sitemaps: set[str] = set()

    def _parse_sitemap(sm_url: str, depth: int = 0):
        if depth > 3 or sm_url in visited_sitemaps:
            return
        visited_sitemaps.add(sm_url)
        try:
            req = urllib.request.Request(sm_url, headers={"User-Agent": "SEO-Analyzer/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            # Strip namespaces for easier parsing
            content = re.sub(r'\s+xmlns\s*=\s*"[^"]*"', '', content, count=1)
            root = ET.fromstring(content)

            # Sitemap index (contains <sitemap><loc> entries)
            for sitemap_elem in root.iter("sitemap"):
                loc = sitemap_elem.find("loc")
                if loc is not None and loc.text:
                    child_url = loc.text.strip()
                    # Strip CDATA if present
                    child_url = child_url.strip()
                    _parse_sitemap(child_url, depth + 1)

            # URL set (contains <url><loc> entries)
            for url_elem in root.iter("url"):
                loc = url_elem.find("loc")
                if loc is not None and loc.text:
                    page_url = loc.text.strip()
                    p = urlparse(page_url)
                    if _same_site(p.netloc, root_netloc):
                        urls.append(_normalise_url(page_url))
        except Exception:
            pass

    for sm in sitemap_candidates:
        _parse_sitemap(sm)

    return list(set(urls))


def _resolve_url(start_url: str) -> tuple[str, str]:
    """Follow redirects and return (resolved_url, root_netloc)."""
    resolved_url = start_url
    try:
        req = urllib.request.Request(start_url, headers={"User-Agent": "SEO-Analyzer/1.0"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resolved_url = resp.url
    except Exception:
        try:
            req = urllib.request.Request(start_url, headers={"User-Agent": "SEO-Analyzer/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                resolved_url = resp.url
        except Exception:
            pass
    parsed = urlparse(resolved_url)
    return _normalise_url(resolved_url), parsed.netloc


def _extract_navbar_links(html: str, base_url: str, root_netloc: str) -> list[str]:
    """Extract links from <nav>, <header>, and common navbar containers."""
    soup = BeautifulSoup(html, "lxml")
    nav_links: set[str] = set()
    # Search nav tags, header tags, and common class/id patterns
    nav_containers = soup.find_all("nav")
    nav_containers += soup.find_all("header")
    for attr in ["class", "id"]:
        for pattern in ["nav", "menu", "navbar", "main-nav", "primary-nav",
                        "site-nav", "site-header", "main-menu", "primary-menu"]:
            nav_containers += soup.find_all(attrs={attr: re.compile(pattern, re.I)})

    for container in nav_containers:
        for a in container.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            full = urljoin(base_url, href)
            parsed = urlparse(full)
            if not _same_site(parsed.netloc, root_netloc):
                continue
            nav_links.add(_normalise_url(full))
    return sorted(nav_links)


def _group_urls_by_branch(urls: list[str]) -> dict:
    """Group URLs into 'branches' by their first path segment."""
    branches: dict[str, list[str]] = {}
    for u in urls:
        parsed = urlparse(u)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        branch = "/" + parts[0] + "/" if parts else "/"
        if branch not in branches:
            branches[branch] = []
        branches[branch].append(u)
    # Sort branches by count descending
    return dict(sorted(branches.items(), key=lambda x: -len(x[1])))


def _clean_site_name(url: str) -> str:
    """Extract clean site name from URL (no https, www, or path)."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    # Remove www.
    netloc = netloc.removeprefix("www.")
    # Remove port if present
    netloc = netloc.split(":")[0]
    return netloc


def _save_report_files(url: str, summary: dict, page_reports: list[dict]):
    """Save JSON and TXT reports to outputs/ folder with dated filename."""
    site_name = _clean_site_name(url)
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H_%M_%S")
    base_name = f"{site_name}_seo_report_{date_str}_{time_str}"
    
    # Save JSON
    json_path = OUTPUTS_DIR / f"{base_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "pages": page_reports}, f, indent=2, ensure_ascii=False)
    
    # Save TXT
    txt_path = OUTPUTS_DIR / f"{base_name}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"FULL SITE SEO REPORT\n{'=' * 70}\n")
        if summary:
            f.write(f"Pages Analyzed: {summary.get('total_pages', 0)}\n")
            f.write(f"Average Score: {summary.get('avg_score', 0)}%\n")
            f.write(f"Total Words: {summary.get('total_words', 0)}\n")
            f.write(f"Total Issues: {summary.get('total_issues', 0)}\n\n")
            
            if summary.get("site_keywords"):
                f.write(f"SITE-WIDE TOP KEYWORDS\n{'-' * 40}\n")
                for kw in summary["site_keywords"]:
                    f.write(f"  {kw['word']}: {kw['count']}\n")
                f.write("\n")
            
            if summary.get("site_bigrams"):
                f.write(f"SITE-WIDE TOP PHRASES\n{'-' * 40}\n")
                for bg in summary["site_bigrams"]:
                    f.write(f"  {bg['phrase']}: {bg['count']}\n")
                f.write("\n")
        
        for r in page_reports:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"PAGE: {r['url']}\n")
            f.write(f"Score: {r['scores']['percentage']}% ({r['scores']['passed']}/{r['scores']['total']} passed)\n")
            f.write(f"Status: {r['timing'].get('status_code', '?')} | {r['timing'].get('total_ms', '?')}ms\n")
            
            for key, sec in r.get("sections", {}).items():
                f.write(f"\n  --- {key.replace('_', ' ').upper()} ---\n")
                if sec.get("value") is not None:
                    f.write(f"    Value: {sec['value']}\n")
                if sec.get("length") is not None:
                    f.write(f"    Length: {sec['length']}\n")
                if sec.get("word_count") is not None:
                    f.write(f"    Word count: {sec['word_count']}\n")
                if sec.get("total") is not None:
                    f.write(f"    Total: {sec['total']}\n")
                if sec.get("internal") is not None:
                    f.write(f"    Internal: {sec['internal']} | External: {sec.get('external', 0)}\n")
                if sec.get("issues"):
                    for i in sec["issues"]:
                        f.write(f"    ⚠ {i}\n")
                if sec.get("top_keywords"):
                    f.write(f"    Top Keywords:\n")
                    for kw in sec["top_keywords"][:10]:
                        f.write(f"      {kw['word']}: {kw['count']} ({kw['density']}%)\n")
                if sec.get("readability", {}).get("flesch_reading_ease") is not None:
                    rd = sec["readability"]
                    f.write(f"    Readability: Flesch={rd['flesch_reading_ease']}, Grade={rd['flesch_kincaid_grade']}, Fog={rd['gunning_fog']}\n")
            
            if r.get("all_issues"):
                f.write(f"\n  ALL ISSUES ({len(r['all_issues'])}):\n")
                for iss in r["all_issues"]:
                    f.write(f"    [{iss['section']}] {iss['issue']}\n")
    
    return {"json": str(json_path), "txt": str(txt_path)}


def _prescan(start_url: str) -> dict:
    """Do a lightweight prescan: resolve URL, fetch sitemap, load homepage for navbar."""
    resolved_url, root_netloc = _resolve_url(start_url)

    # Fetch sitemap URLs
    sitemap_urls = []
    try:
        sitemap_urls = _fetch_sitemap_urls(resolved_url, root_netloc)
    except Exception:
        pass

    # Fetch homepage and extract navbar links
    navbar_urls: list[str] = []
    homepage_links: list[str] = []
    try:
        req = urllib.request.Request(resolved_url, headers={"User-Agent": "SEO-Analyzer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        navbar_urls = _extract_navbar_links(html, resolved_url, root_netloc)
        # Also get all internal links from homepage (non-rendered, quick)
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            full = urljoin(resolved_url, href)
            parsed = urlparse(full)
            if _same_site(parsed.netloc, root_netloc):
                homepage_links.append(_normalise_url(full))
    except Exception:
        pass

    # Combine all discovered URLs
    all_urls = list(set([resolved_url] + sitemap_urls + navbar_urls + homepage_links))
    branches = _group_urls_by_branch(all_urls)

    # Figure out which branches the navbar links touch
    navbar_branches: set[str] = set()
    for u in navbar_urls:
        parsed = urlparse(u)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        branch = "/" + parts[0] + "/" if parts else "/"
        navbar_branches.add(branch)

    return {
        "resolved_url": resolved_url,
        "root_netloc": root_netloc,
        "total_urls": len(all_urls),
        "navbar_urls": navbar_urls,
        "navbar_branches": sorted(navbar_branches),
        "branches": {b: {"count": len(urls), "sample_urls": urls[:5]}
                     for b, urls in branches.items()},
        "all_urls": all_urls,
    }


# -- Server-Sent Events streaming crawl -----------------------------------

# Holds crawl state for active crawl (single-user local app)
_crawl_state: dict = {}

# Number of parallel browser tabs for crawling
PARALLEL_TABS = 10


def _run_crawl(start_url: str, max_pages: int, state: dict,
               seed_urls: list[str] | None = None,
               allowed_branches: list[str] | None = None):
    """Run full site crawl in a background thread using asyncio."""
    asyncio.run(_async_crawl(start_url, max_pages, state, seed_urls, allowed_branches))


async def _async_crawl(start_url: str, max_pages: int, state: dict,
                       seed_urls: list[str] | None = None,
                       allowed_branches: list[str] | None = None):
    from playwright.async_api import async_playwright

    # If we already have prescan data, skip the resolve + sitemap step
    if seed_urls is not None:
        # seed_urls already contains the filtered URL list
        parsed_root = urlparse(start_url)
        root_netloc = parsed_root.netloc

        state["q"].put({"type": "status", "page": 0, "url": start_url,
                        "queued": len(seed_urls), "total_found": len(seed_urls),
                        "message": f"Starting crawl of {len(seed_urls)} selected URLs…"})
    else:
        # Legacy path: resolve + sitemap discovery
        resolved_url = start_url
        try:
            req = urllib.request.Request(start_url, headers={"User-Agent": "SEO-Analyzer/1.0"}, method="HEAD")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resolved_url = resp.url
        except Exception:
            try:
                req = urllib.request.Request(start_url, headers={"User-Agent": "SEO-Analyzer/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resolved_url = resp.url
            except Exception:
                pass

        parsed_root = urlparse(resolved_url)
        root_netloc = parsed_root.netloc
        start_url = _normalise_url(resolved_url)

        state["q"].put({"type": "status", "page": 0, "url": start_url,
                        "queued": 0, "total_found": 1,
                        "message": f"Resolved to {root_netloc}, checking sitemap…"})

        sitemap_urls = []
        try:
            sitemap_urls = _fetch_sitemap_urls(start_url, root_netloc)
            if sitemap_urls:
                state["q"].put({"type": "status", "page": 0, "url": start_url,
                                "queued": len(sitemap_urls), "total_found": len(sitemap_urls),
                                "message": f"Found {len(sitemap_urls)} URLs in sitemap"})
        except Exception:
            pass
        seed_urls = [start_url] + sitemap_urls

    def _url_matches_branches(u: str) -> bool:
        """Check if a URL belongs to one of the allowed branches."""
        if allowed_branches is None:
            return True
        if allowed_branches == []:
            # Empty list means: navbar-only mode, no link discovery
            # Only allow URLs that are in the original seed list
            return False
        parsed = urlparse(u)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        branch = "/" + parts[0] + "/" if parts else "/"
        return branch in allowed_branches

    visited: set[str] = set()
    to_visit_set: set[str] = set()
    to_visit: list[str] = []

    def _enqueue(u: str, force: bool = False):
        norm = _normalise_url(u)
        if norm not in visited and norm not in to_visit_set and (force or _url_matches_branches(norm)):
            to_visit_set.add(norm)
            to_visit.append(norm)

    # Seed queue - force=True to bypass branch checking for initial seeds
    for su in seed_urls:
        _enqueue(su, force=True)

    page_reports: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )

        # Create parallel tabs
        pages = []
        for _ in range(PARALLEL_TABS):
            pages.append(await context.new_page())

        async def _process_url(tab, url_to_crawl):
            """Fetch, discover links, analyse a single URL on a given tab."""
            try:
                html, timing = await fetch_rendered_html(url_to_crawl, tab)
            except Exception as exc:
                state["q"].put({"type": "page_error", "url": url_to_crawl, "error": str(exc)[:300]})
                return

            # Discover more internal links
            try:
                new_links = _discover_internal_links(html, url_to_crawl, root_netloc)
                for link in new_links:
                    _enqueue(link)
            except Exception:
                pass

            # Analyse
            try:
                report = analyze_html(html, url_to_crawl, timing)
                page_reports.append(report)
                state["q"].put({"type": "page_done", "report": report})
            except Exception as exc:
                state["q"].put({"type": "page_error", "url": url_to_crawl, "error": str(exc)[:300]})

        # Crawl with parallel tabs
        while to_visit and len(visited) < max_pages:
            # Grab a batch of URLs for parallel processing
            batch: list[str] = []
            while to_visit and len(batch) < PARALLEL_TABS and (len(visited) + len(batch)) < max_pages:
                url = to_visit.pop(0)
                norm = _normalise_url(url)
                if norm in visited:
                    continue
                visited.add(norm)
                batch.append(norm)

            if not batch:
                break

            page_num = len(visited)
            state["q"].put({"type": "status", "page": page_num, "url": batch[0],
                            "queued": len(to_visit), "total_found": len(visited) + len(to_visit)})

            # Run batch in parallel
            tasks = []
            for i, burl in enumerate(batch):
                tasks.append(_process_url(pages[i % len(pages)], burl))
            await asyncio.gather(*tasks)

        await browser.close()

    # Build site-wide summary
    summary = _build_site_summary(page_reports)
    
    # Auto-save reports to outputs/ folder
    try:
        saved_paths = _save_report_files(start_url, summary, page_reports)
        state["q"].put({"type": "status", "page": len(visited), "url": "",
                        "queued": 0, "total_found": len(visited),
                        "message": f"Reports saved: {Path(saved_paths['json']).name}"})
    except Exception as e:
        state["q"].put({"type": "status", "page": len(visited), "url": "",
                        "queued": 0, "total_found": len(visited),
                        "message": f"Warning: Failed to save reports: {e}"})
    
    state["q"].put({"type": "complete", "summary": summary})


def _build_site_summary(reports: list[dict]) -> dict:
    """Aggregate page reports into a site-wide summary."""
    total_pages = len(reports)
    if total_pages == 0:
        return {"total_pages": 0}

    total_score = sum(r["scores"]["percentage"] for r in reports)
    avg_score = round(total_score / total_pages)

    all_issues: list[dict] = []
    section_pass_counts: dict = {}
    site_keywords: Counter = Counter()
    site_bigrams: Counter = Counter()
    total_words = 0

    for r in reports:
        for iss in r.get("all_issues", []):
            all_issues.append({**iss, "url": r["url"]})

        for sec_name, sec in r.get("sections", {}).items():
            if sec_name not in section_pass_counts:
                section_pass_counts[sec_name] = {"pass": 0, "total": 0}
            section_pass_counts[sec_name]["total"] += 1
            if sec.get("pass"):
                section_pass_counts[sec_name]["pass"] += 1

        content = r.get("sections", {}).get("content", {})
        total_words += content.get("word_count", 0)
        for kw in content.get("top_keywords", []):
            site_keywords[kw["word"]] += kw["count"]
        for bg in content.get("bigrams", []):
            site_bigrams[bg["phrase"]] += bg["count"]

    # Pages with worst scores
    sorted_reports = sorted(reports, key=lambda r: r["scores"]["percentage"])
    worst_pages = [{"url": r["url"], "score": r["scores"]["percentage"],
                    "issue_count": len(r.get("all_issues", []))} for r in sorted_reports[:5]]

    return {
        "total_pages": total_pages,
        "avg_score": avg_score,
        "total_words": total_words,
        "total_issues": len(all_issues),
        "all_issues": all_issues,
        "section_pass_rates": section_pass_counts,
        "site_keywords": [{"word": w, "count": c} for w, c in site_keywords.most_common(30)],
        "site_bigrams": [{"phrase": p, "count": c} for p, c in site_bigrams.most_common(15)],
        "worst_pages": worst_pages,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Single-page analysis (kept for backwards compat)."""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not url.startswith("http"):
        url = "https://" + url

    try:
        async def _single():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                )
                page = await ctx.new_page()
                html, timing = await fetch_rendered_html(url, page)
                await browser.close()
            return html, timing
        html, timing = asyncio.run(_single())
    except Exception as e:
        return jsonify({"error": f"Failed to fetch page: {e}"}), 500

    try:
        report = analyze_html(html, url, timing)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500

    return jsonify(report)


@app.route("/api/prescan", methods=["POST"])
def api_prescan():
    """Quick pre-scan: resolve URL, fetch sitemap, extract navbar links, group by branch."""
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not url.startswith("http"):
        url = "https://" + url
    try:
        result = _prescan(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Pre-scan failed: {e}"}), 500


@app.route("/api/crawl", methods=["POST"])
def api_crawl_start():
    """Start a full-site crawl. Returns immediately; use /api/crawl/stream to get results via SSE."""
    global _crawl_state
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    max_pages = min(int(data.get("max_pages", 100)), 500)
    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not url.startswith("http"):
        url = "https://" + url

    # Accept optional prescan-based filtering
    seed_urls = data.get("seed_urls")  # pre-filtered URL list
    allowed_branches = data.get("allowed_branches")  # list of branch prefixes

    _crawl_state = {"q": queue.Queue(), "started": True}
    t = threading.Thread(
        target=_run_crawl,
        args=(url, max_pages, _crawl_state, seed_urls, allowed_branches),
        daemon=True,
    )
    t.start()
    return jsonify({"status": "started", "url": url, "max_pages": max_pages})


@app.route("/api/crawl/stream")
def api_crawl_stream():
    """SSE endpoint streaming crawl progress and results."""
    def generate():
        global _crawl_state
        if not _crawl_state.get("started"):
            yield f"data: {json.dumps({'type': 'error', 'error': 'No crawl in progress'})}\n\n"
            return
        q = _crawl_state["q"]
        while True:
            try:
                msg = q.get(timeout=120)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "complete":
                    break
            except Exception:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Timeout waiting for crawl data'})}\n\n"
                break

    from flask import Response
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/reports")
def api_list_reports():
    """List all saved reports in outputs/ folder."""
    try:
        reports = []
        # Ensure outputs directory exists
        if not OUTPUTS_DIR.exists():
            OUTPUTS_DIR.mkdir(exist_ok=True)
        
        # Safely list JSON files
        json_files = list(OUTPUTS_DIR.glob("*.json"))
        for f in sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                stat = f.stat()
                reports.append({
                    "filename": f.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except Exception:
                continue  # Skip files that can't be read
        
        return jsonify({"reports": reports}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to list reports: {str(e)}"}), 500


@app.route("/api/reports/<filename>")
def api_get_report(filename):
    """Serve a specific saved report JSON file."""
    try:
        # Security: only allow alphanumeric, dots, dashes, underscores
        if not re.match(r'^[\w\.\-]+\.json$', filename):
            return jsonify({"error": "Invalid filename"}), 400
        
        file_path = OUTPUTS_DIR / filename
        if not file_path.exists():
            return jsonify({"error": "Report not found"}), 404
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Failed to load report: {e}"}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  🔍  SEO Analyzer running at http://localhost:5015\n")
    app.run(host="0.0.0.0", port=5015, debug=False)
