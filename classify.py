"""
Classify the forum comments in comments.json with Cloudflare's Clef model,
then write results.html, a page for reviewing each comment and its label.

Run:   python3 classify.py                          -> comments.json with clef-flash, writes results.html
       python3 classify.py comments-v2.json clef    -> harder set with clef, writes results-v2.html

Needs: cloud-flare.local.sh with your account ID and API token.
Uses only the Python standard library.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request

INPUT = sys.argv[1] if len(sys.argv) > 1 else "comments.json"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "clef-flash"
SUFFIX = "-v2" if "v2" in INPUT else ""
LOW_CONFIDENCE = 0.5  # answers below this get flagged for a closer human look

# ---------------------------------------------------------------------------
# THE DEFINITIONS. These decide how many mistakes Clef makes.
# Read them and change them so they match where YOU draw the line.
# ---------------------------------------------------------------------------
INSTRUCTIONS = (
    "`comment` is a post on the discussion forum of an online college course on "
    "using AI tools. The forum is `forum` and the thread is `thread`. Decide whether "
    "a moderator should leave the post up, remove it as toxic, or remove it as spam. "
    "Students are often blunt, informal, frustrated or joking; that alone is not toxic."
)
CRITERIA = {
    "acceptable": (
        "A genuine post by a course participant: questions, answers, sharing work, "
        "feedback, complaints or criticism of the course, frustration, informal "
        "language or mild swearing not aimed at a person, and friendly banter."
    ),
    "toxic": (
        "Attacks, insults, mocks, harasses, threatens or demeans a person or group; "
        "slurs; hateful or sexual content aimed at someone; or encourages "
        "cheating that harms others, such as sharing someone's work without consent. "
        "Stereotyping a group and belittle them without using cuss words OR framed as a joke."
    ),
    "spam": (
        "Not a genuine contribution: advertising, selling services (including "
        "paid assignment help), promotional links, scams, phishing, or repeated "
        "off-topic posting meant to promote something."
    ),
}
# ---------------------------------------------------------------------------


def load_credentials():
    text = open("cloud-flare.local.sh").read()
    creds = dict(re.findall(r'export (\w+)="([^"]*)"', text))
    return creds["CLOUDFLARE_ACCOUNT_ID"], creds["CLOUDFLARE_API_TOKEN"]


def classify(account, token, data, c):
    payload = {
        "state": {
            "comment": c["comment"],
            "forum": data.get("forum", ""),
            "thread": c.get("thread", ""),
        },
        "questions": {
            "label": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA}
        },
    }
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{MODEL}"
    for attempt in range(5):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.load(resp)
            if not result.get("success"):
                raise RuntimeError(result.get("errors"))
            return result["result"]["answers"]["label"]
        except urllib.error.HTTPError as e:
            if e.code == 429:  # too many requests: wait and retry
                time.sleep(2 ** attempt)
                continue
            if e.code in (401, 403):
                sys.exit("Cloudflare rejected the credentials. Check cloud-flare.local.sh.")
            raise
    raise RuntimeError(f"Gave up on comment {c['id']} after repeated rate limits")


def write_html(data, results, path=None):
    path = path or f"results{SUFFIX}.html"
    counts = {k: sum(1 for r in results if r["label"] == k) for k in CRITERIA}
    low = sum(1 for r in results if r["confidence"] < LOW_CONFIDENCE)
    rows = []
    for r in results:
        probs = " ".join(
            f'<span class="p">{k} {v:.2f}</span>'
            for k, v in sorted(r["probabilities"].items(), key=lambda x: -x[1])
        )
        flag = ' <span class="flag">unsure</span>' if r["confidence"] < LOW_CONFIDENCE else ""
        rows.append(
            f'<tr class="row {r["label"]}" data-label="{r["label"]}" '
            f'data-conf="{r["confidence"]:.4f}" data-id="{r["id"]}">'
            f'<td class="id">{r["id"]}</td>'
            f'<td><span class="tag {r["label"]}">{r["label"]}</span>{flag}'
            f'<div class="conf">confidence {r["confidence"]:.2f}</div><div>{probs}</div></td>'
            f'<td><div class="meta">{html.escape(r["author"])} in {html.escape(r["thread"])}, '
            f'{html.escape(r["posted_at"])}</div>'
            f'<div class="text">{html.escape(r["comment"])}</div></td></tr>'
        )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Clef moderation review</title>
<style>
:root {{ --bg:#eef1f4; --paper:#ffffff; --ink:#1d2733; --muted:#5d6b7a; --line:#d5dbe2;
  --ok:#2f7d4f; --okbg:#e3f3e9; --tox:#b3261e; --toxbg:#fbe4e2; --spam:#8a5a00; --spambg:#fdf0d5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121820; --paper:#1b232d; --ink:#e6ebf0;
  --muted:#9aa7b4; --line:#2e3a47; --ok:#7fd3a0; --okbg:#1e3a2b; --tox:#ff9a92; --toxbg:#4a1f1c;
  --spam:#f2c46b; --spambg:#45360f; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif; }}
header {{ position:sticky; top:0; background:var(--paper); border-bottom:1px solid var(--line);
  padding:14px 20px; z-index:2; }}
h1 {{ margin:0 0 4px; font-size:20px; }}
.sub {{ color:var(--muted); font-size:13px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
button {{ font:inherit; font-size:13px; padding:5px 12px; border:1px solid var(--line);
  border-radius:999px; background:var(--paper); color:var(--ink); cursor:pointer; }}
button.on {{ background:var(--ink); color:var(--paper); border-color:var(--ink); }}
button:focus-visible {{ outline:2px solid var(--ok); outline-offset:2px; }}
main {{ max-width:1000px; margin:0 auto; padding:16px; }}
table {{ width:100%; border-collapse:collapse; background:var(--paper); }}
td {{ padding:12px; border-bottom:1px solid var(--line); vertical-align:top; }}
td.id {{ width:44px; color:var(--muted); font-weight:600; }}
td:nth-child(2) {{ width:220px; }}
tr.toxic td.id {{ box-shadow: inset 4px 0 var(--tox); }}
tr.spam td.id {{ box-shadow: inset 4px 0 var(--spam); }}
.tag {{ display:inline-block; padding:2px 10px; border-radius:4px; font-weight:600; font-size:13px; }}
.tag.acceptable {{ color:var(--ok); background:var(--okbg); }}
.tag.toxic {{ color:var(--tox); background:var(--toxbg); }}
.tag.spam {{ color:var(--spam); background:var(--spambg); }}
.flag {{ font-size:12px; color:var(--tox); border:1px solid var(--tox); border-radius:4px; padding:0 6px; margin-left:6px; }}
.conf, .meta {{ color:var(--muted); font-size:12px; margin-top:4px; }}
.p {{ font-size:12px; color:var(--muted); margin-right:8px; white-space:nowrap; }}
.text {{ max-width:68ch; }}
@media (max-width:640px) {{ td {{ display:block; width:auto !important; border:none; padding:6px 12px; }}
  tr {{ display:block; border-bottom:1px solid var(--line); padding:6px 0; }} }}
</style></head><body>
<header>
<h1>Clef moderation review</h1>
<div class="sub">{html.escape(data.get("forum",""))}. Model: {MODEL}.
{len(results)} comments: {counts["acceptable"]} acceptable, {counts["toxic"]} toxic,
{counts["spam"]} spam. {low} below {LOW_CONFIDENCE} confidence.</div>
<div class="controls">
<button data-f="all" class="on">All</button>
<button data-f="acceptable">Acceptable</button>
<button data-f="toxic">Toxic</button>
<button data-f="spam">Spam</button>
<button data-f="unsure">Unsure only</button>
<button id="sort">Sort by confidence</button>
</div></header>
<main><table><tbody id="rows">{''.join(rows)}</tbody></table></main>
<script>
const rows=[...document.querySelectorAll('.row')], body=document.getElementById('rows');
document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('[data-f]').forEach(x=>x.classList.remove('on')); b.classList.add('on');
  const f=b.dataset.f;
  rows.forEach(r=>r.style.display=(f==='all'||r.dataset.label===f||
    (f==='unsure'&&+r.dataset.conf<{LOW_CONFIDENCE}))?'':'none');
}});
let byConf=false; const sortBtn=document.getElementById('sort');
sortBtn.onclick=()=>{{ byConf=!byConf; sortBtn.classList.toggle('on',byConf);
  sortBtn.textContent=byConf?'Sort by id':'Sort by confidence';
  rows.slice().sort((a,b)=>byConf?a.dataset.conf-b.dataset.conf:a.dataset.id-b.dataset.id)
    .forEach(r=>body.appendChild(r)); }};
</script></body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    data = json.load(open(INPUT, encoding="utf-8"))
    account, token = load_credentials()
    results = []
    for c in data["comments"]:
        a = classify(account, token, data, c)
        results.append({**c, "label": a["choice"], "confidence": a["confidence"],
                        "probabilities": a["probabilities"]})
        print(f'{c["id"]:>3}  {a["choice"]:<10}  conf {a["confidence"]:.2f}')
    json.dump({"model": MODEL, "results": results},
              open(f"results{SUFFIX}.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    write_html(data, results)
    print(f"\nWrote results{SUFFIX}.html and results{SUFFIX}.json")


if __name__ == "__main__":
    main()