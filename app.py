import os, re, time, urllib.parse, html
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string
import requests, feedparser

app = Flask(__name__)
GUIDE = "https://bdsmovement.net/sites/default/files/2024-12/Guide%20to%20BDS%20Boycott%20%26%20Pressure%20Corporate%20Priority%20Targeting-30%20Nov%202024-Submitted%20by%20BDS%20movement.pdf"
AFSC = "https://investigate.info/"
SHORTLIST = "https://investigate.info/sites/default/files/attachment/BDS%20Divestment%20Shortlist%20-%20November%202026.pdf"
# Each item is a documented campaign association, not a blanket ethical judgment.
# category: consumer, grassroots, pressure; source: attributed publication.
def item(name, category, description, source=GUIDE, relation="direct"):
    return dict(name=name, category=category, description=description, source=source, relation=relation)
TARGETS = {
"CVX":item("Chevron","consumer","Chevron, including Caltex and Texaco, is a consumer-boycott target."),
"INTC":item("Intel","consumer","Intel is a named consumer-boycott target."),
"DELL":item("Dell Technologies","consumer","Dell is a named consumer-boycott target."),
"SIE.DE":item("Siemens","consumer","Siemens is a named consumer-boycott target."),
"SIEGY":item("Siemens","consumer","Siemens is a named consumer-boycott target."),
"HPQ":item("HP Inc.","consumer","The BDS guide discusses HP Inc. and HPE."),
"HPE":item("Hewlett Packard Enterprise","consumer","The BDS guide discusses HP Inc. and HPE."),
"CA.PA":item("Carrefour","consumer","Carrefour is a named consumer-boycott target."),
"CRRFY":item("Carrefour","consumer","Carrefour is a named consumer-boycott target."),
"CS.PA":item("AXA","consumer","AXA is a named consumer-boycott target."),
"AXAHY":item("AXA","consumer","AXA is a named consumer-boycott target."),
"DIS":item("The Walt Disney Company","consumer","Disney+ is a named campaign target; this is a brand-to-parent association.",relation="brand"),
"PEP":item("PepsiCo","consumer","SodaStream is a named target owned by PepsiCo; parent relationship is distinguished.",relation="brand"),
"MCD":item("McDonald's","grassroots","McDonald's is listed as a BDS-supported grassroots campaign."),
"KO":item("The Coca-Cola Company","grassroots","Coca-Cola is listed as a BDS-supported grassroots campaign."),
"QSR":item("Restaurant Brands International","grassroots","Burger King is listed as a grassroots campaign; linked to listed parent.",relation="brand"),
"YUM":item("Yum! Brands","grassroots","Pizza Hut is listed as a grassroots campaign; linked to listed parent.",relation="brand"),
"PZZA":item("Papa John's International","grassroots","Papa John's is listed as a grassroots campaign."),
"WIX":item("Wix.com","grassroots","Wix is listed as a grassroots campaign."),
"GOOG":item("Alphabet","pressure","Google is a BDS pressure target, including Project Nimbus.",relation="brand"),
"GOOGL":item("Alphabet","pressure","Google is a BDS pressure target, including Project Nimbus.",relation="brand"),
"AMZN":item("Amazon","pressure","Amazon is a BDS pressure target, including Project Nimbus."),
"BKNG":item("Booking Holdings","pressure","Booking.com is listed as a pressure target.",relation="brand"),
"ABNB":item("Airbnb","pressure","Airbnb is a pressure target."),
"EXPE":item("Expedia Group","pressure","Expedia is a pressure target."),
"TEVA":item("Teva Pharmaceutical Industries","pressure","Teva is a pressure target."),
"MSFT":item("Microsoft","consumer","BDS launched a Microsoft/Xbox campaign in April 2025.","https://bdsmovement.net/news/boycott-microsofts-xbox",relation="brand"),
"6954.T":item("FANUC","pressure","BDS operates a Stop FANUC campaign.","https://www.bdsmovement.net/stop-fanuc"),
"FANUY":item("FANUC","pressure","BDS operates a Stop FANUC campaign.","https://www.bdsmovement.net/stop-fanuc"),
}
EXTRAS = {"ADS.DE":"adidas AG","ADDYY":"adidas AG","PUM.DE":"PUMA SE","NKE":"NIKE, Inc.","AAPL":"Apple Inc.","META":"Meta Platforms","NVDA":"NVIDIA","TSLA":"Tesla","ASML":"ASML Holding","MC.PA":"LVMH","OR.PA":"L'Oreal","NESN.SW":"Nestle","7203.T":"Toyota"}
HEADERS = {"User-Agent":"ClearScreen research app (non-commercial; contact via website)"}
CACHE={}
def cached(key,ttl,func):
    t=time.time()
    if key in CACHE and t-CACHE[key][0] < ttl:return CACHE[key][1]
    value=func();CACHE[key]=(t,value);return value

def sec():
    def fetch():
        try:
            r=requests.get("https://www.sec.gov/files/company_tickers.json",headers=HEADERS,timeout=7);r.raise_for_status()
            return {v["ticker"].upper():v["title"] for v in r.json().values()}
        except Exception:return {}
    return cached("sec",86400,fetch)

def yahoo(q):
    def fetch():
        try:
            r=requests.get("https://query1.finance.yahoo.com/v1/finance/search",params={"q":q,"quotesCount":10,"newsCount":0},headers={"User-Agent":"Mozilla/5.0"},timeout=4);r.raise_for_status()
            return [{"ticker":v["symbol"].upper(),"name":v.get("shortname") or v.get("longname") or v["symbol"],"exchange":v.get("exchDisp","")} for v in r.json().get("quotes",[]) if v.get("quoteType")=="EQUITY" and v.get("symbol")]
        except Exception:return []
    return cached("yahoo:"+q.lower(),3600,fetch)

@app.get("/api/suggest")
def suggest():
    q=request.args.get("q","").strip()[:60]
    if len(q)<2:return jsonify(suggestions=[])
    catalog=sec();catalog.update(EXTRAS);catalog.update({k:v["name"] for k,v in TARGETS.items()})
    matches=[]
    for ticker,name in catalog.items():
        if q.casefold() in (ticker+" "+name).casefold():
            rank=0 if ticker.lower()==q.lower() else 1 if ticker.lower().startswith(q.lower()) else 2 if name.lower().startswith(q.lower()) else 3
            matches.append((rank,len(name),ticker,{"ticker":ticker,"name":name,"exchange":""}))
    matches.sort(key=lambda v:(v[0],v[1],v[2]))
    results=[m[3] for m in matches[:10]]
    for v in yahoo(q):
        if len(results)>=12:break
        if not any(x["ticker"]==v["ticker"] for x in results):results.append(v)
    return jsonify(suggestions=results)

def recent_news(name):
    articles=[]
    for publisher,domain in [("Reuters","reuters.com"),("AP","apnews.com"),("BBC","bbc.com"),("The Guardian","theguardian.com"),("Financial Times","ft.com")]:
        query=f'"{name}" (Israel OR Gaza OR Palestine OR settlements OR military OR BDS) site:{domain} when:18m'
        url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":query,"hl":"en-US","gl":"US","ceid":"US:en"})
        try:
            r=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=5);r.raise_for_status()
            for v in feedparser.parse(r.content).entries[:2]:
                articles.append({"title":html.unescape(v.get("title","")),"url":v.get("link",""),"publisher":publisher,"published":v.get("published","")})
        except Exception:pass
    return articles[:10]

@app.get("/api/check")
def check():
    ticker=request.args.get("ticker","").strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,24}",ticker):return jsonify(error="Choose a valid ticker from the suggestions."),400
    matched=TARGETS.get(ticker)
    company=(matched or {}).get("name") or EXTRAS.get(ticker) or sec().get(ticker) or next((x["name"] for x in yahoo(ticker) if x["ticker"]==ticker),None)
    if not company:return jsonify(ticker=ticker,status="unresolved",message="Company not identified. No conclusion can be drawn.",evidence=[],news=[],sources={"guide":GUIDE,"afsc":AFSC,"shortlist":SHORTLIST})
    articles=cached("news:"+company,1800,lambda:recent_news(company))
    return jsonify(ticker=ticker,company=company,status="flagged" if matched else "unknown",match=matched,evidence=[matched] if matched else [],news=articles,message="Attributed campaign match; review primary evidence." if matched else "No match in this curated mapping. This is NOT confirmation the company is safe. Sources have not been exhaustively checked.",sources={"guide":GUIDE,"afsc":AFSC,"shortlist":SHORTLIST},checked_at=datetime.now(timezone.utc).isoformat())

@app.get("/api/health")
def health():return jsonify(ok=True,curated_tickers=len(TARGETS))

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ClearScreen — Evidence-led company research</title><style>
:root{font-family:Inter,system-ui,-apple-system,sans-serif;color:#e6f0e9;background:#0d1715}*{box-sizing:border-box}body{margin:0}main{max-width:840px;margin:0 auto;padding:36px 20px 80px}.brand{font-size:21px;color:#b9f6d0;font-weight:800}.hint{color:#91a79c}.headline{font-size:clamp(34px,7vw,58px);margin:80px 0 10px;line-height:1.08}.headline em{color:#9de6b8}.search{margin-top:30px;position:relative;display:flex;gap:10px}input{flex:1;min-width:0;padding:17px 18px;background:#182824;color:white;border:1px solid #3a5b4b;border-radius:12px;font-size:17px}button{padding:14px 22px;border:0;border-radius:12px;background:#a8e7be;color:#10211a;font-size:16px;font-weight:750;cursor:pointer}.suggestions{position:absolute;left:0;right:100px;top:60px;background:#172722;border:1px solid #385444;border-radius:12px;z-index:10;max-height:360px;overflow:auto;box-shadow:0 12px 24px #0008}.suggestion{padding:12px 16px;cursor:pointer;border-bottom:1px solid #2c4036;display:flex;justify-content:space-between;gap:12px}.suggestion:hover,.suggestion:focus{background:#2c4537}.ticker{color:#b4f2c5;font-family:monospace}section{margin-top:32px;background:#162521;border:1px solid #2b4337;border-radius:17px;padding:26px}h2{margin-top:0}a{color:#a8e7be}small{color:#91a79c}.tag{display:inline-block;padding:7px 12px;border-radius:20px;background:#364536;color:#d7eddd;font-weight:700}.flagged{background:#5a392e;color:#ffd3c5}.unknown{background:#3a483a;color:#e3e9cc}.source{padding:16px 0;border-bottom:1px solid #304338}.source:last-child{border:0}footer{margin-top:45px;color:#91a79c;font-size:13px;line-height:1.6}#result{display:none}@media(max-width:540px){.search{flex-direction:column}.suggestions{right:0;top:58px}.headline{margin-top:50px}section{padding:18px}}
</style></head><body><main><div class="brand">◈ clearScreen</div><p class="hint">EVIDENCE-LED INVESTMENT RESEARCH</p><h1 class="headline">Know what you <em>invest in.</em></h1><p class="hint">Search by company name or stock ticker. Choose a suggestion to research documented BDS campaigns and relevant recent reporting.</p><div class="search"><input id="input" placeholder="Try adidas, Microsoft, CVX…" autocomplete="off" aria-label="Company or ticker" role="combobox" aria-autocomplete="list" aria-expanded="false"><button id="check">Check</button><div class="suggestions" id="suggestions" role="listbox" hidden></div></div><p id="notice" class="hint"></p><section id="result"><h2 id="company"></h2><span id="status" class="tag"></span><p id="message"></p><div id="evidence"></div><h3>Recent reporting</h3><p class="hint">Headlines are leads for verification, not independently validated allegations.</p><div id="news"></div><h3>Primary sources</h3><div id="sources"></div></section><footer>ClearScreen is a research aid, not a certification or investment recommendation. The absence of a curated match is never a safe-company verdict. Campaign classifications reflect the named publisher, and parent/subsidiary relationships must be reviewed separately. News retrieval may be incomplete.</footer></main>
<script>
const $=id=>document.getElementById(id);let chosen=null, timer=0, items=[];const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function close(){ $('suggestions').hidden=true; $('input').setAttribute('aria-expanded','false') }
async function suggest(){ const q=$('input').value.trim();chosen=null;if(q.length<2){close();return}try{const r=await fetch('/api/suggest?q='+encodeURIComponent(q));items=(await r.json()).suggestions||[];const list=$('suggestions');list.innerHTML='';items.forEach(v=>{const el=document.createElement('div');el.className='suggestion';el.setAttribute('role','option');el.tabIndex=0;el.innerHTML='<span>'+escapeHTML(v.name)+'<br><small>'+escapeHTML(v.exchange||'Public company')+'</small></span><span class="ticker">'+escapeHTML(v.ticker)+'</span>';const select=()=>{chosen=v.ticker;$('input').value=v.name+' ('+v.ticker+')';close()};el.addEventListener('mousedown',e=>{e.preventDefault();select()});el.addEventListener('keydown',e=>{if(e.key==='Enter')select()});list.append(el)});list.hidden=!items.length;$('input').setAttribute('aria-expanded',String(!!items.length));}catch(e){close()}}
$('input').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(suggest,260)});$('input').addEventListener('keydown',e=>{if(e.key==='Enter'){if(!chosen&&items.length){chosen=items[0].ticker;$('input').value=items[0].name+' ('+chosen+')';close()}check()};if(e.key==='Escape')close()});document.addEventListener('click',e=>{if(!e.target.closest('.search'))close()});$('check').addEventListener('click',check);
function link(url,label){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=label;return a}
async function check(){const raw=$('input').value.trim();const match=raw.match(/\(([A-Za-z0-9.\-]+)\)$/);const ticker=chosen||(match&&match[1])||(/^[A-Za-z0-9.\-]+$/.test(raw)?raw:null);if(!ticker){$('notice').textContent='Choose a company from the dropdown.';return}$('notice').textContent='Checking available sources…';close();try{const r=await fetch('/api/check?ticker='+encodeURIComponent(ticker));const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');$('notice').textContent='';$('result').style.display='block';$('company').textContent=(d.company||ticker)+' · '+d.ticker;$('status').textContent=d.status==='flagged'?'Documented campaign match':d.status==='unknown'?'Not assessed / inconclusive':'Company unresolved';$('status').className='tag '+(d.status==='flagged'?'flagged':'unknown');$('message').textContent=d.message||'';const evidence=$('evidence');evidence.replaceChildren();(d.evidence||[]).forEach(v=>{const div=document.createElement('div');div.className='source';div.textContent=v.description+' · Category: '+v.category+' · Relationship: '+v.relation+' · ';div.append(link(v.source,'Original BDS source'));evidence.append(div)});const news=$('news');news.replaceChildren();if(!d.news?.length)news.textContent='No recent news retrieved. This is not evidence of absence.';(d.news||[]).forEach(v=>{const el=document.createElement('div');el.className='source';el.append(link(v.url,v.title||'Read article'));const s=document.createElement('small');s.textContent=' · '+v.publisher+' · '+v.published;el.append(s);news.append(el)});const sources=$('sources');sources.replaceChildren();for(const [key,url] of Object.entries(d.sources||{})){const p=document.createElement('p');p.append(link(url,key==='guide'?'BDS corporate targeting guide':key==='afsc'?'AFSC Investigate':'AFSC November 2026 divestment shortlist'));sources.append(p)}}catch(e){$('notice').textContent='Unable to check: '+e.message}}
</script></body></html>"""

@app.get("/")
def home():return render_template_string(HTML)

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5000")))
