"""
AI Battle — All 4 AI models compete to write the best outreach email.
A judge AI picks the winner. Each company gets a unique personalized message.
"""

import os
import json
import asyncio
import concurrent.futures
from dotenv import load_dotenv

load_dotenv()

# ── EaseYourFiling service context ────────────────────────────────────────
EYOF_CONTEXT = """
EaseYourFiling (easeyourfiling.com) is an Indian compliance services firm offering:
- Private Limited Company registration (7-10 days, fully online)
- One Person Company (OPC) registration
- LLP and Partnership registration
- GST registration (3 days) and monthly/quarterly filing
- ROC / MCA annual compliance and annual returns
- Trademark registration and brand protection
- FSSAI food license for food businesses
- Startup India and MSME/Udyam registration
- Company amendments (name change, director change, address change)
- Revival of struck-off companies
- Income tax filing for companies and directors
- Section 8 / NGO registration
Contact: official@easeyourfiling.com | +91 9065734856 | easeyourfiling.com
"""


def _analyze_company_needs(company_name: str, cin: str, industry: str, state: str) -> str:
    """
    Based on company info, determine what EaseYourFiling services they likely need.
    Returns a short analysis string used to personalize the email.
    """
    cin_year = ""
    if cin and len(cin) >= 11:
        try:
            cin_year = int(cin[7:11])
            current_year = 2026
            age_years = current_year - cin_year
        except Exception:
            age_years = 0
    else:
        age_years = 0

    needs = []

    if age_years <= 2:
        needs.append("GST registration (newly registered companies often need this)")
        needs.append("Startup India / MSME registration for government benefits")
        needs.append("ROC annual compliance (first filing due soon)")
    elif age_years <= 5:
        needs.append("ROC annual compliance and MCA filings")
        needs.append("Trademark registration to protect their brand")
        needs.append("GST return filing support")
    else:
        needs.append("ROC annual compliance")
        needs.append("Income tax filing")
        needs.append("Trademark registration if not done yet")

    industry_lower = (industry or "").lower()
    if any(w in industry_lower for w in ["food", "restaurant", "cafe", "bakery", "catering", "fssai"]):
        needs.insert(0, "FSSAI food license (mandatory for food businesses)")
    if any(w in industry_lower for w in ["tech", "software", "it", "startup", "saas"]):
        needs.insert(0, "Startup India registration for tax benefits and funding eligibility")
    if any(w in industry_lower for w in ["retail", "trade", "shop", "store", "ecommerce"]):
        needs.insert(0, "GST registration and filing (mandatory for retail/ecommerce)")

    return "; ".join(needs[:3])


def _write_email_groq(company_name: str, needs: str, cin: str) -> dict:
    """Groq — Llama 3.3 70B"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("ai2"),
            base_url="https://api.groq.com/openai/v1",
        )
        prompt = _build_prompt(company_name, needs, cin, "Groq Llama 3.3")
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=500,
        )
        return json.loads(_clean_json(resp.choices[0].message.content))
    except Exception as e:
        return {"subject": "", "body": "", "error": str(e), "model": "groq"}


def _write_email_openrouter(company_name: str, needs: str, cin: str) -> dict:
    """OpenRouter — Mistral or Llama via OpenRouter"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("ai1"),
            base_url="https://openrouter.ai/api/v1",
        )
        prompt = _build_prompt(company_name, needs, cin, "OpenRouter Mistral")
        resp = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=500,
        )
        return json.loads(_clean_json(resp.choices[0].message.content))
    except Exception as e:
        return {"subject": "", "body": "", "error": str(e), "model": "openrouter"}


def _write_email_anthropic(company_name: str, needs: str, cin: str) -> dict:
    """Anthropic Claude Haiku"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ai4"))
        prompt = _build_prompt(company_name, needs, cin, "Claude Haiku")
        msg = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(_clean_json(msg.content[0].text))
    except Exception as e:
        return {"subject": "", "body": "", "error": str(e), "model": "anthropic"}


def _write_email_openai(company_name: str, needs: str, cin: str) -> dict:
    """OpenAI GPT-4o (fallback — may have quota issues)"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("ai3"))
        prompt = _build_prompt(company_name, needs, cin, "GPT-4o")
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=500,
        )
        return json.loads(_clean_json(resp.choices[0].message.content))
    except Exception as e:
        return {"subject": "", "body": "", "error": str(e), "model": "openai"}


def _build_prompt(company_name: str, needs: str, cin: str, model_name: str) -> str:
    return f"""You are writing a cold outreach email for EaseYourFiling.

{EYOF_CONTEXT}

Target Company: {company_name}
CIN: {cin}
Likely needs: {needs}

Write a SHORT (under 100 words), warm, professional outreach email that:
1. Mentions the company by name
2. Specifically references what they likely need ({needs.split(';')[0].strip()})
3. Offers a free consultation
4. Signs off from EaseYourFiling with official@easeyourfiling.com and +91 9065734856
5. Does NOT sound like spam or a template

Return ONLY valid JSON (no markdown):
{{"subject": "compelling subject line", "body": "full email body text"}}"""


def _judge_emails(candidates: list, company_name: str) -> dict:
    """
    Use Groq (fastest) as judge to pick the best email from candidates.
    Returns the winning email dict with 'winner_model' added.
    """
    # Filter out failed candidates
    valid = [c for c in candidates if c.get("subject") and c.get("body") and not c.get("error")]

    if not valid:
        # All failed — return a hardcoded fallback
        return _fallback_email(company_name)

    if len(valid) == 1:
        return valid[0]

    # Build judge prompt
    options = "\n\n".join([
        f"OPTION {i+1} (Model: {c.get('model','?')}):\nSubject: {c['subject']}\nBody: {c['body']}"
        for i, c in enumerate(valid)
    ])

    judge_prompt = f"""You are judging cold outreach emails for a compliance services company.

Company being targeted: {company_name}

{options}

Pick the BEST email based on:
- Personalization (mentions the company specifically)
- Conciseness (under 100 words is better)
- Professional but warm tone
- Clear value proposition
- Not spammy

Respond with ONLY JSON: {{"winner": 1}} (use the option number, 1-indexed)"""

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("ai2"),
            base_url="https://api.groq.com/openai/v1",
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": judge_prompt}],
            temperature=0,
            max_tokens=50,
        )
        result = json.loads(_clean_json(resp.choices[0].message.content))
        winner_idx = int(result.get("winner", 1)) - 1
        winner_idx = max(0, min(winner_idx, len(valid) - 1))
        winner = valid[winner_idx].copy()
        winner["winner_model"] = valid[winner_idx].get("model", "unknown")
        return winner
    except Exception:
        # Judge failed — just return first valid
        v = valid[0].copy()
        v["winner_model"] = v.get("model", "unknown")
        return v


def _fallback_email(company_name: str) -> dict:
    return {
        "subject": f"Compliance Support for {company_name} — EaseYourFiling",
        "body": (
            f"Dear Team at {company_name},\n\n"
            "I'm reaching out from EaseYourFiling — we help Indian businesses with "
            "company registration, GST, ROC compliance, Trademark, and all MCA filings.\n\n"
            "We'd love to offer you a free consultation to see how we can help.\n\n"
            "Reply or call/WhatsApp: +91 9065734856\n\n"
            "Warm regards,\nTeam EaseYourFiling\n"
            "official@easeyourfiling.com | easeyourfiling.com"
        ),
        "winner_model": "fallback",
    }


def _clean_json(text: str) -> str:
    """Strip markdown code fences from AI response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return text


def generate_best_email(
    company_name: str,
    cin: str = "",
    industry: str = "",
    state: str = "",
) -> dict:
    """
    Run all 4 AI models in parallel, judge picks the best.
    Returns: {subject, body, winner_model, needs_analysis}
    """
    needs = _analyze_company_needs(company_name, cin, industry, state)

    writers = [
        (_write_email_groq,       "groq"),
        (_write_email_openrouter, "openrouter"),
        # Anthropic skipped — credits exhausted
        # (_write_email_anthropic,  "anthropic"),
        # OpenAI skipped — quota exceeded
        # (_write_email_openai,     "openai"),
    ]

    candidates = []

    # Run all writers in parallel threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fn, company_name, needs, cin): model
            for fn, model in writers
        }
        for future in concurrent.futures.as_completed(futures, timeout=30):
            model = futures[future]
            try:
                result = future.result()
                result["model"] = model
                candidates.append(result)
            except Exception as e:
                candidates.append({"subject": "", "body": "", "error": str(e), "model": model})

    # Judge picks the best
    winner = _judge_emails(candidates, company_name)
    if "winner_model" not in winner:
        winner["winner_model"] = winner.get("model", "unknown")
    winner["needs_analysis"] = needs
    winner["all_candidates"] = [
        {"model": c.get("model"), "subject": c.get("subject", ""), "error": c.get("error", "")}
        for c in candidates
    ]

    return winner


if __name__ == "__main__":
    result = generate_best_email(
        company_name="Sharma Foods Pvt Ltd",
        cin="U15100MH2022PTC123456",
        industry="Food & Beverage",
        state="Maharashtra",
    )
    print(f"Winner: {result['winner_model']}")
    print(f"Subject: {result['subject']}")
    print(f"Body:\n{result['body']}")
    print(f"\nNeeds: {result['needs_analysis']}")
