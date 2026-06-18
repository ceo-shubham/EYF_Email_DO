"""
Email Finder — Fast email discovery for Indian companies.
Strategy: AI domain guess → scrape contact page → mailto links → regex
"""

import re
import requests
from bs4 import BeautifulSoup
from ai_client import chat_json

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

EMAIL_RE = re.compile(r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b')

SKIP_DOMAINS = {
    "example.com", "test.com", "sentry.io", "w3.org", "schema.org",
    "google.com", "facebook.com", "twitter.com", "linkedin.com",
    "youtube.com", "instagram.com", "mca.gov.in", "zaubacorp.com",
    "tofler.in", "indiafilings.com", "cleartax.in", "indiamart.com",
    "justdial.com", "sulekha.com", "tradeindia.com",
}

SKIP_PREFIXES = {
    "noreply", "no-reply", "donotreply", "bounce",
    "mailer-daemon", "postmaster", "abuse", "spam",
    "unsubscribe", "newsletter", "billing", "careers",
}


def find_email_fast(company_name: str, domain_hint: str = "") -> str:
    """
    Find the best email for a company. Returns a single email string or "".
    Fast path: AI guess first (instant), then verify by scraping if needed.
    """
    # 1. Ask AI to guess the domain and likely email (fast, no network)
    ai_email = _ai_email_guess(company_name, domain_hint)

    # 2. If we have a domain (from hint or AI), try a quick scrape
    domain_to_scrape = ""
    if domain_hint and "." in domain_hint:
        domain_to_scrape = domain_hint
    elif ai_email and "@" in ai_email:
        domain_to_scrape = ai_email.split("@")[1]

    if domain_to_scrape:
        scraped = _scrape_domain_quick(domain_to_scrape)
        if scraped:
            return scraped

    # 3. Return AI guess as fallback
    return ai_email or ""


def _scrape_domain_quick(domain: str) -> str:
    """
    Quick scrape — only tries the homepage, 3 second timeout.
    Returns best email or "".
    """
    domain = domain.strip().lower()
    if not domain.startswith("http"):
        base_url = f"https://{domain}"
    else:
        base_url = domain
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

    emails = _extract_emails_from_url(base_url)
    return _pick_best_email(emails, domain)


def _scrape_domain(domain: str) -> str:
    """
    Full scrape — tries homepage + contact/about pages.
    Returns the best email found, or "".
    """
    domain = domain.strip().lower()
    if not domain.startswith("http"):
        base_url = f"https://{domain}"
    else:
        base_url = domain
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

    pages_to_try = [
        base_url,
        f"{base_url}/contact",
        f"{base_url}/contact-us",
        f"{base_url}/about",
        f"{base_url}/about-us",
    ]

    all_emails = []
    for url in pages_to_try[:3]:
        emails = _extract_emails_from_url(url)
        all_emails.extend(emails)
        if all_emails:
            break

    return _pick_best_email(all_emails, domain)


def _extract_emails_from_url(url: str) -> list:
    """Fetch a URL and extract all email addresses."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=4, allow_redirects=True)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # mailto links first (most reliable)
        emails = []
        for link in soup.find_all("a", href=re.compile(r'^mailto:', re.I)):
            raw = link["href"].replace("mailto:", "").split("?")[0].strip().lower()
            if raw and "@" in raw:
                emails.append(raw)

        # Regex on visible text
        text = soup.get_text(" ")
        regex_emails = [e.lower() for e in EMAIL_RE.findall(text)]
        emails.extend(regex_emails)

        return list(set(emails))

    except Exception:
        return []


def _pick_best_email(emails: list, domain: str = "") -> str:
    """
    From a list of emails, pick the most relevant business contact email.
    Prefers: info@ > contact@ > hello@ > admin@ > sales@ > others
    Filters out junk.
    """
    clean = []
    for email in emails:
        email = email.lower().strip()
        if not email or "@" not in email:
            continue
        parts = email.split("@")
        if len(parts) != 2:
            continue
        prefix, dom = parts

        # Skip junk domains
        if any(skip in dom for skip in SKIP_DOMAINS):
            continue
        # Skip junk prefixes
        if any(prefix.startswith(skip) for skip in SKIP_PREFIXES):
            continue
        # Skip very long emails
        if len(email) > 80:
            continue
        # Skip emails with numbers only in prefix (likely auto-generated)
        if re.match(r'^\d+$', prefix):
            continue

        clean.append(email)

    if not clean:
        return ""

    # If we know the domain, prefer emails from that domain
    if domain:
        domain_emails = [e for e in clean if domain in e]
        if domain_emails:
            clean = domain_emails

    # Priority order
    priority = ["info@", "contact@", "hello@", "enquiry@", "enquiries@",
                "admin@", "sales@", "support@", "office@", "mail@"]
    for p in priority:
        for e in clean:
            if e.startswith(p):
                return e

    # Return first clean email
    return clean[0]


def _ai_email_guess(company_name: str, domain_hint: str = "") -> str:
    """
    Ask AI to guess the most likely email for a company.
    Returns a single email string.
    """
    prompt = f"""You are a business research assistant. Guess the most likely official contact email for this Indian company:

Company: {company_name}
Known domain hint: {domain_hint if domain_hint else "unknown"}

Rules:
- Guess the most likely domain (e.g. "Sharma Foods Pvt Ltd" → "sharmafoods.com" or "sharmafoods.in")
- Guess the most likely email prefix (info@, contact@, hello@, etc.)
- For small Indian businesses, .in and .com are most common
- Return ONLY JSON: {{"email": "info@example.com", "confidence": "high/medium/low"}}
- If you truly cannot guess, return {{"email": "", "confidence": "none"}}"""

    try:
        result = chat_json(prompt, temperature=0.1, max_tokens=100)
        email = result.get("email", "").lower().strip()
        confidence = result.get("confidence", "low")

        # Validate format
        if email and "@" in email and "." in email.split("@")[1]:
            if confidence in ("high", "medium"):
                return email
    except Exception:
        pass

    return ""


if __name__ == "__main__":
    test_companies = [
        ("Sharma Foods Pvt Ltd", "sharmafoods.com"),
        ("TechNova Solutions", ""),
        ("Green Earth Organics", ""),
    ]
    for name, hint in test_companies:
        email = find_email_fast(name, hint)
        print(f"{name}: {email or 'NOT FOUND'}")
