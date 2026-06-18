"""
EaseYourFiling — Smart Outreach System
AI generates targets → Tofler scrapes real emails → AI battle writes best message → Resend sends
"""

import streamlit as st
import pandas as pd
import os, json, time, io
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="EaseYourFiling Outreach",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
    #MainMenu, footer, header {visibility: hidden;}
    .block-container {padding-top: 1.5rem;}
    div[data-testid="stMetricValue"] {color: #e94560 !important;}
    .winner-badge {
        background: #1a3a1a; border: 1px solid #2d6a2d;
        border-radius: 6px; padding: 4px 10px;
        font-size: 0.75rem; color: #5cb85c; display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────────────────
SCRAPE_FILE   = "scraped_leads.json"
HISTORY_FILE  = "send_history.json"
FROM_EMAIL    = "EaseYourFiling <official@easeyourfiling.com>"

# ── Automation Controls ───────────────────────────────────────────────────────
repeat_count = st.sidebar.number_input("Repetition count", min_value=1, value=1, step=1, key="repeat_count")
auto_send = st.sidebar.checkbox("Automatically send emails after generation", value=False, key="auto_send")

ALL_INDIA_STATES = [
    "All India",
    # 28 States
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # 8 Union Territories
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi", "Jammu and Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
]

# ── File helpers ───────────────────────────────────────────────────────────
def load_leads() -> list:
    if os.path.exists(SCRAPE_FILE):
        with open(SCRAPE_FILE) as f:
            return json.load(f)
    return []

def save_leads(data: list):
    with open(SCRAPE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(data: list):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ══════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════
st.markdown("## ⚡ EaseYourFiling — Smart Outreach")
st.caption("AI picks targets · Tofler finds real emails · AI battle writes best message · Resend delivers")
st.divider()

tab_scrape, tab_emails, tab_send, tab_history = st.tabs([
    "🎯 Step 1 — Find Companies",
    "📧 Step 2 — Emails & Messages",
    "📨 Step 3 — Send",
    "📊 History",
])


# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — FIND COMPANIES + SCRAPE TOFLER
# ══════════════════════════════════════════════════════════════════════════
with tab_scrape:
    st.markdown("### 🤖 AI generates company names → Tofler finds their real registered email")

    col_left, col_right = st.columns([3, 2])

    with col_left:
        target_type = st.selectbox("What kind of companies to target", [
            "Newly registered startups (last 1–2 years)",
            "Companies with pending ROC / annual filing",
            "Businesses needing GST registration",
            "Companies needing Trademark registration",
            "MSME / small businesses needing compliance",
            "Companies needing FSSAI food license",
            "Businesses needing Startup India registration",
            "Companies needing LLP / OPC registration",
            "Businesses needing revival from strike-off",
            "Custom (describe below)",
        ])

        custom_desc = ""
        if target_type == "Custom (describe below)":
            custom_desc = st.text_area("Describe your target", height=70, label_visibility="collapsed",
                placeholder="e.g. food businesses in Delhi that need FSSAI license...")

        col_s, col_n = st.columns(2)
        with col_s:
            state_filter = st.selectbox("State", ALL_INDIA_STATES)
        with col_n:
            company_count = st.selectbox("How many companies", [30, 50, 100, 200], index=1)

        company_type = st.selectbox("Company type", [
            "Private Limited (Pvt Ltd)",
            "All Types",
            "One Person Company (OPC)",
            "Limited Liability Partnership (LLP)",
            "Partnership Firm",
            "Section 8 / NGO",
            "Producer Company",
            "Nidhi Company",
            "Foreign Company",
        ], help="🔒 Public Limited (PLC) and Listed companies are excluded")

        headless_mode = st.checkbox("Run browser in background (headless)", value=True,
            help="Uncheck to watch the browser work in real time")

    with col_right:
        st.markdown("**How this works:**")
        st.markdown("""
**Step 1** — AI generates real company names matching your target

**Step 2** — Playwright opens Tofler for each company, finds the **MCA-registered email** (the real owner email, not info@)

**Step 3** — Results saved to CSV with: company name, CIN, email

**Why Tofler?** — Tofler shows the official email from MCA filings — this is the email the company director registered with the government.
        """)
        st.info("⏱️ ~2-3 seconds per company. 100 companies ≈ 4-5 minutes.")

    st.divider()

    go_btn = st.button("🚀 Start — Find Companies & Scrape Emails", type="primary", use_container_width=True)

    # ── Pipeline state machine ─────────────────────────────────────────────
    if go_btn:
        st.session_state.update({
            "pipe_state": "generating",
            "pipe_target": custom_desc if target_type == "Custom (describe below)" else target_type,
            "pipe_state_filter": state_filter,
            "pipe_company_type": company_type,
            "pipe_count": company_count,
            "pipe_headless": headless_mode,
            "pipe_companies": [],
            "pipe_leads": [],
            "pipe_idx": 0,
        })

    state = st.session_state.get("pipe_state", "idle")

    # ── GENERATING ────────────────────────────────────────────────────────
    if state == "generating":
        from company_finder import find_target_companies
        target = st.session_state["pipe_target"]
        s      = st.session_state["pipe_state_filter"]
        n      = st.session_state["pipe_count"]
        ctype  = st.session_state.get("pipe_company_type", "All Types")

        info = st.info(f"🤖 Finding {n} **{ctype}** companies for: **{target}** — this may take 30–60 seconds for large counts...")
        companies = find_target_companies(target_description=target, state=s, count=n, company_type=ctype)

        if not companies:
            info.error("AI returned no companies. Try again.")
            st.session_state["pipe_state"] = "idle"
        else:
            info.success(f"✅ Got {len(companies)} companies. Starting Tofler scrape...")
            st.session_state["pipe_companies"] = companies
            st.session_state["pipe_state"] = "scraping"
            st.session_state["pipe_idx"] = 0
            st.session_state["pipe_leads"] = []
            st.rerun()

    # ── SCRAPING ──────────────────────────────────────────────────────────
    elif state == "scraping":
        companies = st.session_state["pipe_companies"]
        idx       = st.session_state["pipe_idx"]
        leads     = st.session_state["pipe_leads"]
        total     = len(companies)
        headless  = st.session_state.get("pipe_headless", True)

        prog = st.progress(idx / total if total else 0)
        stat = st.empty()
        live_table = st.empty()

        # Process in chunks of 20 per rerun
        CHUNK = 20
        end_idx = min(idx + CHUNK, total)
        chunk_items = companies[idx:end_idx]  # pass full dicts with cin+slug

        stat.markdown(f"🔍 Scraping Tofler: **{chunk_items[0]['name']}** ... ({idx+1}–{end_idx}/{total})")

        from tofler_scraper import scrape_companies
        chunk_results = scrape_companies(chunk_items, headless=headless)

        # Merge with company metadata
        for i, r in enumerate(chunk_results):
            company_meta = companies[idx + i]
            leads.append({
                "company_name": r.get("company_name") or company_meta["name"],
                "cin":          r.get("cin", ""),
                "email":        r.get("email", ""),
                "industry":     company_meta.get("industry", ""),
                "state":        r.get("state") or company_meta.get("state", ""),
                "tofler_url":   r.get("tofler_url", ""),
                "scrape_status": r.get("status", ""),
            })

        st.session_state["pipe_leads"] = leads
        st.session_state["pipe_idx"] = end_idx
        prog.progress(end_idx / total)

        # Show live results
        if leads:
            df_live = pd.DataFrame(leads)
            found_so_far = df_live[df_live["email"] != ""]
            live_table.dataframe(
                df_live[["company_name", "cin", "email", "scrape_status"]].tail(20),
                use_container_width=True, hide_index=True,
            )

        if end_idx >= total:
            # Done scraping
            stat.empty()
            prog.empty()
            live_table.empty()
            st.session_state["pipe_state"] = "idle"
            save_leads(leads)
            st.session_state["scraped_leads"] = leads

            found = [l for l in leads if l["email"]]
            st.success(f"✅ Done! Found **{len(found)} real emails** out of {total} companies.")
            st.rerun()
        else:
            st.rerun()

    # ── SHOW RESULTS ──────────────────────────────────────────────────────
    leads = st.session_state.get("scraped_leads") or load_leads()

    if leads and state == "idle":
        df = pd.DataFrame(leads)
        found_df = df[df["email"] != ""]
        not_found_df = df[df["email"] == ""]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Scraped", len(df))
        m2.metric("Emails Found", len(found_df))
        m3.metric("Not Found", len(not_found_df))
        m4.metric("Success Rate", f"{int(len(found_df)/len(df)*100)}%" if len(df) else "0%")

        st.markdown(f"### 📋 Results — {len(found_df)} emails ready")

        tab_found, tab_all = st.tabs([f"✅ With Email ({len(found_df)})", f"📋 All ({len(df)})"])
        with tab_found:
            st.dataframe(found_df[["company_name", "cin", "email", "industry", "state"]],
                use_container_width=True, hide_index=True, height=400)
        with tab_all:
            st.dataframe(df[["company_name", "cin", "email", "scrape_status", "industry"]],
                use_container_width=True, hide_index=True, height=400)

        # Download CSV
        buf = io.StringIO()
        found_df[["company_name", "cin", "email", "industry", "state"]].to_csv(buf, index=False)
        st.download_button("⬇️ Download CSV", buf.getvalue(), "leads.csv", "text/csv")

        col_next, col_clear = st.columns([4, 1])
        with col_next:
            st.info("👉 Go to **Step 2 — Emails & Messages** to generate personalized messages")
        with col_clear:
            if st.button("🗑️ Clear", key="clear_leads"):
                save_leads([])
                st.session_state["scraped_leads"] = []
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — AI BATTLE: GENERATE PERSONALIZED MESSAGES
# ══════════════════════════════════════════════════════════════════════════
with tab_emails:
    st.markdown("### ⚔️ AI Battle — 4 models compete, best message wins for each company")

    leads = st.session_state.get("scraped_leads") or load_leads()
    found_leads = [l for l in leads if l.get("email")]

    if not found_leads:
        st.warning("No leads with emails yet. Complete Step 1 first.")
    else:
        st.markdown(f"**{len(found_leads)} companies with emails ready for message generation**")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**AI Models competing:**")
            st.markdown("- 🟢 Groq Llama 3.3 70B (fast)")
            st.markdown("- 🔵 OpenRouter Mistral 7B")
            st.markdown("- 🟣 Anthropic Claude Haiku")
            st.markdown("- 🟡 OpenAI GPT-4o (if quota available)")
            st.markdown("- ⚖️ **Judge:** Groq picks the winner")
        with col_b:
            st.markdown("**Each email is personalized based on:**")
            st.markdown("- Company name and CIN")
            st.markdown("- Industry / business type")
            st.markdown("- Company age (from CIN year)")
            st.markdown("- State / location")
            st.markdown("- Likely compliance needs")

        batch_size = len(found_leads)
        gen_btn = st.button("⚔️ Run AI Battle — Generate Messages", type="primary", use_container_width=True)

        if gen_btn:
            st.session_state["battle_state"] = "running"
            st.session_state["battle_leads"] = found_leads[:batch_size]
            st.session_state["battle_results"] = []
            st.session_state["battle_idx"] = 0

        battle_state = st.session_state.get("battle_state", "idle")

        if battle_state == "running":
            from ai_battle import generate_best_email

            b_leads  = st.session_state["battle_leads"]
            b_idx    = st.session_state["battle_idx"]
            b_results = st.session_state["battle_results"]
            b_total  = len(b_leads)

            prog2 = st.progress(b_idx / b_total if b_total else 0)
            stat2 = st.empty()

            # Process 3 at a time (parallel AI calls are already inside generate_best_email)
            CHUNK2 = 3
            end2 = min(b_idx + CHUNK2, b_total)

            for i in range(b_idx, end2):
                lead = b_leads[i]
                stat2.markdown(f"⚔️ AI battle for **{lead['company_name']}** ({i+1}/{b_total})...")
                email_result = generate_best_email(
                    company_name=lead["company_name"],
                    cin=lead.get("cin", ""),
                    industry=lead.get("industry", ""),
                    state=lead.get("state", ""),
                )
                b_results.append({**lead, **email_result})
                prog2.progress((i + 1) / b_total)

            st.session_state["battle_results"] = b_results
            st.session_state["battle_idx"] = end2

            if end2 >= b_total:
                stat2.empty()
                prog2.empty()
                st.session_state["battle_state"] = "done"
                st.rerun()
            else:
                st.rerun()

        elif battle_state == "done":
            b_results = st.session_state.get("battle_results", [])
            st.success(f"✅ Generated {len(b_results)} personalized messages!")
            st.session_state["ready_to_send"] = b_results
            st.session_state["battle_state"] = "idle"



            st.info("👉 Go to **Step 3 — Send** to send all emails")


# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — SEND
# ══════════════════════════════════════════════════════════════════════════
with tab_send:
    st.markdown("### 📨 Send Personalized Emails via Resend")

    ready = st.session_state.get("ready_to_send", [])

    if not ready:
        st.warning("No messages ready. Complete Step 2 first.")
    else:
        st.markdown(f"**{len(ready)} personalized emails ready to send from `official@easeyourfiling.com`**")

        # Preview table
        df_send = pd.DataFrame(ready)
        st.dataframe(
            df_send[["company_name", "email", "subject", "winner_model"]],
            use_container_width=True, hide_index=True, height=300,
        )

        st.divider()
        st.warning("⚠️ This will send real emails. Make sure your Resend domain is verified.")

        send_btn = st.button(f"📨 Send All {len(ready)} Emails Now", type="primary", use_container_width=True)

        if send_btn:
            import resend as resend_lib
            resend_lib.api_key = os.getenv("RESEND_API_KEY")

            history = load_history()
            prog3 = st.progress(0)
            stat3 = st.empty()
            sent = 0
            failed = 0
            total3 = len(ready)

            for i, item in enumerate(ready):
                to_email     = item["email"]
                company_name = item["company_name"]
                subject      = item.get("subject", "Compliance Support — EaseYourFiling")
                body_text    = item.get("body", "")

                stat3.markdown(f"📤 Sending to **{company_name}** `{to_email}` — {i+1}/{total3}")

                body_html = body_text.replace("\n", "<br>")
                html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
  <img src="https://easeyourfiling.com/logo.png" alt="EaseYourFiling" style="height:36px;margin-bottom:16px;">
  <div style="font-size:15px;line-height:1.8;color:#222;">{body_html}</div>
  <hr style="margin:20px 0;border:none;border-top:1px solid #eee;">
  <div style="font-size:12px;color:#999;">
    EaseYourFiling &nbsp;·&nbsp; official@easeyourfiling.com &nbsp;·&nbsp; +91 9065734856 &nbsp;·&nbsp;
    <a href="https://easeyourfiling.com" style="color:#e94560;">easeyourfiling.com</a>
  </div>
</div>"""

                try:
                    result = resend_lib.Emails.send({
                        "from": FROM_EMAIL,
                        "to": [to_email],
                        "subject": subject,
                        "html": html,
                        "text": body_text,
                        "reply_to": "official@easeyourfiling.com",
                    })
                    sent += 1
                    history.append({
                        "company": company_name, "email": to_email,
                        "subject": subject, "status": "sent",
                        "message_id": result.get("id", ""),
                        "winner_model": item.get("winner_model", ""),
                        "sent_at": datetime.now().isoformat(),
                    })
                except Exception as e:
                    failed += 1
                    history.append({
                        "company": company_name, "email": to_email,
                        "subject": subject, "status": f"failed: {str(e)[:80]}",
                        "message_id": "", "winner_model": "",
                        "sent_at": datetime.now().isoformat(),
                    })

                prog3.progress((i + 1) / total3)
                time.sleep(0.2)

            save_history(history)
            stat3.empty()
            prog3.empty()

            if sent:
                st.success(f"✅ Sent **{sent}** emails!")
                st.balloons()
                # Show a quick summary of recent sent emails (most recent first)
                sent_items = [h for h in history if h.get("status") == "sent"]
                if sent_items:
                    df_sent = pd.DataFrame(sent_items)
                    st.caption("🗂️ Sent email details (most recent first)")
                    st.dataframe(df_sent[["company", "email", "subject", "message_id", "sent_at"]].sort_values("sent_at", ascending=False).head(10), use_container_width=True, hide_index=True)
            if failed:
                st.warning(f"⚠️ {failed} failed — check History tab")


# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — HISTORY
# ══════════════════════════════════════════════════════════════════════════
with tab_history:
    st.markdown("### 📊 Send History")

    history = load_history()

    if history:
        df_h = pd.DataFrame(history)
        sent_df = df_h[df_h["status"] == "sent"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Sent", len(sent_df))
        c2.metric("Failed", len(df_h) - len(sent_df))
        c3.metric("All Time", len(df_h))

        if not sent_df.empty:
            sent_df2 = sent_df.copy()
            sent_df2["date"] = pd.to_datetime(sent_df2["sent_at"]).dt.date
            daily = sent_df2.groupby("date").size().reset_index(name="Sent")
            st.bar_chart(daily.set_index("date"))

        # Winner model stats
        if "winner_model" in df_h.columns:
            model_counts = df_h[df_h["winner_model"] != ""]["winner_model"].value_counts()
            if not model_counts.empty:
                st.markdown("**AI Model Win Rate:**")
                st.bar_chart(model_counts)

        # Only show columns that actually exist
        show_cols = [c for c in ["company", "email", "subject", "status", "winner_model", "sent_at"] if c in df_h.columns]
        st.dataframe(
            df_h[show_cols].sort_values("sent_at", ascending=False) if "sent_at" in df_h.columns else df_h[show_cols],
            use_container_width=True, hide_index=True,
        )

        buf = io.StringIO()
        df_h.to_csv(buf, index=False)
        st.download_button("⬇️ Download History", buf.getvalue(), "history.csv", "text/csv")
    else:
        st.info("No history yet.")
