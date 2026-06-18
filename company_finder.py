"""
Company Finder — Gets REAL Indian companies using Playwright on Zaubacorp.
Playwright (real browser) bypasses bot detection that blocks plain HTTP requests.
Tofler is used only for fetching individual company emails.
"""

import re
import os
import json
import asyncio
from ai_client import chat_json

# Only match UNLISTED companies (CIN starts with 'U', not 'L')
CIN_RE = re.compile(r'\b(U\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b')
# Also keep a broader pattern for filtering purposes
CIN_RE_ALL = re.compile(r'\b([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b')

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── State to ROC mapping ───────────────────────────────────────────────────
STATE_TO_ROC = {
    "All India": "",
    "Andhra Pradesh": "RoC-Vijayawada",
    "Arunachal Pradesh": "RoC-Shillong",
    "Assam": "RoC-Shillong",
    "Bihar": "RoC-Patna",
    "Chhattisgarh": "RoC-Chhattisgarh",
    "Goa": "RoC-Goa",
    "Gujarat": "RoC-Ahmedabad",
    "Haryana": "RoC-Delhi",
    "Himachal Pradesh": "RoC-HimachalPradesh",
    "Jharkhand": "RoC-Jharkhand",
    "Karnataka": "RoC-Bangalore",
    "Kerala": "RoC-Ernakulam",
    "Madhya Pradesh": "RoC-Gwalior",
    "Maharashtra": "RoC-Mumbai",
    "Manipur": "RoC-Shillong",
    "Meghalaya": "RoC-Shillong",
    "Mizoram": "RoC-Shillong",
    "Nagaland": "RoC-Shillong",
    "Odisha": "RoC-Cuttack",
    "Punjab": "RoC-Chandigarh",
    "Rajasthan": "RoC-Jaipur",
    "Sikkim": "RoC-Shillong",
    "Tamil Nadu": "RoC-Chennai",
    "Telangana": "RoC-Hyderabad",
    "Tripura": "RoC-Shillong",
    "Uttar Pradesh": "RoC-Kanpur",
    "Uttarakhand": "RoC-Uttarakhand",
    "West Bengal": "RoC-Kolkata",
    "Delhi": "RoC-Delhi",
    "Chandigarh": "RoC-Chandigarh",
    "Puducherry": "RoC-Pondicherry",
    "Jammu and Kashmir": "RoC-Jammu",
    "Ladakh": "RoC-Jammu",
    "Andaman and Nicobar Islands": "RoC-ANDAMAN",
    "Lakshadweep": "RoC-Ernakulam",
    "Dadra and Nagar Haveli and Daman and Diu": "RoC-Ahmedabad",
}

# ── Company type → URL prefix mapping ──────────────────────────────────────
COMPANY_TYPE_TO_URL = {
    "Private Limited (Pvt Ltd)":           "companytype-PTC",
    "Public Limited":                      "companytype-PLC",
    "One Person Company (OPC)":            "companytype-OPC",
    "Limited Liability Partnership (LLP)": "companytype-LLP",
    "Section 8 / NGO":                     "companytype-NPL",
    "Producer Company":                    "companytype-PTC",
    "Nidhi Company":                       "companytype-PTC",
    "Foreign Company":                     "companytype-FTC",
    "All Types":                           "",
}

# ── Standard Company type information map for local filtering ──────────────
COMPANY_TYPE_MAP = {
    "All Types":                           {"cin_code": None},
    "Private Limited (Pvt Ltd)":           {"cin_code": "PTC"},
    "Public Limited":                      {"cin_code": "PLC"},
    "One Person Company (OPC)":            {"cin_code": "OPC"},
    "Limited Liability Partnership (LLP)": {"cin_code": "AAC"},
    "Section 8 / NGO":                     {"cin_code": "NPL"},
    "Producer Company":                    {"cin_code": "PCL"},
    "Nidhi Company":                       {"cin_code": "NLC"},
    "Foreign Company":                     {"cin_code": "FTC"},
    "Partnership Firm":                    {"cin_code": None},
}


async def _scrape_zaubacorp_async(roc_slug: str, type_slug: str, target: int) -> list:
    """
    Use Playwright to scrape Zaubacorp company listings.
    Uses direct page clicks to avoid 403 blocks.
    """
    from playwright.async_api import async_playwright

    all_companies = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=BROWSER_UA,
            viewport={"width": 1280, "height": 900},
        )
        await context.route(
            "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf,ico,mp4,webp}",
            lambda r: r.abort()
        )
        page = await context.new_page()

        # Build initial URL
        if roc_slug:
            url = f"https://www.zaubacorp.com/companies-list/roc-{roc_slug}-company.html"
        elif type_slug:
            url = f"https://www.zaubacorp.com/companies-list/{type_slug}-company.html"
        else:
            url = "https://www.zaubacorp.com/companies-list"

        try:
            print(f"[ZaubacorpScraper] Navigating to initial page: {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if not resp or resp.status != 200:
                print(f"[ZaubacorpScraper] Failed to load initial page: {resp.status if resp else 'No response'}")
                await browser.close()
                return []
        except Exception as e:
            print(f"[ZaubacorpScraper] Initial navigation failed: {e}")
            await browser.close()
            return []

        page_num = 1
        while len(all_companies) < target and page_num <= 10:
            await page.wait_for_timeout(1000)

            # Extract company links
            links = await page.query_selector_all("a[href]")
            page_companies = []
            for link in links:
                href = await link.get_attribute("href") or ""
                cin_match = CIN_RE_ALL.search(href)
                if not cin_match:
                    continue
                cin  = cin_match.group(1)
                name = (await link.inner_text()).strip()
                if not name or len(name) < 3 or name == cin:
                    continue
                
                # Build Tofler slug from name
                slug = name.lower()
                slug = re.sub(r'[^a-z0-9\s]', '', slug)
                slug = re.sub(r'\s+', '-', slug.strip())

                page_companies.append({
                    "name": name,
                    "cin": cin,
                    "slug": slug,
                    "state": roc_slug.replace("RoC-", "").replace("ROC-", "").title() if roc_slug else "",
                    "industry": "",
                    "domain_hint": "",
                })

            # Filter out listed companies (L prefix)
            page_companies = [
                c for c in page_companies
                if c["cin"].startswith("U") or "-" in c["cin"]  # Unlisted only
            ]

            if not page_companies:
                print(f"[ZaubacorpScraper] No companies found on page {page_num}")
                break

            print(f"[ZaubacorpScraper] Scraped {len(page_companies)} companies from page {page_num}")
            all_companies.extend(page_companies)

            if len(all_companies) >= target:
                break

            # Try to paginate to page_num + 1
            next_page = page_num + 1
            try:
                page_link = await page.query_selector(f'a[href*="/p-{next_page}-"]')
                if not page_link:
                    print(f"[ZaubacorpScraper] No pagination link found for page {next_page}")
                    break
                
                print(f"[ZaubacorpScraper] Clicking link to page {next_page}...")
                await page_link.click()
                page_num = next_page
            except Exception as e:
                print(f"[ZaubacorpScraper] Failed to navigate to page {next_page}: {e}")
                break

        await browser.close()

    # Deduplicate
    seen = set()
    unique = []
    for c in all_companies:
        if c["cin"] not in seen:
            seen.add(c["cin"])
            unique.append(c)

    return unique


def find_target_companies(
    target_description: str,
    state: str = "All India",
    count: int = 100,
    company_type: str = "All Types",
) -> list:
    """
    Get companies for outreach.
    Primary: Zaubacorp via Playwright (real companies with CINs).
    Fallback: AI-generated names (fast, always works).
    """
    roc_slug = STATE_TO_ROC.get(state, "")
    type_slug = COMPANY_TYPE_TO_URL.get(company_type, "")
    
    type_info = COMPANY_TYPE_MAP.get(company_type, COMPANY_TYPE_MAP["All Types"])
    cin_code = type_info.get("cin_code")

    # PRIMARY: Zaubacorp listing scraping — gets REAL companies with REAL CINs
    all_companies = []
    try:
        all_companies = asyncio.run(
            _scrape_zaubacorp_async(roc_slug, type_slug, count * 2)
        )
        print(f"[CompanyFinder] Zaubacorp returned {len(all_companies)} real companies")
    except Exception as e:
        print(f"[CompanyFinder] Zaubacorp failed ({e}), will use AI fallback")
        all_companies = []

    # Deduplicate by CIN/Name
    seen = set()
    unique = []
    for c in all_companies:
        key = c.get("cin") or c.get("name", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(c)

    # Filter by company type locally
    if cin_code and unique:
        filtered = []
        for c in unique:
            cin = c.get("cin", "")
            if len(cin) == 21 and cin[14:17] == cin_code:
                filtered.append(c)
            elif cin_code == "AAC" and "LLP" in cin.upper():
                filtered.append(c)
        if len(filtered) >= count // 2:
            unique = filtered

    # Always filter out listed companies and PLC (unless user specifically asked for PLC)
    unique = [
        c for c in unique
        if not c.get("cin", "").startswith("L")  # No listed companies
        and (len(c.get("cin", "")) < 17 or c.get("cin", "")[14:17] != "PLC")  # No PLC
    ]

    # If Zaubacorp gave enough, return
    if len(unique) >= count:
        return unique[:count]

    # Fallback: AI generates company names (always works, fast)
    shortfall = count - len(unique)
    ai_extra = _ai_fallback(target_description, state, shortfall, company_type)
    unique.extend(ai_extra)
    return unique[:count]


def _ai_fallback(target_description: str, state: str, count: int, company_type: str = "All Types") -> list:
    """
    AI generates company names using available models.
    Uses the fastest available model with smart batching.
    """
    import concurrent.futures

    state_str = f"in {state}" if state != "All India" else "across India"

    type_suffix_map = {
        "Private Limited (Pvt Ltd)":           "Private Limited",
        "Public Limited":                      "Limited",
        "One Person Company (OPC)":            "OPC Private Limited",
        "Limited Liability Partnership (LLP)": "LLP",
        "Section 8 / NGO":                     "Foundation",
        "All Types":                           "Pvt Ltd",
    }
    type_suffix = type_suffix_map.get(company_type, "Pvt Ltd")

    # Use different state seeds for variety
    state_seeds = [
        "Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "Gujarat",
        "Telangana", "Uttar Pradesh", "West Bengal", "Rajasthan", "Haryana",
        "Kerala", "Punjab", "Madhya Pradesh", "Bihar", "Odisha",
    ] if state == "All India" else [state] * 15

    def _call_groq(batch_count: int, state_seed: str) -> list:
        prompt = f"""Generate exactly {batch_count} realistic Indian UNLISTED PRIVATE LIMITED company names in {state_seed}.
IMPORTANT: Only generate Private Limited Companies (Pvt Ltd / PTC). Do NOT generate any Public Limited Companies (PLC) or Listed companies.
Company type must end with: "{type_suffix}"
These companies need: {target_description}

Return ONLY a valid JSON array (no markdown):
[{{"name": "Sharma Foods {type_suffix}", "industry": "Food", "state": "{state_seed}", "cin": "", "slug": "", "domain_hint": ""}}]"""
        for attempt in range(3):  # retry up to 3 times
            try:
                from openai import OpenAI
                client = OpenAI(api_key=os.getenv("ai2"), base_url="https://api.groq.com/openai/v1")
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.9, max_tokens=4000,
                )
                raw = resp.choices[0].message.content.strip()
                if raw.startswith("```"):
                    raw = "\n".join(raw.split("\n")[1:-1])
                result = json.loads(raw)
                return result if isinstance(result, list) else []
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    import time as _t; _t.sleep(10 * (attempt + 1))  # wait 10s, 20s
                else:
                    return []
        return []

    def _call_anthropic(batch_count: int, state_seed: str) -> list:
        prompt = f"""Generate exactly {batch_count} realistic Indian UNLISTED PRIVATE LIMITED company names in {state_seed}.
IMPORTANT: Only generate Private Limited Companies (Pvt Ltd / PTC). Do NOT generate any Public Limited Companies (PLC) or Listed companies.
Company type must end with: "{type_suffix}"
These companies need: {target_description}

Return ONLY a valid JSON array (no markdown):
[{{"name": "Sharma Foods {type_suffix}", "industry": "Food", "state": "{state_seed}", "cin": "", "slug": "", "domain_hint": ""}}]"""
        try:
            import anthropic as _ant
            client = _ant.Anthropic(api_key=os.getenv("ai4"))
            msg = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    def _call_openrouter(batch_count: int, state_seed: str) -> list:
        prompt = f"""Generate exactly {batch_count} realistic Indian UNLISTED PRIVATE LIMITED company names in {state_seed}.
IMPORTANT: Only generate Private Limited Companies (Pvt Ltd / PTC). Do NOT generate any Public Limited Companies (PLC) or Listed companies.
Company type must end with: "{type_suffix}"
These companies need: {target_description}

Return ONLY a valid JSON array (no markdown):
[{{"name": "Sharma Foods {type_suffix}", "industry": "Food", "state": "{state_seed}", "cin": "", "slug": "", "domain_hint": ""}}]"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("ai1"), base_url="https://openrouter.ai/api/v1")
            resp = client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9, max_tokens=4000,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:-1])
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except Exception:
            return []

    # Rotate only working models: groq and openrouter
    # Anthropic is skipped (credits exhausted)
    batch_per_task = 50
    working_models = [_call_groq, _call_openrouter]
    tasks = []
    for i in range((count + batch_per_task - 1) // batch_per_task):
        state_seed = state_seeds[i % len(state_seeds)]
        fn = working_models[i % len(working_models)]
        tasks.append((fn, batch_per_task, state_seed))

    all_companies = []

    # Run tasks in parallel batches of 3 (one per model simultaneously)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            ex.submit(fn, n, s): (fn.__name__, s)
            for fn, n, s in tasks
        }
        for future in concurrent.futures.as_completed(futures, timeout=120):
            try:
                batch = future.result()
                all_companies.extend(batch)
                if len(all_companies) >= count:
                    break
            except Exception:
                pass

    # Deduplicate by name
    seen = set()
    unique = []
    for c in all_companies:
        name = c.get("name", "").strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(c)

    return unique[:count]


if __name__ == "__main__":
    import time
    print("Testing 50 Private Limited companies from Maharashtra via Zaubacorp...")
    t = time.time()
    companies = find_target_companies(
        "Newly registered startups",
        state="Maharashtra",
        count=50,
        company_type="Private Limited (Pvt Ltd)",
    )
    elapsed = time.time() - t
    ptc = [c for c in companies if len(c.get("cin","")) == 21 and c["cin"][14:17] == "PTC"]
    print(f"Got {len(companies)} in {elapsed:.1f}s | PTC: {len(ptc)}")
    for c in companies[:5]:
        print(f"  {c['name']} | {c['cin']}")
