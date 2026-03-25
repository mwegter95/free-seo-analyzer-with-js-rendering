# 🔍 SEO Analyzer

A powerful, **free, local SEO analysis tool** with **full JavaScript rendering support** — no paywalls, no limitations. Automatically crawls your entire website and generates comprehensive SEO reports.

## Table of Contents

- [Why This Tool?](#why-this-tool)
- [What Gets Analyzed](#what-gets-analyzed)
- [Installation & Setup](#installation--setup)
  - [Quick Start](#quick-start)
  - [Manual Setup](#manual-setup-alternative)
- [Usage](#usage)
- [Technology Stack](#technology-stack)
- [Why Local + JavaScript Rendering Matters](#why-local--javascript-rendering-matters)
- [Use Cases](#use-cases)
- [Tips for Best Results](#tips-for-best-results)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Why This Tool?

- **🚀 Full JavaScript Rendering**: Uses Playwright headless Chromium to render pages exactly as Google sees them — including SPAs, dynamic content, and client-side rendered apps
- **🌐 Complete Site Crawling**: Automatically discovers and analyzes all internal pages, not just the homepage
- **📊 17 SEO Checks Per Page**: Title, meta description, headings, keywords, images, links, Open Graph, Twitter Cards, structured data, performance hints, and more
- **💰 100% Free & Local**: No API limits, no subscriptions, no cloud services — runs entirely on your machine
- **🎯 Keyword Analysis**: Extracts top keywords, 2-word & 3-word phrases, keyword density, and checks placement in critical locations
- **📈 Readability Metrics**: Flesch Reading Ease, Flesch-Kincaid Grade, Gunning Fog Index
- **📤 Export Reports**: JSON & plain text formats for documentation and sharing
- **⚡ Real-Time Progress**: Live crawl status with streaming updates

## What Gets Analyzed

### On-Page SEO

- **Title Tag**: Length, optimization, keyword presence
- **Meta Description**: Length, optimization, keyword presence
- **Headings (H1-H6)**: Structure, hierarchy, keyword usage
- **URL Structure**: Length, formatting, keyword presence
- **Content Quality**: Word count, thin content detection

### Keywords & Content

- **Top Keywords**: Frequency analysis with density percentages
- **2-Word & 3-Word Phrases**: Multi-word keyword opportunities
- **Strategic Placement**: Keyword presence in title, meta, H1, URL
- **Readability Scores**: Multiple readability indices

### Technical SEO

- **Canonical URLs**: Proper URL canonicalization
- **Robots Meta**: Indexing directives
- **HTTPS**: Security check
- **Viewport**: Mobile responsiveness
- **Charset & Language**: Proper encoding and language tags

### Images

- **Alt Text**: Missing or empty alt attributes
- **Image Count**: Total images per page

### Links

- **Internal Links**: Internal linking structure
- **External Links**: Outbound link analysis
- **Nofollow Detection**: Rel="nofollow" identification

### Social & Rich Media

- **Open Graph**: Facebook/LinkedIn sharing tags
- **Twitter Cards**: Twitter sharing optimization
- **Structured Data (JSON-LD)**: Schema.org markup for rich snippets

### Performance

- **Inline Styles**: Excessive inline CSS detection
- **Render-Blocking Scripts**: Scripts without async/defer
- **Page Load Times**: Navigation and total render time

### Site-Wide Analysis

- **Average Score**: Overall site health percentage
- **Check Pass Rates**: How each SEO check performs across all pages
- **Site-Wide Keywords**: Aggregated keyword usage across the entire site
- **Worst-Performing Pages**: Pages needing the most attention

## Installation & Setup

### Prerequisites

- Python 3.8 or higher
- ~200MB disk space for Playwright Chromium

### Quick Start

1. **Get the code**

   **Option A: Clone with Git**

   ```bash
   git clone https://github.com/mwegter95/free-seo-analyzer-with-js-rendering.git
   cd free-seo-analyzer-with-js-rendering
   ```

   **Option B: Download ZIP**
   - Go to [https://github.com/mwegter95/free-seo-analyzer-with-js-rendering](https://github.com/mwegter95/free-seo-analyzer-with-js-rendering)
   - Click the green **Code** button → **Download ZIP**
   - Extract the ZIP file and navigate to the folder:
     ```bash
     cd free-seo-analyzer-with-js-rendering
     ```
   - Make the scripts executable (ZIP downloads lose this):
     ```bash
     chmod +x start.sh start_and_install.sh
     ```

2. **First-time setup** — run the installation script (does everything automatically):

   ```bash
   ./start_and_install.sh
   ```

   This script will:
   - Create a Python virtual environment
   - Install all dependencies
   - Download Playwright Chromium browser (~200MB)
   - Start the server on `http://localhost:5015`

3. **Subsequent runs** — just start the server:

   ```bash
   ./start.sh
   ```

4. **Open your browser** to `http://localhost:5015`

### Manual Setup (Alternative)

If you prefer to set up manually:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Run the server
python server.py
```

Server will start at `http://localhost:5015`

## Usage

1. **Enter your website URL** (e.g., `https://example.com`)
2. **Set max pages** to crawl (default: 50, max: 200)
3. **Click "Crawl & Analyze"**
4. **Wait 15-60 seconds** while the tool:
   - Renders each page with JavaScript
   - Discovers all internal links
   - Analyzes SEO for every page
   - Aggregates site-wide statistics

### Understanding the Report

The tool provides **three views**:

#### 📊 Site Summary

- **Overall score** across all pages
- **Check pass rates** showing which SEO elements pass/fail site-wide
- **Site-wide keyword analysis** aggregated from all content
- **Worst-performing pages** needing immediate attention

#### 📄 All Pages

- List of every analyzed page with individual scores
- Click any page to see detailed breakdown
- Issues count per page
- Sorted by score (worst first)

#### ⚠️ All Issues

- Every SEO issue found across the entire site
- Grouped by category (title, meta, images, etc.)
- Shows which page each issue appears on
- Total issue count

### Click Any Page for Details

Click on any page in the list to see:

- Full breakdown of all 17 SEO checks
- Per-page keyword analysis
- Specific issues and recommendations
- Readability metrics
- Social sharing optimization

### Export Options

- **Export Full JSON**: Machine-readable format for integrations
- **Export Full Text Report**: Human-readable report for documentation

## Technology Stack

- **Backend**: Python 3 + Flask
- **Browser Automation**: Playwright (Chromium headless)
- **HTML Parsing**: BeautifulSoup4 + lxml
- **Readability Analysis**: textstat
- **Frontend**: Vanilla JavaScript (no frameworks)

## Why Local + JavaScript Rendering Matters

### The Problem with Most SEO Tools

- **Screaming Frog**: JavaScript rendering locked behind paid tier ($259/year)
- **Online Tools**: Rate limits, monthly costs, data privacy concerns
- **Basic Crawlers**: Miss client-side rendered content (React, Vue, Angular apps)

### How This Tool Solves It

✅ **Free forever** — no subscriptions or feature paywalls  
✅ **Full JS rendering** — sees your site exactly like Google does  
✅ **Unlimited crawls** — analyze as many sites as you want  
✅ **Complete privacy** — all data stays on your machine  
✅ **No rate limits** — crawl at full speed  
✅ **Open source** — modify and extend as needed

## Use Cases

- **Website Launch**: Comprehensive pre-launch SEO audit
- **Content Optimization**: Identify keyword gaps and opportunities
- **Competitor Analysis**: Crawl competitor sites for insights
- **Migration Testing**: Verify SEO after site migrations
- **Ongoing Monitoring**: Regular SEO health checks
- **Client Reports**: Generate professional SEO reports

## Tips for Best Results

- **Start Small**: Test with 10-20 pages first to verify results
- **Check robots.txt**: Ensure your site allows crawling
- **Stable Internet**: Required for external resource loading
- **Local Development**: Works on localhost too (e.g., `http://localhost:3000`)
- **Review All Issues**: Click through individual pages for detailed insights

## Troubleshooting

**First time setup vs regular startup**

- **First time**: Use `./start_and_install.sh` to install everything
- **Already installed**: Use `./start.sh` to just start the server
- **Stop server**: Press `Ctrl+C` in the terminal

**Server won't start?**

- Ensure port 5015 is available
- Check Python version: `python3 --version` (needs 3.8+)

**Crawl fails or times out?**

- Check your internet connection
- Verify the URL is accessible in a browser
- Try reducing max pages for initial test

**Missing Playwright browser?**

- Run: `playwright install chromium`

**Dependencies not found?**

- Ensure virtual environment is activated: `source venv/bin/activate`
- Reinstall: `pip install -r requirements.txt`

## Contributing

Found a bug? Have an idea for improvement? Contributions are welcome!

## License

This project is free to use, modify, and distribute.

---

**Built for SEO professionals who need powerful analysis without the paywall.** 🚀
