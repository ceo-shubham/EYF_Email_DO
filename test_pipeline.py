import time

print("=" * 55)
print("FULL PIPELINE TEST — 30 companies")
print("=" * 55)

# Step 1
print("\n[1/3] Generating 30 company names...")
t = time.time()
from company_finder import find_target_companies
companies = find_target_companies(
    "Newly registered startups (last 1-2 years)",
    state="Maharashtra",
    count=30,
    company_type="Private Limited (Pvt Ltd)",
)
print(f"  Got {len(companies)} companies in {time.time()-t:.1f}s")
for c in companies[:3]:
    print(f"  - {c['name']}")

# Step 2
print(f"\n[2/3] Scraping Tofler emails for {len(companies)} companies...")
t = time.time()
from tofler_scraper import scrape_companies

found = 0
not_found = 0
def prog(i, total, r):
    global found, not_found
    if r["email"]:
        found += 1
        print(f"  ✅ [{i}/{total}] {r['company_name'][:45]}: {r['email']}")
    else:
        not_found += 1
        print(f"  ❌ [{i}/{total}] {r['company_name'][:45]}: {r['status']}")

results = scrape_companies(companies, on_progress=prog, headless=True)
elapsed = time.time() - t
print(f"\n  Done in {elapsed:.1f}s | Found: {found} | Not found: {not_found}")
print(f"  Success rate: {int(found/len(results)*100) if results else 0}%")

# Step 3
found_results = [r for r in results if r.get("email")]
if found_results:
    print(f"\n[3/3] AI battle for: {found_results[0]['company_name']}")
    t = time.time()
    from ai_battle import generate_best_email
    r = found_results[0]
    msg = generate_best_email(r["company_name"], r.get("cin",""), "", "Maharashtra")
    print(f"  Winner: {msg.get('winner_model','?')}")
    print(f"  Subject: {msg.get('subject','')}")
    print(f"  Done in {time.time()-t:.1f}s")

print("\n" + "=" * 55)
print(f"  Generated: {len(companies)} | Emails: {found} | Rate: {int(found/max(len(results),1)*100)}%")
print("=" * 55)
