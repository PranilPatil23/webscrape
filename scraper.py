import requests
from bs4 import BeautifulSoup
import urllib.parse
import google.generativeai as genai
import re
from serpapi import GoogleSearch
from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()

SERP_API_KEY = os.getenv("SERP_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
}

# 🔥 GLOBAL MEMORY
previous_results = {}

# ---------- INPUT DETECTION ----------
def detect_input(user_input):
    url_pattern = re.compile(
        r'^(https?://)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}'
    )
    if url_pattern.match(user_input.strip()):
        return "url"
    return "keyword"

def fix_url(url):
    url = url.strip()
    if not url.startswith("http"):
        return "https://" + url
    return url

# ---------- URL SCRAPER ----------
def scrape_static(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code != 200:
            return [{"title": "Error", "content": f"Status code {response.status_code}", "link": url}]

        soup = BeautifulSoup(response.text, "html.parser")

        data = []

        # 🔥 title fix
        page_title = soup.title.string if soup.title else "No Title"

        paragraphs = soup.find_all("p")

        content = " ".join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30])

        if not content:
            content = "Content not available (possibly JS-based site)"

        data.append({
            "title": page_title,
            "content": content[:2000],
            "link": url
        })

        return data

    except Exception as e:
        return [{"title": "Error", "content": str(e), "link": url}]
# ---------- KEYWORD SCRAPER ----------
def scrape_by_keyword(keyword):
    try:
        query = urllib.parse.quote(keyword)
        url = f"https://html.duckduckgo.com/html/?q={query}"

        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        links = soup.select("a.result__a")[:5]
        data = []

        for item in links:
            link = item.get("href")
            title = item.get_text()

            content = ""

            try:
                page = requests.get(link, headers=HEADERS, timeout=5)
                page_soup = BeautifulSoup(page.text, "html.parser")

                paragraphs = page_soup.find_all("p")
                content = " ".join([p.get_text() for p in paragraphs[:5]])

            except:
                pass

            # 🔥 IMPORTANT: even if content empty, still add basic info
            data.append({
                "title": title,
                "link": link,
                "content": content if content else "Content not available"
            })
            
        return data

    except Exception as e:
        return {"error": str(e)}
# ---------- BING SCRAPER ----------
def scrape_by_bing(keyword):
    try:
        query = urllib.parse.quote(keyword)
        url = f"https://www.bing.com/search?q={query}"

        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        links = soup.select("li.b_algo h2 a")[:5]
        data = []

        for item in links:
            link = item.get("href")
            title = item.get_text()

            content = ""

            try:
                page = requests.get(link, headers=HEADERS, timeout=5)
                page_soup = BeautifulSoup(page.text, "html.parser")

                paragraphs = page_soup.find_all("p")
                content = " ".join([p.get_text() for p in paragraphs[:5]])

            except:
                pass

            data.append({
                "title": title,
                "link": link,
                "content": content if content else "Content not available"
            })
            
        return data

    except Exception as e:
        return {"error": str(e)}

# ---------- GOOGLE SCRAPER ----------
def scrape_by_google(keyword):
    try:
        from googlesearch import search
        links = list(search(keyword, num_results=5, sleep_interval=1))
        data = []

        for link in links:
            title = "Google Result"
            content = ""

            try:
                page = requests.get(link, headers=HEADERS, timeout=5)
                page_soup = BeautifulSoup(page.text, "html.parser")
                
                if page_soup.title:
                    title = page_soup.title.get_text(strip=True)

                paragraphs = page_soup.find_all("p")
                content = " ".join([p.get_text() for p in paragraphs[:5]])

            except:
                pass

            data.append({
                "title": title,
                "link": link,
                "content": content if content else "Content not available"
            })
            
        if not data:
            return {"error": "Google blocked the request or no results found. Try Bing or DuckDuckGo."}
            
        return data

    except ImportError:
        return {"error": "googlesearch-python not installed. Run: pip install googlesearch-python"}
    except Exception as e:
        return {"error": f"Google Search Error: {str(e)}"}

# ---------- ENHANCED SCRAPER ----------
def enhanced_scrape(query, engine="all"):
    data = []

    if engine in ["duckduckgo", "all"]:
        data += scrape_by_keyword(query)

    if engine in ["bing", "all"]:
        data += scrape_by_bing(query)

    if engine in ["google", "all"]:
        data += scrape_by_google(query)

    if engine in ["serpapi", "all"]:
        data += serp_search(query)

    if engine in ["tavily", "all"]:
        data += tavily_search(query)

    unique = {item['link']: item for item in data if item.get("link")}
    return list(unique.values())

# ---------- AI SUMMARY ----------
def ai_summary(data_list, query):
    combined = ""

    for item in data_list:
        combined += item.get("content", "") + "\n"

    if not combined.strip():
        return f"No detailed data found for '{query}', but here are relevant sources."

    prompt = f"""
    User Query: {query}

    You are an expert assistant.

    Based on the following data collected from multiple websites:
    {combined}

    Do the following:
    - Give a clear explanation
    - Combine all sources
    - Remove duplicate ideas
    - Make it easy to understand
    - Answer like ChatGPT
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Error: {str(e)}"

# SERP API Google Search
def serp_search(query):
    params = {
        "q": query,
        "api_key": SERP_API_KEY,
        "num": 10           
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    data = []
    for r in results.get("organic_results", []):
        data.append({
            "title": r.get("title"),
            "link": r.get("link"),
            "content": r.get("snippet")
        })

    return data 

# TAVILY Search
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

def tavily_search(query):
    res = tavily_client.search(query=query, search_depth="advanced")

    data = []
    for r in res["results"]:
        data.append({
            "title": r["title"],
            "link": r["url"],
            "content": r["content"]
        })

    return data

# Deep Research
def deep_research(query):
    base_results = enhanced_scrape(query, "all")

    deep_data = []
    for item in base_results[:5]:
        link = item.get("link")
        if link:
            extra = scrape_static(link)
            if isinstance(extra, list):
                deep_data.extend(extra)

    return base_results + deep_data

