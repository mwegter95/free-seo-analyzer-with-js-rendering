"""
SEO Analyzer App — Local SEO analysis tool with JS rendering support.
Uses Playwright for headless browser rendering and BeautifulSoup for HTML parsing.
"""

import re
import json
import math
import time
import asyncio
from urllib.parse import urlparse, urljoin
from collections import Counter

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from bs4 import BeautifulSoup, Comment
import textstat

app = Flask(__name__, static_folder="static")
CORS(app)

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
        response = await page.goto(url, wait_until="networkidle", timeout=30000)
        timing["status_code"] = response.status if response else None
    except Exception as exc:
        timing["status_code"] = None
        timing["error"] = str(exc)[:200]

    # Small extra wait for late JS
    await page.wait_for_timeout(1500)
    html = await page.content()
    timing["total_ms"] = round((time.time() - t0) * 1000)
    return html, timing


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
        # Same domain only
        if parsed.netloc != root_netloc:
            continue
        # Normalise: drop fragment, keep path+query
        clean = parsed._replace(fragment="").geturl()
        # Skip non-page resources
        ext = parsed.path.rsplit(".", 1)[-1].lower() if "." in parsed.path.split("/")[-1] else ""
        if ext in ("jpg", "jpeg", "png", "gif", "svg", "webp", "pdf", "zip",
                    "mp3", "mp4", "wav", "css", "js", "ico", "woff", "woff2", "ttf"):
            continue
        found.add(clean)
    return found


# -- Server-Sent Events streaming crawl -----------------------------------

import queue
import threading

# Holds crawl state for active crawl (single-user local app)
_crawl_state: dict = {}


def _run_crawl(start_url: str, max_pages: int, state: dict):
    """Run full site crawl in a background thread using asyncio."""
    asyncio.run(_async_crawl(start_url, max_pages, state))


async def _async_crawl(start_url: str, max_pages: int, state: dict):
    from playwright.async_api import async_playwright

    parsed_root = urlparse(start_url)
    root_netloc = parsed_root.netloc

    visited: set[str] = set()
    to_visit: list[str] = [start_url]
    page_reports: list[dict] = []
    all_site_issues: list[dict] = []

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
        page = await context.new_page()

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            # Normalise
            url_parsed = urlparse(url)
            url_clean = url_parsed._replace(fragment="").geturl()
            if url_clean in visited:
                continue
            visited.add(url_clean)

            page_num = len(visited)
            state["q"].put({"type": "status", "page": page_num, "url": url_clean,
                            "queued": len(to_visit), "total_found": len(visited) + len(to_visit)})

            try:
                html, timing = await fetch_rendered_html(url_clean, page)
            except Exception as exc:
                state["q"].put({"type": "page_error", "url": url_clean, "error": str(exc)[:300]})
                continue

            # Discover more internal links
            try:
                new_links = _discover_internal_links(html, url_clean, root_netloc)
                for link in new_links:
                    if link not in visited and link not in to_visit:
                        to_visit.append(link)
            except Exception:
                pass

            # Analyse
            try:
                report = analyze_html(html, url_clean, timing)
                page_reports.append(report)
                # Stream individual page result
                state["q"].put({"type": "page_done", "report": report})
            except Exception as exc:
                state["q"].put({"type": "page_error", "url": url_clean, "error": str(exc)[:300]})

        await browser.close()

    # Build site-wide summary
    summary = _build_site_summary(page_reports)
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


@app.route("/api/crawl", methods=["POST"])
def api_crawl_start():
    """Start a full-site crawl. Returns immediately; use /api/crawl/stream to get results via SSE."""
    global _crawl_state
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    max_pages = min(int(data.get("max_pages", 50)), 200)
    if not url:
        return jsonify({"error": "No URL provided."}), 400
    if not url.startswith("http"):
        url = "https://" + url

    _crawl_state = {"q": queue.Queue(), "started": True}
    t = threading.Thread(target=_run_crawl, args=(url, max_pages, _crawl_state), daemon=True)
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  🔍  SEO Analyzer running at http://localhost:5015\n")
    app.run(host="0.0.0.0", port=5015, debug=False)
