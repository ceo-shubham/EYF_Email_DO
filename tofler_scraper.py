"""
Tofler Scraper — Gets real MCA-registered company email from Tofler.

Strategy:
1. AI gives us company name + domain hint
2. We get the CIN via AI knowledge (Groq)
3. We build the Tofler URL: tofler.in/{slug}/company/{CIN}
4. Playwright fetches the page and extracts "Company Email" from Registered Details

Tofler shows the official MCA-registered email publicly — no login needed.
"""

import re
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from ai_client import chat_json

# Only match UNLISTED companies (CIN starts with 'U', not 'L')
CIN_RE   = re.compile(r'\b(U\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b')
CIN_RE_ALL = re.compile(r'\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b')
EMAIL_RE = re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b')

SKIP_EMAILS = {
    "support@tofler.in", "tofler@tofler.in",
    "example@example.com", "test@test.com",
}
SKIP_DOMAINS = {
    "tofler.in", "w3.org", "schema.org", "google.com",
    "facebook.com", "twitter.com", "linkedin.com", "youtube.com",
}


def _get_cin_and_slug(company_name: str) -> tuple:
    """
    Use AI to get the CIN for a company.
    Slug is always derived from the company name (Tofler pattern).
    Returns (cin, slug)
    """
    # Always generate slug from name — Tofler uses this exact pattern
    slug = company_name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s\-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = slug.strip('-')

    prompt = f"""You are an expert on Indian MCA company data.

What is the CIN (Corporate Identification Number) for: "{company_name}"?

CIN format: L or U + 5 digits + 2-letter state code + 4-digit year + 3-letter type + 6 digits
Example: U40100TN2010PTC075961

Return ONLY JSON: {{"cin": "ACTUAL_CIN"}}
If unknown, return: {{"cin": ""}}"""

    try:
        result = chat_json(prompt, temperature=0, max_tokens=80)
        cin = result.get("cin", "").strip().upper()
        if cin and CIN_RE.match(cin):
            return cin, slug
    except Exception:
        pass

    return "", slug


def _extract_email_from_text(page_text: str) -> str:
    """
    Extract the MCA-registered email from Tofler page text.
    Tofler shows it under 'Registered Details' → 'Company Email'.
    """
    # Strategy 1: Find text right after "Company Email" label
    lower = page_text.lower()
    idx = lower.find("company email")
    if idx != -1:
        snippet = page_text[idx: idx + 300]
        emails = EMAIL_RE.findall(snippet)
        for e in emails:
            e = e.lower().strip()
            if _is_valid_email(e):
                return e

    # Strategy 2: Find text after "Registered Details"
    idx = lower.find("registered details")
    if idx != -1:
        snippet = page_text[idx: idx + 600]
        emails = EMAIL_RE.findall(snippet)
        for e in emails:
            e = e.lower().strip()
            if _is_valid_email(e):
                return e

    # Strategy 3: Look for any line containing "email" keyword and email pattern
    lines = page_text.splitlines()
    for line in lines:
        if "email" in line.lower():
            emails = EMAIL_RE.findall(line)
            for e in emails:
                e = e.lower().strip()
                if _is_valid_email(e):
                    return e

    # Strategy 4: All emails on page, skip junk
    all_emails = EMAIL_RE.findall(page_text)
    for e in all_emails:
        e = e.lower().strip()
        if _is_valid_email(e):
            return e

    return ""


def _is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.split("@")[1]
    if email in SKIP_EMAILS:
        return False
    if any(s in domain for s in SKIP_DOMAINS):
        return False
    if len(email) > 100:
        return False
    return True


async def _fetch_tofler_page(page, cin: str, slug: str, company_name: str = "") -> tuple:
    """
    Fetch the Tofler company page and return its text content.
    Strategy:
      1. Try direct URL with CIN + slug
      2. Try direct URL with CIN only
      3. FALLBACK: Search Tofler by company name, follow first result
    """
    urls_to_try = []

    if cin and slug:
        urls_to_try.append(f"https://www.tofler.in/{slug}/company/{cin}")
    if cin:
        urls_to_try.append(f"https://www.tofler.in/company/company/{cin}")

    # Try direct URLs first
    for url in urls_to_try:
        try:
            print(f"[ToflerScraper] Trying URL: {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp and resp.status == 200:
                # Wait for JS to render the Registered Details section
                try:
                    await page.wait_for_function(
                        "document.body.innerText.includes('@')",
                        timeout=8000
                    )
                except Exception:
                    await page.wait_for_timeout(3000)
                print(f"[ToflerScraper] Successfully loaded page: {url}")

                text = await page.inner_text("body")
                if "registered details" in text.lower() or "company email" in text.lower() or "@" in text:
                    return text, url
        except Exception:
            continue

    # FALLBACK: Search Tofler by company name
    search_name = company_name or slug.replace("-", " ").title()
    if search_name:
        try:
            print(f"[ToflerScraper] Searching for: {search_name}")
            search_url = f"https://www.tofler.in/search?q={search_name.replace(' ', '+')}"
            resp = await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
            if resp and resp.status == 200:
                await page.wait_for_selector("a[href*='/company/']", timeout=5000)

                # Find the first company link in search results
                result_links = await page.query_selector_all("a[href*='/company/']")
                for link in result_links:
                    href = await link.get_attribute("href") or ""
                    # Skip non-company links (like navigation, ads)
                    if "/company/" not in href:
                        continue
                    # Check if it looks like a real company page URL
                    if CIN_RE_ALL.search(href):
                        # Build full URL if relative
                        if href.startswith("/"):
                            href = f"https://www.tofler.in{href}"

                        try:
                            print(f"[ToflerScraper] Navigating to search result: {href}")
                            resp2 = await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                            if resp2 and resp2.status == 200:
                                try:
                                    await page.wait_for_function(
                                        "document.body.innerText.includes('@')",
                                        timeout=8000
                                    )
                                except Exception:
                                    await page.wait_for_timeout(3000)

                                text = await page.inner_text("body")
                                if "registered details" in text.lower() or "company email" in text.lower() or "@" in text:
                                    print(f"[ToflerScraper] Successfully loaded search result page.")
                                    return text, href
                        except Exception as e:
                            print(f"[ToflerScraper] Error navigating to search result: {e}")
                        break  # Only try first matching link
        except Exception as e:
            print(f"[ToflerScraper] Search failed: {e}")

    return "", ""


async def _scrape_one_async(page, company_name: str, cin: str = "", slug: str = "") -> dict:
    """Scrape one company from Tofler."""
    result = {
        "company_name": company_name,
        "cin": cin,
        "email": "",
        "state": "",
        "tofler_url": "",
        "status": "not_found",
    }

    # Step 1: Get CIN + slug — use provided values first, then AI
    if not cin or not slug:
        ai_cin, ai_slug = _get_cin_and_slug(company_name)
        if not cin:
            cin = ai_cin
            result["cin"] = cin
        if not slug:
            slug = ai_slug

    if not slug:
        # Generate slug from name as last resort
        slug = company_name.lower().strip()
        slug = re.sub(r'[^a-z0-9\s\-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)

    # Step 2: Fetch Tofler page (tries direct URL first, then search fallback)
    page_text, used_url = await _fetch_tofler_page(page, cin, slug, company_name)
    result["tofler_url"] = used_url

    # Extract real CIN from URL if search fallback was used
    if used_url:
        url_cin_match = CIN_RE_ALL.search(used_url)
        if url_cin_match:
            real_cin = url_cin_match.group(1)
            if real_cin != cin:
                result["cin"] = real_cin
                cin = real_cin
    # Fallback: try to extract CIN from page text if still missing or empty
    if not cin:
        if page_text:
            cin_match = CIN_RE_ALL.search(page_text)
            if cin_match:
                result["cin"] = cin_match.group(1)
                cin = result["cin"]

    if not page_text:
        result["status"] = "page_not_found"
        return result

    # Step 3: Extract email
    email = _extract_email_from_text(page_text)
    if email:
        result["email"] = email
        result["status"] = "found"
    else:
        result["status"] = "no_email_on_page"

    # Extract actual company name from H1
    try:
        h1 = await page.query_selector("h1")
        if h1:
            name = await h1.inner_text()
            if name and len(name) > 3:
                result["company_name"] = name.strip()
    except Exception:
        pass

    return result


async def scrape_companies_async(
    company_names: list,
    on_progress=None,
    headless: bool = True,
) -> list:
    """
    Scrape Tofler for a list of companies.
    Each item can be a string (name only) or dict with {name, cin, slug}.
    """
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
        )

        # Block images/fonts/media to speed up
        await context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,ico,mp4,webp}",
            lambda r: r.abort()
        )

        page = await context.new_page()

        for i, item in enumerate(company_names):
            # Accept both string and dict
            if isinstance(item, dict):
                name = item.get("name", "")
                cin  = item.get("cin", "")
                slug = item.get("slug", "")
            else:
                name = item
                cin  = ""
                slug = ""

            r = await _scrape_one_async(page, name, cin, slug)
            results.append(r)

            if on_progress:
                on_progress(i + 1, len(company_names), r)

            await asyncio.sleep(1.2)

        await browser.close()

    return results


def scrape_companies(
    company_names: list,
    on_progress=None,
    headless: bool = True,
) -> list:
    """Sync wrapper."""
    return asyncio.run(
        scrape_companies_async(company_names, on_progress, headless)
    )


if __name__ == "__main__":
    def prog(i, total, r):
        status = "✅" if r["email"] else "❌"
        print(f"  {status} [{i}/{total}] {r['company_name']}: {r['email'] or r['status']}")

    results = scrape_companies(
        ["Zoho Corporation Private Limited", "Tata Electronics Private Limited"],
        on_progress=prog,
        headless=False,
    )
    print("\nFinal:")
    for r in results:
        print(f"  {r['company_name']} | {r['cin']} | {r['email']}")
