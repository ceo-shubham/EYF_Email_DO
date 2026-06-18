# 🏢 Company Outreach Master — EaseYourFiling

An AI-powered system that finds Indian companies, looks up their CIN from MCA, finds their email addresses, and sends personalized outreach emails.

## 🚀 How to Run

```bash
streamlit run app.py
```

Opens at: **http://localhost:8501**

## 🔄 Pipeline Flow

```
Company Name → CIN (MCA) → Email (AI + Scraping) → Send Email (Resend)
```

1. **Find CIN** — Searches Zaubacorp, Tofler, then uses AI (Groq/OpenRouter) as fallback
2. **Find Email** — AI suggests likely emails + scrapes company website
3. **Send Email** — Resend API sends personalized AI-written outreach

## 📁 Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit web UI |
| `pipeline.py` | Main orchestration logic |
| `mca_lookup.py` | CIN lookup from MCA data |
| `email_finder.py` | AI-powered email discovery |
| `email_sender.py` | Resend email sending |
| `ai_client.py` | Smart AI fallback (Groq → OpenRouter → Anthropic → OpenAI) |

## 🔑 API Keys (.env)

```
ai1=<OpenRouter key>
ai2=<Groq key>          ← Primary AI (fast, free)
ai3=<OpenAI key>        ← Fallback
ai4=<Anthropic key>     ← Fallback
RESEND_API_KEY=<key>    ← Email sending
```

## ⚠️ Important Notes

- **Resend free tier**: 100 emails/day, must verify sender domain
- **Email sending**: Set "From Email" to a verified domain in Resend dashboard
- **CIN accuracy**: AI knowledge is used for well-known companies; always verify on mca.gov.in for smaller companies
- Results auto-save to `results.csv` after each run
