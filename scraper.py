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

# Support both GEMINI_API_KEY and Gemini_API_KEY
gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
if gemini_key:
    genai.configure(api_key=gemini_key)

# Use a stable default model and avoid network calls during import
available_model = "gemini-1.5-flash"
model = genai.GenerativeModel(available_model)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "en-US,en;q=0.9",
}

# 🔥 GLOBAL MEMORY
previous_results = {}

# 🔥 SEARCH CACHE
SEARCH_CACHE = {}

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
        return {"error": "googlesearch-python not installed. Run:   pip install googlesearch-python"}
    except Exception as e:
        return {"error": f"Google Search Error: {str(e)}"}

# ---------- ENHANCED SCRAPER ----------
def enhanced_scrape(query, engine="all"):
    data = []

    if engine in ["duckduckgo", "all"]:
        result = scrape_by_keyword(query)
        if isinstance(result, list):
            data.extend(result)

    if engine in ["bing", "all"]:
        result = scrape_by_bing(query)
        if isinstance(result, list):
            data.extend(result)

    if engine in ["google", "all"]:
        result = scrape_by_google(query)
        if isinstance(result, list):
            data.extend(result)

    if engine in ["serpapi", "all"]:
        result = serp_search(query)
        if isinstance(result, list):
            data.extend(result)

    if engine in ["tavily", "all"]:
        result = tavily_search(query)
        if isinstance(result, list):
            data.extend(result)

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


# ---------- HDFC CATEGORY SCRAPER ----------
def scrape_hdfc_categories():
    return [
        {
            "title": "Credit Cards",
            "link": "https://www.hdfcbank.com/personal/pay/cards/credit-cards"
        },
        {
            "title": "Debit Cards",
            "link": "https://www.hdfcbank.com/personal/pay/cards/debit-cards"
        },
        {
            "title": "Prepaid Cards",
            "link": "https://www.hdfcbank.com/personal/pay/cards/prepaid-cards"
        },
        {
            "title": "Forex Cards",
            "link": "https://www.hdfcbank.com/personal/pay/cards/forex-cards"
        }
    ]


# ---------- CARDS FROM CATEGORY ----------
def scrape_cards_from_category(url):
    try:
        url_lower = url.lower()
        
        # Define exact, original HDFC card names matching official catalogs
        if "credit" in url_lower:
            card_titles = [
                "HDFC Infinia Credit Card",
                "HDFC Regalia Gold Credit Card",
                "HDFC Millennia Credit Card",
                "HDFC MoneyBack+ Credit Card",
                "HDFC Freedom Credit Card",
                "Swiggy HDFC Bank Credit Card",
                "Tata Neu Infinity HDFC Bank Credit Card",
                "Tata Neu Plus HDFC Bank Credit Card",
                "Indian Oil HDFC Bank Credit Card",
                "IRCTC HDFC Bank Credit Card",
                "HDFC Shoppers Stop Credit Card",
                "Marriott Bonvoy HDFC Bank Credit Card",
                "HDFC Pixel Play Credit Card",
                "HDFC Pixel Go Credit Card"
            ]
        elif "debit" in url_lower:
            card_titles = [
                "EasyShop Platinum Debit Card",
                "Millennia Debit Card",
                "EasyShop Titanium Debit Card",
                "EasyShop RuPay Premium Debit Card",
                "HDFC Regalia Debit Card",
                "EasyShop Classic Platinum Debit Card",
                "EasyShop Womans Advantage Debit Card"
            ]
        elif "prepaid" in url_lower:
            card_titles = [
                "HDFC GiftPlus Prepaid Card",
                "HDFC FoodPlus Prepaid Card",
                "HDFC Apollo Medical Prepaid Card",
                "HDFC MoneyPlus Prepaid Card",
                "HDFC SmartHub Vyapar Prepaid Card"
            ]
        elif "forex" in url_lower:
            card_titles = [
                "HDFC Multicurrency Forex Card",
                "HDFC Regalia Forex Card",
                "HDFC ISIC Student Forex Card",
                "HDFC Haj Forex Card"
            ]
        else:
            card_titles = []

        # Map to expected dict format
        cards = [{"title": title, "link": url} for title in card_titles]
        return cards

    except Exception as e:
        return [{
            "title": "Error",
            "link": "",
            "content": str(e)
        }]

def get_category_details(url):
    try:
        url_lower = url.lower()
        
        # 1. Determine category name & official URL
        if "credit" in url_lower:
            category_name = "Credit Cards"
            official_url = "https://www.hdfcbank.com/personal/pay/cards/credit-cards"
            default_desc = "HDFC Bank Credit Cards offer unparalleled privileges, reward programs, and lifestyle benefits. Designed to complement diverse spending patterns, they provide extensive benefits across online shopping, travel, dining, and fuel. Cardholders enjoy premium privileges such as complimentary airport lounge access, interest-free credit periods, secure contactless payments, and robust reward points or direct cashback programs that make every spend highly rewarding."
        elif "debit" in url_lower:
            category_name = "Debit Cards"
            official_url = "https://www.hdfcbank.com/personal/pay/cards/debit-cards"
            default_desc = "HDFC Bank Debit Cards offer direct, secure access to your bank account funds while providing a host of premium benefits and rewards. Widely accepted globally, these cards come equipped with high daily ATM withdrawal and shopping limits, comprehensive personal and air accident insurance coverage, and complimentary domestic airport lounge access. Cardholders earn attractive cashback points or reward points on point-of-sale and online transactions, making it an ideal choice for smart and secure daily money management."
        elif "prepaid" in url_lower:
            category_name = "Prepaid Cards"
            official_url = "https://www.hdfcbank.com/personal/pay/cards/prepaid-cards"
            default_desc = "HDFC Bank Prepaid Cards are secure, pre-funded payment solutions that offer unmatched convenience and budgeting control without being linked to a bank account. Ideal for personal budgeting, gifting, or corporate payroll disbursements, these reloadable or single-use cards are widely accepted at millions of outlets. Key variants include GiftPlus for gifting, FoodPlus for tax-saving employee meal allowances, and Apollo Medical for healthcare spends, all equipped with advanced security PINs and real-time transaction tracking."
        elif "forex" in url_lower:
            category_name = "Forex Cards"
            official_url = "https://www.hdfcbank.com/personal/pay/cards/forex-cards"
            default_desc = "HDFC Bank Forex Cards are the ultimate international travel companion, designed to offer cashless, secure, and hassle-free payments across the globe. By allowing you to load multiple foreign currencies (up to 22 currencies) at locked-in exchange rates, these cards protect you from unpredictable market currency fluctuations. They offer zero cross-currency markup fees on loaded currencies, complimentary international airport lounge access via Priority Pass, comprehensive travel insurance, and 24/7 global concierge assistance, ensuring a seamless travel experience."
        else:
            category_name = "Cards"
            official_url = "https://www.hdfcbank.com/personal/pay/cards"
            default_desc = "Explore HDFC Bank's wide range of payment cards tailored to fit every financial need and lifestyle choice."

        description = default_desc
        
        # 2. Try to generate a richer description using Gemini if key is available
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. rewards, travel, convenience, security).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass
                
        # 3. Get the individual card types
        cards = scrape_cards_from_category(url)
        
        return {
            "category_name": category_name,
            "description": description,
            "results": cards,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Cards",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/pay/cards"
        }

# ---------- DYNAMIC SCRAPER ----------
def scrape_dynamic(url):
    """
    Replaced Playwright with fast server-side scraping to avoid Vercel timeout issues.
    Playwright caused: browser launch delays, missing system dependencies, memory exhaustion.
    This optimized version uses BeautifulSoup only (10x faster, serverless-compatible).
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        
        if response.status_code != 200:
            return [{
                "title": "Error",
                "content": f"Failed to load page (Status {response.status_code}). Trying static content.",
                "link": url
            }]

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        paragraphs = soup.find_all("p")
        text = " ".join([p.get_text(strip=True) for p in paragraphs[:10]])

        if not text:
            # Fallback: get any text content
            text = soup.get_text(strip=True)[:1000]

        return [{
            "title": "Page Content",
            "content": text if text else "No content found",
            "link": url
        }]

    except requests.Timeout:
        return [{
            "title": "Error",
            "content": "Page load timeout. The website took too long to respond.",
            "link": url
        }]
    except Exception as e:
        return [{
            "title": "Error",
            "content": f"Scraping failed: {str(e)[:200]}",
            "link": url
        }]

# ---------- SMART HDFC SEARCH ----------
def smart_hdfc_search(query):

    # 🔥 CACHE CHECK
    if query in SEARCH_CACHE:
        return SEARCH_CACHE[query]

    try:    
        # 🔥 Search only HDFC official website
        search_query = f"site:hdfcbank.com {query}"

        search_results = serp_search(search_query)
        if isinstance(search_results, dict):
            return [search_results]

        final_results = []

        for item in search_results[:8]:

            link = item.get("link", "")

            # only official HDFC links
            if "hdfcbank.com" not in link:
                continue

            try:
                # dynamic scrape
                scraped = scrape_dynamic(link)

                content = ""

                if scraped and isinstance(scraped, list):
                    content = scraped[0].get("content", "")

                # fallback content
                if not content:
                    content = item.get("content", "")

                final_results.append({
                    "title": item.get("title", "HDFC Result"),
                    "link": link,
                    "content": content[:1500]
                })

            except Exception as e:
                continue

        # 🔥 UPDATE CACHE
        SEARCH_CACHE[query] = final_results

        return final_results

    except Exception as e:
        return [{
            "title": "Error",
            "link": "",
            "content": str(e)
        }]


# ---------- HDFC LOCAL CARDS DATABASE ----------
HDFC_CARDS_DB = {
    "Millennia Credit Card": {
        "features": [
            "5% Cashback on Amazon, Flipkart, Flight & Hotel bookings via PayZapp and SmartBuy",
            "1% Cashback on all other online & offline transactions (except fuel, wallet, etc.)",
            "8 Complimentary Domestic Airport Lounge Access per year (2 per quarter)",
            "1% Fuel Surcharge Waiver on transactions between Rs. 400 and Rs. 5,000"
        ],
        "cashback_or_rewards": "Get 5% Cashback on partner merchants (Amazon, Flipkart, Swiggy, Uber, Zomato, etc.), and 1% cashback on other spends.",
        "benefits": ["Cashback", "Lounge", "Shopping", "Dining"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/millennia-credit-card"
    },
    "Indian Oil HDFC Bank Credit Card": {
        "features": [
            "Earn up to 50 Litres of Free Fuel annually by accumulating Fuel Points",
            "5% of your transaction spend as Fuel Points at IndianOil fuel outlets (Max 250 points/month)",
            "5% of your transaction spend as Fuel Points on Grocery & Bill Payments (Max 100 points/month)",
            "1 Fuel Point for every Rs. 150 spent on all other retail transactions"
        ],
        "cashback_or_rewards": "Earn Fuel Points on fuel and daily utility spends, redeemable for free fuel at IOCL pumps via XTRAREWARDS.",
        "benefits": ["Fuel Points", "Free Fuel", "Shopping", "Utility Bills"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/indianoil-hdfc-bank-credit-card"
    },
    "Pixel Credit Card": {
        "features": [
            "Choose your own merchants: Get up to 5% Cashback on your selected choice of brands (Zomato, BookMyShow, Croma, etc.)",
            "1% Cashback on all other retail purchases and online spends",
            "100% digital/mobile-first card management directly in the PayZapp app",
            "Customise your card design virtually and pay off large transactions in easy parts/EMIs"
        ],
        "cashback_or_rewards": "Fully customisable cashback card allowing up to 5% cashback on your chosen favorite merchant brands.",
        "benefits": ["Digital First", "Cashback", "Shopping", "Customised"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/pixel-play"
    },
    "Freedom Credit Card": {
        "features": [
            "10X Reward Points on PayZapp and SmartBuy purchases",
            "5X Reward Points on Dining, Movies, Groceries, Railways, and Taxis",
            "1 Reward Point for every Rs. 150 spent on all other categories",
            "Complimentary Personal Accidental Death Insurance cover of Rs. 50,000"
        ],
        "cashback_or_rewards": "Earn 10X Reward Points on PayZapp, 5X on daily essentials, redeemable for statement credit or gifts.",
        "benefits": ["Daily Spends", "Rewards", "Dining", "Movies"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/freedom-credit-card"
    },
    "MoneyBack+ Credit Card": {
        "features": [
            "10X Reward Points on Amazon, Flipkart, BigBasket, Reliance Smart & Swiggy",
            "5X Reward Points on EMI spends at merchant locations",
            "2 Reward Points for every Rs. 150 spent on other categories",
            "Gift vouchers worth Rs. 500 on spends of Rs. 50,000 per calendar quarter"
        ],
        "cashback_or_rewards": "Earn 10X Reward Points on online shopping partners, redeemable for cashback/vouchers (1 RP = Rs. 0.25).",
        "benefits": ["Rewards", "Shopping", "Fuel", "Dining"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/moneyback-plus-credit-card"
    },
    "Regalia Gold Credit Card": {
        "features": [
            "4 Reward Points for every Rs. 150 spent on all retail spends",
            "20X Reward Points on partner brands including Nykaa, Myntra, Marks & Spencer, and Reliance Digital",
            "Complimentary Club Marriott membership and M&S/Myntra vouchers on achieving milestones",
            "12 Complimentary Domestic Lounge Access per year and 6 International Lounge Access via Priority Pass"
        ],
        "cashback_or_rewards": "Premium rewards system with 4 RP per Rs. 150 spent, redeemable for flights, hotels, and products (1 RP = up to Rs. 0.50).",
        "benefits": ["Travel Luxury", "Premium Lounge", "Rewards Points", "Hotel Dining"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/regalia-gold"
    },
    "Infinia Credit Card": {
        "features": [
            "5 Reward Points for every Rs. 150 spent on all retail transactions",
            "Up to 10X Reward Points on travel and shopping bookings via SmartBuy",
            "Unlimited Complimentary Domestic & International Airport Lounge Access for primary and add-on cardholders",
            "Complimentary 1-year Club Marriott membership and round-the-clock global concierge service",
            "Complimentary Golf Games at leading courses in India and worldwide"
        ],
        "cashback_or_rewards": "Super-premium reward structure with 1 RP = Rs. 1.00 when redeemed for flights/hotel bookings on SmartBuy.",
        "benefits": ["Super Premium", "Unlimited Lounge", "Travel", "Golf Privileges"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/infinia"
    },
    "Tata Neu Plus HDFC Bank Credit Card": {
        "features": [
            "2% NeuCoins on partner Tata brands (Tata CLIQ, BigBasket, 1mg, Croma, Air India Express, etc.)",
            "1% NeuCoins on non-Tata brands and other online/offline spends",
            "4 Complimentary Domestic Airport Lounge Access per year (1 per quarter)",
            "1% Fuel Surcharge Waiver at all refueling stations in India"
        ],
        "cashback_or_rewards": "Earn NeuCoins (1 NeuCoin = Rs. 1) that can be redeemed for shopping on the Tata Neu app.",
        "benefits": ["Shopping", "Co-Branded", "Lounge", "Dining"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/tata-neu-plus"
    },
    "Tata Neu Infinity HDFC Bank Credit Card": {
        "features": [
            "5% NeuCoins on partner Tata brands (BigBasket, Croma, Air India Express, Tata CLIQ, etc.)",
            "1.5% NeuCoins on non-Tata spends, local merchants, and other transactions",
            "8 Complimentary Domestic and 4 International Airport Lounge Access per year",
            "1% Fuel Surcharge Waiver on transaction sizes of Rs. 400 to Rs. 5,000"
        ],
        "cashback_or_rewards": "High-value NeuCoins earnings (5% on Tata spends) redeemable across all Tata services and Neu app stores.",
        "benefits": ["Shopping", "Lounge", "Travel", "Co-Branded"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/tata-neu-infinity"
    },
    "Swiggy HDFC Bank Credit Card": {
        "features": [
            "10% Cashback on Swiggy application (Food delivery, Instamart, Dineout, and Genie)",
            "5% Cashback on online shopping across key platforms (Amazon, Flipkart, Croma, Myntra, Nike, etc.)",
            "1% Cashback on other offline and online retail purchases",
            "Complimentary 3-month Swiggy One membership as a welcome benefit"
        ],
        "cashback_or_rewards": "High cashback card offering massive 10% cashback on Swiggy and 5% cashback on broad online shopping.",
        "benefits": ["Food & Dining", "Cashback", "Shopping", "Lifestyle"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/swiggy"
    },
    "EasyShop Platinum Debit Card": {
        "features": [
            "1% Cashback on purchases made at apparel, grocery, electronics, and travel stores",
            "1 Cashback Point for every Rs. 100 spent on select categories",
            "Daily Domestic ATM withdrawal limit of Rs. 1 Lakh and shopping limit of Rs. 5 Lakhs",
            "2 Complimentary Domestic Airport Lounge Access per quarter"
        ],
        "cashback_or_rewards": "Earn cashback points on every point-of-sale purchase, redeemable directly as cash in your account.",
        "benefits": ["Cashback", "Lounge Access", "ATM Limits", "Shopping"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/debit-cards/easyshop-platinum-debit-card"
    },
    "Millennia Debit Card": {
        "features": [
            "5% Cashback Points on shopping via PayZapp and SmartBuy",
            "2.5% Cashback Points on all online shopping transactions",
            "1% Cashback Points on offline spends and wallet loads",
            "4 Complimentary Domestic Airport Lounge Access per year"
        ],
        "cashback_or_rewards": "Up to 5% cashback points on online and smart buy transactions, redeemable for statement balance.",
        "benefits": ["Cashback", "Lounge Access", "Shopping", "Digital Spends"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/debit-cards/millennia-debit-card"
    },
    "EasyShop Titanium Debit Card": {
        "features": [
            "Earn reward points on shopping across apparel, groceries, and dining",
            "Daily ATM withdrawal limit of Rs. 50,000 and shopping limit of Rs. 3.5 Lakhs",
            "Zero liability protection on lost or stolen cards for unauthorized transactions",
            "Complimentary insurance cover for accidental death and baggage loss"
        ],
        "cashback_or_rewards": "Earn shopping reward points on standard spends, redeemable for catalog items.",
        "benefits": ["Rewards", "Shopping", "Insurance", "Secure Transactions"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/debit-cards/easyshop-titanium-debit-card"
    },
    "EasyShop RuPay Premium Debit Card": {
        "features": [
            "Earn reward points on utility bill payments and general spends",
            "Enjoy exclusive RuPay merchant offers, cashback, and dining discounts",
            "Daily ATM withdrawal limit of Rs. 25,000 and shopping limit of Rs. 2.75 Lakhs",
            "Complimentary domestic lounge access across key Indian airports"
        ],
        "cashback_or_rewards": "RuPay exclusive rewards and cashbacks on utility spends, plus Indian merchant benefits.",
        "benefits": ["Lounge", "RuPay Perks", "Utility Spends", "Secure"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/debit-cards/easyshop-rupay-premium"
    },
    "HDFC Regalia Debit Card": {
        "features": [
            "Earn 4 reward points for every Rs. 150 spent on all retail merchant outlets",
            "2 Complimentary Domestic Airport Lounge Access per quarter (8 per year)",
            "High daily limits: ATM withdrawals up to Rs. 1 Lakh and shopping up to Rs. 5 Lakhs",
            "Comprehensive Air Accidental Death insurance cover of up to Rs. 1 Crore"
        ],
        "cashback_or_rewards": "Earn premium reward points similar to a credit card, redeemable for air tickets and hotels.",
        "benefits": ["Premium Debit", "Lounge Access", "High Insurance", "Travel Perks"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/debit-cards/regalia-debit-card"
    },
    "HDFC Multicurrency Forex Card": {
        "features": [
            "Load up to 22 currencies on a single card to travel across multiple countries hassle-free",
            "Locked-in exchange rates protect you from market volatility during your overseas trip",
            "Complimentary insurance cover against counterfeit card fraud, baggage loss, and theft",
            "Emergency cash delivery service globally and free international ATM withdrawal offers"
        ],
        "cashback_or_rewards": "Saves up to 3.5% currency markup charges. Peace of mind with pre-loaded locked exchange rates.",
        "benefits": ["Travel Forex", "Multi-Currency", "Rate Lock", "Global Secure"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/forex-cards/multicurrency-forex-card"
    },
    "HDFC Regalia Forex Card": {
        "features": [
            "Zero cross-currency markup charges on transactions in loaded currencies",
            "Earn 4 reward points for every Rs. 150 equivalent spent internationally",
            "Complimentary international airport lounge access via Priority Pass",
            "Comprehensive emergency travel assistance and concierge services globally"
        ],
        "cashback_or_rewards": "Premium travel card with 0% currency conversion markup, offering maximum overseas savings.",
        "benefits": ["Zero Markup", "Travel", "Lounge Access", "Rewards"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/forex-cards/regalia-forex-card"
    },
    "IRCTC HDFC Bank Credit Card": {
        "features": [
            "5 Reward Points for every Rs. 100 spent on ticket bookings via IRCTC website/app",
            "5% Cashback on bookings via SmartBuy and PayZapp",
            "1% Transaction charge waiver on IRCTC website bookings",
            "4 Complimentary Domestic Railway Lounge Access per year"
        ],
        "cashback_or_rewards": "Earn specialized railway points redeemable directly for free train tickets on IRCTC.",
        "benefits": ["Railway Deals", "Cashback", "Travel Spends", "Lounge Access"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/irctc-credit-card"
    },
    "HDFC Shoppers Stop Credit Card": {
        "features": [
            "Earn up to 6 First Citizen Points on Shoppers Stop brands and retail spends",
            "Complimentary Shoppers Stop Golden Glow membership upgrade as a welcome benefit",
            "Redeem earned points instantly at any Shoppers Stop billing counter",
            "1% Fuel Surcharge Waiver at all petrol stations across India"
        ],
        "cashback_or_rewards": "Earn First Citizen points redeemable directly for apparel/accessories at Shoppers Stop stores.",
        "benefits": ["Shopping Perks", "Co-Branded", "Rewards", "Lifestyle"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/shoppers-stop"
    },
    "Marriott Bonvoy HDFC Bank Credit Card": {
        "features": [
            "Complimentary 1 Night Award voucher redeemable at Marriott Bonvoy hotels worldwide",
            "Complimentary Marriott Bonvoy Silver Elite Status upgrade",
            "Earn 8 Bonvoy Points for every Rs. 150 spent on Marriott hotel properties",
            "Earn 4 Bonvoy Points on Travel, Dining, and Entertainment spends",
            "12 Complimentary Domestic and 12 International Airport Lounge Access per year"
        ],
        "cashback_or_rewards": "Direct Marriott Bonvoy Points earnings, redeemable for luxury stays across the globe.",
        "benefits": ["Hotel Luxury", "Travel", "Lounge Access", "Co-Branded"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards/credit-cards/marriott-bonvoy"
    }
}

HDFC_ACCOUNTS_DB = {
    "Speciale Platinum Savings Account": {
        "features": [
            "Complimentary Speciale Platinum Debit Card with high ATM limits of Rs. 2 Lakhs/day",
            "Up to 50% discount on locker rentals and preferential rates on foreign exchange",
            "Dedicated Relationship Manager for comprehensive banking and investment assistance",
            "Zero banking charges on demand drafts, checkbook issuances, and outstation clearing"
        ],
        "cashback_or_rewards": "Earn up to 1% cashback on retail shopping via the Speciale Platinum Debit Card.",
        "benefits": ["Premium Banking", "Locker Discount", "Relationship Manager", "Zero Charges"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts/speciale-platinum"
    },
    "Speciale Gold Savings Account": {
        "features": [
            "Complimentary Speciale Gold Debit Card with daily ATM withdrawal limit of Rs. 1 Lakh",
            "35% discount on locker rentals and free banking transactions nationwide",
            "Dedicated Relationship Team for financial advisory and priority support",
            "High-yield interest rates on dynamic fixed deposit sweep-in integrations"
        ],
        "cashback_or_rewards": "Get attractive shopping cashback points and discount vouchers on leading merchant sites.",
        "benefits": ["Achievers Choice", "Locker Discount", "High ATM Limit", "Priority Help"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts/speciale-gold"
    },
    "Regular Savings Account": {
        "features": [
            "Easy daily banking with a highly competitive interest rate on savings balance",
            "Free access to secure NetBanking, MobileBanking, and wide ATM networks in India",
            "Complimentary international debit card with zero-liability protection",
            "Option to convert excess funds into high-yield Fixed Deposits automatically (Sweep-in)"
        ],
        "cashback_or_rewards": "Standard savings interest paid quarterly plus reward points on debit card spends.",
        "benefits": ["Signature Account", "Daily Spends", "ATM Network", "NetBanking"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts/regular-savings-account"
    },
    "Women's Advantage Savings Account": {
        "features": [
            "Special EasyShop Woman's Advantage Debit Card with Rs. 1 cashback on every Rs. 200 spent",
            "50% discount on locker rentals for the first year of account opening",
            "Complimentary Personal Accidental Death insurance cover of Rs. 10 Lakhs",
            "Highly preferential rates on automated two-wheeler and personal loans"
        ],
        "cashback_or_rewards": "Get Rs. 1 cashback for every Rs. 200 spent on apparel, dining, entertainment, and shopping.",
        "benefits": ["Women Special", "Locker Discount", "Cashback Points", "Loan Discounts"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts/womens-advantage-savings-account"
    },
    "Senior Citizens Savings Account": {
        "features": [
            "Preferential higher interest rates on domestic fixed deposit accounts",
            "Complimentary health debit card with exclusive discounts at leading pharmacies and hospitals",
            "Free priority branch banking service and dedicated elder-care helpdesk assistance",
            "Lifetime free BillPay service to securely automate all utility payments"
        ],
        "cashback_or_rewards": "Higher interest payout options (monthly or quarterly) and medical/health discount coupons.",
        "benefits": ["Senior Perks", "Higher Interest", "Health Deals", "Priority Help"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts/senior-citizens-savings-account"
    },
    "Kids Savings Account": {
        "features": [
            "Free Kids Debit Card with safe, customized daily spending limit of Rs. 2,500",
            "Complimentary Education Insurance cover of Rs. 1 Lakh for child's academic safety",
            "Option to set up automated recurring deposit sweeps starting at just Rs. 500/month",
            "Interactive savings book and simple digital platform access to teach financial values"
        ],
        "cashback_or_rewards": "Free educational gifts and vouchers on building healthy savings habits.",
        "benefits": ["Young Learners", "Academic Secure", "Recur Deposit", "Custom Debit"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts/kids-savings-account"
    }
}

HDFC_DEPOSITS_DB = {
    "Regular Fixed Deposit": {
        "features": [
            "Attractive interest rates up to 7.25% p.a. for regular citizens and up to 7.75% for senior citizens",
            "Flexible tenure options ranging from 7 days to 10 years to suit every financial goal",
            "Loan against FD facility available up to 90% of deposit amount at low interest rates",
            "Auto-renewal option to seamlessly reinvest matured deposits without any manual intervention"
        ],
        "cashback_or_rewards": "Earn up to 7.75% p.a. (senior citizens) with interest payout options: monthly, quarterly, or on maturity.",
        "benefits": ["High Returns", "Flexible Tenure", "Loan Facility", "Auto-Renewal"],
        "apply_url": "https://www.hdfcbank.com/personal/save/deposits/fixed-deposits/regular-fixed-deposit"
    },
    "5-Year Tax Saving Fixed Deposit": {
        "features": [
            "Tax deduction up to Rs. 1.5 Lakh per year under Section 80C of the Income Tax Act",
            "Competitive interest rates with a mandatory lock-in period of 5 years",
            "Available for individual and joint account holders (first holder eligible for tax benefit)",
            "Senior citizens earn an additional 0.50% interest over the standard rate"
        ],
        "cashback_or_rewards": "Save up to Rs. 46,800 in taxes annually while earning guaranteed fixed returns.",
        "benefits": ["Tax Saving", "80C Benefit", "Fixed Returns", "Senior Bonus"],
        "apply_url": "https://www.hdfcbank.com/personal/save/deposits/fixed-deposits/5-year-tax-saving-fixed-deposit"
    },
    "Regular Recurring Deposit": {
        "features": [
            "Start a recurring deposit with as little as Rs. 1,000 per month to build a savings habit",
            "Tenures from 6 months to 10 years with attractive compounded interest rates",
            "Missed installment flexibility with a nominal penalty to avoid deposit cancellation",
            "Loan against Recurring Deposit available up to 90% of the accumulated value"
        ],
        "cashback_or_rewards": "Earn compounded returns on monthly contributions, with rates equivalent to regular Fixed Deposits.",
        "benefits": ["Monthly Savings", "Flexible Tenure", "Loan Facility", "Compounded Returns"],
        "apply_url": "https://www.hdfcbank.com/personal/save/deposits/recurring-deposits/regular-recurring-deposit"
    },
    "SureSave Recurring Deposit": {
        "features": [
            "Fixed monthly installments with guaranteed payout on maturity for worry-free planning",
            "Option to link with your HDFC savings account for hassle-free auto-debit of installments",
            "Available in tenures of 12, 24, 36, 48, and 60 months for flexible savings planning",
            "Competitive interest rates with option to choose cumulative or non-cumulative payout"
        ],
        "cashback_or_rewards": "Grow your monthly savings with guaranteed, compounded returns at competitive recurring deposit rates.",
        "benefits": ["Goal-Based Savings", "Auto-Debit", "Guaranteed Returns", "Flexible Payout"],
        "apply_url": "https://www.hdfcbank.com/personal/save/deposits/recurring-deposits/suresave-recurring-deposit"
    },
    "HDFC Floating Rate Fixed Deposit": {
        "features": [
            "Interest rate linked to HDFC Bank's repo-rate benchmark for transparent market-aligned returns",
            "Benefit from rising interest rate environments with upward rate revisions",
            "Available in tenures of 1 year to 3 years with quarterly interest payout option",
            "Eligible for loan up to 90% of deposit value, same as regular Fixed Deposits"
        ],
        "cashback_or_rewards": "Dynamic interest rates that adjust with RBI benchmark changes, ensuring you always earn market-linked returns.",
        "benefits": ["Market-Linked Rate", "Quarterly Payout", "Loan Facility", "Transparent Pricing"],
        "apply_url": "https://www.hdfcbank.com/personal/save/deposits/fixed-deposits/floating-rate-fixed-deposit"
    }
}

HDFC_LOANS_DB = {
    "Personal Loan": {
        "features": [
            "Instant approval and disbursal within 10 seconds for pre-approved HDFC customers",
            "Loan amounts from Rs. 50,000 up to Rs. 40 Lakhs based on eligibility",
            "Flexible repayment tenures from 12 months to 60 months for easy EMI planning",
            "No collateral or security required — completely unsecured personal loan"
        ],
        "cashback_or_rewards": "Get pre-approved offers with lowest interest rates starting at 10.50% p.a. for eligible customers.",
        "benefits": ["Instant Disbursal", "No Collateral", "Flexible EMI", "High Loan Amount"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/personal-loan"
    },
    "Home Loan": {
        "features": [
            "Loan up to Rs. 10 Crore with repayment tenure up to 30 years for maximum affordability",
            "Attractive floating and fixed interest rates starting from 8.75% p.a.",
            "Step-up EMI facility to align repayments with your expected income growth over time",
            "Balance transfer facility to move existing home loans to HDFC at lower interest rates"
        ],
        "cashback_or_rewards": "Save lakhs with low processing fees, home loan insurance options, and balance transfer benefits.",
        "benefits": ["Long Tenure", "Low Rates", "Balance Transfer", "Step-Up EMI"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow/home-loans"
    },
    "Car Loan": {
        "features": [
            "Finance up to 100% on-road price for new cars with tenures up to 7 years",
            "Competitive interest rates starting from 8.85% p.a. with instant digital approval",
            "Pre-approved offers for existing HDFC Bank account holders for faster processing",
            "Doorstep document pickup and quick loan disbursal directly to the car dealer"
        ],
        "cashback_or_rewards": "Benefit from zero prepayment charges after 12 EMIs and special rates for select car models.",
        "benefits": ["100% Funding", "Fast Approval", "Doorstep Service", "Long Tenure"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/car-loan"
    },
    "Two Wheeler Loan": {
        "features": [
            "Finance up to 95% of the on-road price of new two-wheelers",
            "Flexible repayment tenures from 12 to 48 months at competitive interest rates",
            "Minimal documentation with quick approval turnaround for salaried and self-employed",
            "Special loan schemes and offers for premium bikes and electric two-wheelers"
        ],
        "cashback_or_rewards": "Enjoy special rate offers and zero processing fee promotions on select two-wheeler brands.",
        "benefits": ["High Funding", "Quick Approval", "EV Schemes", "Low Documentation"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/two-wheeler-loan"
    },
    "Education Loan": {
        "features": [
            "Loan up to Rs. 150 Lakhs for premier institutions abroad and up to Rs. 20 Lakhs within India",
            "Covers tuition fees, hostel, books, equipment, travel, and other education-related expenses",
            "Repayment starts 12 months after course completion or 6 months after getting a job",
            "Tax benefit on interest paid under Section 80E of the Income Tax Act"
        ],
        "cashback_or_rewards": "Flexible moratorium period during study, plus 80E tax deduction on loan interest with no upper limit.",
        "benefits": ["Study Abroad", "Tax Benefit", "Moratorium Period", "Comprehensive Coverage"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/educational-loan"
    },
    "Business Loan": {
        "features": [
            "Collateral-free business loans from Rs. 75,000 up to Rs. 50 Lakhs for SMEs and self-employed",
            "Fast processing with minimal documentation and disbursal within 4 business hours",
            "Flexible repayment tenures from 12 to 48 months to match business cash flow cycles",
            "Overdraft facility option available for dynamic short-term working capital needs"
        ],
        "cashback_or_rewards": "Competitive rates starting from 10.75% p.a. with pre-approved offers for HDFC Bank current account holders.",
        "benefits": ["No Collateral", "Quick Disbursal", "Overdraft Option", "SME Friendly"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/business-loan"
    }
}

HDFC_INSURANCE_DB = {
    "Click 2 Protect Super": {
        "features": [
            "Comprehensive term life cover with customizable payouts and benefits options",
            "Option to accelerate death benefit in case of critical illness diagnosis",
            "Flexible premium payment tenures: Single, Limited, or Regular options",
            "Tax benefits on premium paid under Section 80C and payouts under Section 10(10D)"
        ],
        "cashback_or_rewards": "High sum assured rebates and loyalty discounts on premium for non-smokers and female lives.",
        "benefits": ["Life Cover", "Tax Savings", "Customizable Payouts", "Accidental Cover"],
        "apply_url": "https://www.hdfcbank.com/personal/insure/life-insurance/term-insurance/click-2-protect-super"
    },
    "Optima Secure Health Insurance": {
        "features": [
            "Get 2X sum assured coverage from Day 1 at no extra premium cost",
            "100% renewal bonus increment for every claim-free year (up to 500% safe buffer)",
            "Zero deduction on non-medical expenses like consumables during hospitalization",
            "Cashless treatment at over 12,000+ network hospitals across India"
        ],
        "cashback_or_rewards": "Get secure double cover from day one and attractive premiums on multi-year policy terms.",
        "benefits": ["Double Cover", "Cashless network", "No Consumables charge", "Tax Savings 80D"],
        "apply_url": "https://www.hdfcbank.com/personal/insure/health-insurance/optima-secure"
    },
    "HDFC ERGO Car Insurance": {
        "features": [
            "Comprehensive coverage for own damage, third-party liability, and personal accident protection",
            "Instant online policy issuance with zero paperwork and zero physical vehicle inspection",
            "Over 8,200+ cashless garage networks across India for immediate vehicle repair",
            "Add-on options like Zero Depreciation, Engine Cover, and Roadside Assistance"
        ],
        "cashback_or_rewards": "Earn up to 50% No Claim Bonus (NCB) discount on own damage premium renewals.",
        "benefits": ["Cashless Repairs", "Zero Paperwork", "No Claim Bonus", "24x7 Support"],
        "apply_url": "https://www.hdfcbank.com/personal/insure/motor-insurance/car-insurance"
    },
    "HDFC ERGO Travel Insurance": {
        "features": [
            "Comprehensive emergency medical expenses coverage up to specified limits abroad",
            "Financial cover for baggage loss, baggage delay, and passport loss during transit",
            "Automatic extension of policy in case of flight delays or medical emergencies",
            "Cashless hospitalization network globally with round-the-clock support helpline"
        ],
        "cashback_or_rewards": "Hassle-free international travel with comprehensive protection starting at low daily rates.",
        "benefits": ["Medical Cover", "Baggage Protection", "Global Cashless", "Flight Delay Cover"],
        "apply_url": "https://www.hdfcbank.com/personal/insure/travel-insurance"
    },
    "HDFC ERGO Home Insurance": {
        "features": [
            "Complete protection for home structure and valuable contents against fire, theft, and natural disasters",
            "Flexible coverage options suited for both home owners and tenants",
            "Cover for alternative accommodation expenses in case of severe property damage",
            "Fast and simplified claims processing with specialized support team"
        ],
        "cashback_or_rewards": "Affordable premiums to secure your lifetime assets with comprehensive multi-hazard insurance protection.",
        "benefits": ["Asset Protection", "Tenant Friendly", "Disaster Cover", "Quick Claims"],
        "apply_url": "https://www.hdfcbank.com/personal/insure/home-insurance"
    }
}

HDFC_INVESTMENT_DB = {
    "HDFC Top 100 Fund": {
        "features": [
            "High-growth equity mutual fund investing majorly in top-tier large-cap companies",
            "Professional fund management aiming for long-term capital appreciation",
            "Easy SIP (Systematic Investment Plan) starting with as low as Rs. 100 per month",
            "Instant online investment, portfolio tracking, and redemption facility"
        ],
        "cashback_or_rewards": "Invest systematically to build long-term wealth leveraging top Indian market leaders.",
        "benefits": ["Large Cap Safety", "SIP Options", "Expert Management", "High Liquidity"],
        "apply_url": "https://www.hdfcbank.com/personal/invest/mutual-funds"
    },
    "Public Provident Fund (PPF)": {
        "features": [
            "Government-backed safe long-term saving scheme with guaranteed interest returns",
            "Completely tax-free interest earnings and maturity amount under EEE status",
            "Annual investment limit from minimum Rs. 500 to maximum Rs. 1.5 Lakhs per year",
            "Flexible tenure of 15 years with extension options in blocks of 5 years"
        ],
        "cashback_or_rewards": "Earn highly competitive government-fixed interest rates with complete tax exemption on returns.",
        "benefits": ["Guaranteed Safety", "Tax Free Returns", "EEE Tax Benefit", "Long-term growth"],
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts/public-provident-fund"
    },
    "National Pension System (NPS)": {
        "features": [
            "Voluntary retirement savings scheme designed for systematic long-term wealth growth",
            "Additional tax deduction benefit up to Rs. 50,000 under Section 80CCD(1B)",
            "Flexible investment choice between active management or auto lifecycle assets allocations",
            "Low-cost pension scheme managed by government-regulated pension fund managers"
        ],
        "cashback_or_rewards": "Save for a peaceful retirement with systematic wealth compounding and extra tax deductions.",
        "benefits": ["Retirement Pension", "Extra Tax Savings", "Low Cost", "Flexible Allocation"],
        "apply_url": "https://www.hdfcbank.com/personal/invest/national-pension-system"
    },
    "Sovereign Gold Bonds (SGB)": {
        "features": [
            "Government-backed bonds denominated in grams of gold, offering absolute safety",
            "Earn a guaranteed interest rate of 2.50% p.a. paid semi-annually on nominal value",
            "Complete capital gains tax exemption upon bond redemption at 8-year maturity",
            "No gold storage hassles, making it a superior digital alternative to physical gold"
        ],
        "cashback_or_rewards": "Get 2.50% p.a. guaranteed interest payouts while capitalizing on gold market appreciation.",
        "benefits": ["Sovereign Safety", "2.5% P.a. Interest", "No Storage Cost", "Capital Gain Waiver"],
        "apply_url": "https://www.hdfcbank.com/personal/invest/sovereign-gold-bonds"
    },
    "HDFC Securities Demat Account": {
        "features": [
            "3-in-1 integrated account linking savings bank, demat, and trading for seamless transactions",
            "Invest easily in equity stocks, mutual funds, IPOs, corporate bonds, and ETFs",
            "Robust research recommendations, daily market calls, and professional stock advisories",
            "Advanced digital trading platforms accessible via mobile app and website portal"
        ],
        "cashback_or_rewards": "Trade dynamically with lowest brokerage plans, integrated account tools, and seamless fund transfer.",
        "benefits": ["3-in-1 Integration", "Expert Research", "Paperless setup", "Multi-Asset Trade"],
        "apply_url": "https://www.hdfcbank.com/personal/invest/demat-account"
    }
}

HDFC_CALCULATOR_DB = {
    "Personal Loan EMI Calculator": {
        "features": [
            "Instantly calculate monthly installment payouts based on loan amount, rate, and tenure",
            "Interactive sliders for quick adjustments of principal amount and interest rates",
            "Detailed amortization schedule break-down showing principal vs interest components over time",
            "Helps plan borrowing budgets easily to avoid over-leveraging monthly finances"
        ],
        "cashback_or_rewards": "Plan your personal borrowing accurately with zero charges and real-time EMI estimations.",
        "benefits": ["Instant Output", "Detailed Amortization", "Budget Planner", "No Input Fee"],
        "apply_url": "https://www.hdfcbank.com/personal/tools-and-calculators/personal-loan-emi-calculator"
    },
    "Home Loan EMI Calculator": {
        "features": [
            "Calculate long-term EMI commitments up to 30 years instantly for precise budgeting",
            "Visualize year-on-year remaining principal balances to plan prepayment benefits",
            "Provides accurate monthly payouts inclusive of potential interest rate adjustments",
            "Seamlessly integrates with loan eligibility checkers for comprehensive home buying planning"
        ],
        "cashback_or_rewards": "Evaluate your monthly home loan EMIs and see how prepayments can save lakhs of interest.",
        "benefits": ["Long-Term Planning", "Prepayment Insights", "Accurate Breakdowns", "Property Budgeting"],
        "apply_url": "https://www.hdfcbank.com/personal/tools-and-calculators/home-loan-emi-calculator"
    },
    "SIP Mutual Fund Calculator": {
        "features": [
            "Estimate potential maturity wealth from systematic monthly mutual fund contributions",
            "Vary expected rate of return and monthly SIP amount to visualize compounding growth",
            "Compare wealth generation profiles against simple savings returns",
            "Perfect tool for planning target milestones like child education or retirement goals"
        ],
        "cashback_or_rewards": "Visualize the power of systematic compounding and plan your financial goals effortlessly.",
        "benefits": ["Compounding Wealth", "Goal Mapping", "Visual Graphs", "Discipline Saving"],
        "apply_url": "https://www.hdfcbank.com/personal/tools-and-calculators/sip-calculator"
    },
    "Fixed Deposit Calculator": {
        "features": [
            "Calculate maturity value and interest earnings instantly before booking an HDFC FD",
            "Includes separate options for cumulative growth or monthly/quarterly interest payout modes",
            "Accurately factors in special 0.50% extra interest benefits for senior citizens",
            "Helps compare return structures across different deposit tenures to maximize earnings"
        ],
        "cashback_or_rewards": "Get guaranteed, transparent maturity amounts and choose payout cycles that suit your liquidity.",
        "benefits": ["Guaranteed Estimates", "Senior Citizens Boost", "Interest Payouts", "Tenure Comparison"],
        "apply_url": "https://www.hdfcbank.com/personal/tools-and-calculators/fixed-deposit-calculator"
    },
    "Income Tax Calculator": {
        "features": [
            "Compare tax liabilities instantly between the New and Old Indian Tax Regimes",
            "Incorporate standard deductions, Section 80C investments, and 80D health premiums",
            "Get customized recommendations on potential tax saving investments for HDFC bank customers",
            "Simple, completely updated to the latest Union Budget tax slabs for maximum accuracy"
        ],
        "cashback_or_rewards": "Find out your exact tax liability and learn how to maximize HDFC saving options to cut taxes.",
        "benefits": ["Regime Comparison", "Budget Compliant", "Investment Advice", "Accurate Liability"],
        "apply_url": "https://www.hdfcbank.com/personal/tools-and-calculators/income-tax-calculator"
    }
}

HDFC_DIGITAL_BANKING_DB = {
    "HDFC NetBanking Portal": {
        "features": [
            "Over 200+ banking services accessible 24/7 from the comfort of your home or office",
            "Transfer funds securely via NEFT, RTGS, IMPS, and UPI instantly",
            "Manage and pay all utility bills, automate recharge cycles, and monitor credit card statements",
            "Open fixed deposits, buy mutual funds, apply for loans, and order cheque books digitally"
        ],
        "cashback_or_rewards": "Zero transaction charges on internet banking transfers, plus secure, instant account management.",
        "benefits": ["24x7 Access", "Secure Tokenization", "Cheque & FD Tools", "200+ Services"],
        "apply_url": "https://www.hdfcbank.com/personal/useful-links/net-banking"
    },
    "HDFC Mobile Banking App": {
        "features": [
            "Manage all your banking requirements on the go with a simple, secure mobile application",
            "Biometric login access via fingerprint or face ID for top-notch security and speed",
            "Quick account summary, custom dashboard, and instant notifications on all fund transfers",
            "In-app UPI payment integration allowing QR scans and mobile phone contacts transfers"
        ],
        "cashback_or_rewards": "Bank from anywhere securely with biometric protection and instant UPI integrations.",
        "benefits": ["Biometric Secure", "On-the-go Banking", "Instant UPI Scan", "Live Alerts"],
        "apply_url": "https://www.hdfcbank.com/personal/ways-to-bank/mobile-banking"
    },
    "PayZapp Wallet & UPI": {
        "features": [
            "One-stop payment application for instant UPI transfers, merchant scans, and mobile recharges",
            "Link multiple credit cards, debit cards, and prepaid bank cards for easy selection",
            "Single-click checkout at major partner platforms like Swiggy, BookMyShow, and Zomato",
            "Robust security features including device binding, payment pins, and instant transaction locks"
        ],
        "cashback_or_rewards": "Get attractive cashbacks, instant discount vouchers, and rewards on utility and merchant spends.",
        "benefits": ["Instant Cashback", "Multi-Card Link", "One-Click Pay", "Partner Deals"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/payment-solutions/payzapp"
    },
    "SmartBuy Offers Portal": {
        "features": [
            "Exclusive online shopping portal aggregate for HDFC Bank cardholders with curated deals",
            "Book flights, hotels, bus tickets, and buy premium brand e-gift vouchers at best rates",
            "Compare prices across top online retail portals directly inside the application",
            "Seamless reward point redemption for travel bookings and shopping items"
        ],
        "cashback_or_rewards": "Earn up to 10X Reward Points or 5% Cashback on flight, hotel, and shopping bookings.",
        "benefits": ["10X Reward Points", "Travel Bookings", "Price Comparison", "Direct Point Redeem"],
        "apply_url": "https://smartbuy.hdfcbank.com"
    },
    "WhatsApp Banking Services": {
        "features": [
            "Access key banking details instantly using safe end-to-end encrypted WhatsApp chats",
            "Instantly check account balances, request mini-statements, and locate nearest ATMs",
            "Deactivate lost credit/debit cards instantly and raise service requests without holding calls",
            "Completely free, secured service available 24/7 with instant automated responses"
        ],
        "cashback_or_rewards": "Get instant answers and essential banking summaries without needing login IDs or passwords.",
        "benefits": ["Instant Chat", "End-to-End Encrypted", "No Login Needed", "Card Hotlisting"],
        "apply_url": "https://www.hdfcbank.com/personal/ways-to-bank/social-media-banking/whatsapp-banking"
    }
}

HDFC_PAYMENTS_DB = {
    "HDFC BillPay Services": {
        "features": [
            "Securely consolidate all your utility bills, mobile connections, and dth recharges in one portal",
            "SmartPay facility to automate recurring monthly bill charges on HDFC credit cards",
            "Guaranteed payment confirmations, avoiding late fees or service disconnections",
            "Highly secure payment environment keeping card details private and transaction safe"
        ],
        "cashback_or_rewards": "Get attractive cashbacks and reward points on utility bill payments and automated spends.",
        "benefits": ["Auto-Pay Utility", "Consolidated Bills", "Zero Late Fee", "Cashback Rewards"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/bill-payments-and-recharge/billpay"
    },
    "HDFC UPI Payments": {
        "features": [
            "Create a secure custom UPI handle (e.g., @hdfcbank) linked to your primary bank accounts",
            "Scan any merchant QR code to transfer money directly from your account within seconds",
            "Request money from other UPI users securely with real-time request approvals",
            "No wallet top-ups required — direct bank-to-bank transfers under government safety guidelines"
        ],
        "cashback_or_rewards": "Make direct, zero-charge merchant payments with attractive scratch card cashbacks.",
        "benefits": ["Zero Cost Transfer", "QR Code Scan", "Direct Bank Link", "Unified Payments"],
        "apply_url": "https://www.hdfcbank.com/personal/ways-to-bank/mobile-banking/unified-payment-interface-upi"
    },
    "HDFC FASTag": {
        "features": [
            "Reloadable tag for electronic toll payments on national highways for seamless travel",
            "Direct toll debit from linked wallet, saving time and fuel at national toll plazas",
            "Instant SMS notifications on toll transactions, balances, and low threshold alerts",
            "Easy online portal for hassle-free recharge using UPI, debit cards, or net banking"
        ],
        "cashback_or_rewards": "Save fuel and time with automated cashless toll deductions and simple digital recharges.",
        "benefits": ["Cashless Toll", "Instant SMS Alerts", "Easy UPI Recharge", "National Highway Accepted"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/payment-solutions/fastag"
    },
    "SmartHub Vyapar Merchant App": {
        "features": [
            "All-in-one business application for merchants to accept payments in multiple digital modes",
            "Generate instant UPI dynamic QR codes, SMS pay links, and accept card swipe collections",
            "Monitor daily merchant settlements, track sales analytics, and manage multiple outlets",
            "Get pre-approved business overdraft limits and quick business loan eligibility directly in-app"
        ],
        "cashback_or_rewards": "Accept zero-fee UPI collections and get merchant premium discounts and low-interest loan offers.",
        "benefits": ["Multi-Mode Accept", "Same-Day Settlement", "Business Analytics", "Overdraft Facility"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/payment-solutions/smarthub-vyapar"
    },
    "Money Transfer Systems": {
        "features": [
            "Transfer funds instantly and securely via IMPS, NEFT, and RTGS transfer systems",
            "Real-time NEFT clearance with zero transaction charges for all online banking channels",
            "High-value transactions supported via RTGS for safe and fast corporate money clearing",
            "Easily add, verify, and manage payees with built-in cooling-off periods for fraud prevention"
        ],
        "cashback_or_rewards": "Clear large transaction volumes securely with absolute tracking and zero online transaction fees.",
        "benefits": ["Instant IMPS Transfer", "Zero Online NEFT Fees", "RTGS Safe Clear", "Fraud Prevention Guard"],
        "apply_url": "https://www.hdfcbank.com/personal/pay/money-transfer"
    }
}


def scrape_insurance_from_category(url):
    try:
        url_lower = url.lower()
        if "life" in url_lower:
            titles = [
                "Click 2 Protect Super"
            ]
        elif "health" in url_lower:
            titles = [
                "Optima Secure Health Insurance"
            ]
        elif "car" in url_lower or "motor" in url_lower or "vehicle" in url_lower:
            titles = [
                "HDFC ERGO Car Insurance"
            ]
        elif "travel" in url_lower:
            titles = [
                "HDFC ERGO Travel Insurance"
            ]
        elif "home" in url_lower:
            titles = [
                "HDFC ERGO Home Insurance"
            ]
        else:
            titles = [
                "Click 2 Protect Super",
                "Optima Secure Health Insurance",
                "HDFC ERGO Car Insurance",
                "HDFC ERGO Travel Insurance",
                "HDFC ERGO Home Insurance"
            ]
        return [{"title": title, "link": url} for title in titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def scrape_investment_from_category(url):
    try:
        url_lower = url.lower()
        if "mutual" in url_lower or "fund" in url_lower:
            titles = [
                "HDFC Top 100 Fund"
            ]
        elif "ppf" in url_lower or "provident" in url_lower:
            titles = ["Public Provident Fund (PPF)"]
        elif "nps" in url_lower or "pension" in url_lower:
            titles = ["National Pension System (NPS)"]
        elif "gold" in url_lower or "sgb" in url_lower:
            titles = ["Sovereign Gold Bonds (SGB)"]
        elif "demat" in url_lower or "securities" in url_lower or "trade" in url_lower:
            titles = ["HDFC Securities Demat Account"]
        else:
            titles = [
                "HDFC Top 100 Fund",
                "Public Provident Fund (PPF)",
                "National Pension System (NPS)",
                "Sovereign Gold Bonds (SGB)",
                "HDFC Securities Demat Account"
            ]
        return [{"title": title, "link": url} for title in titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def scrape_calculator_from_category(url):
    try:
        url_lower = url.lower()
        if "personal" in url_lower:
            titles = ["Personal Loan EMI Calculator"]
        elif "home" in url_lower:
            titles = ["Home Loan EMI Calculator"]
        elif "sip" in url_lower or "mutual" in url_lower:
            titles = ["SIP Mutual Fund Calculator"]
        elif "fixed" in url_lower or "fd" in url_lower:
            titles = ["Fixed Deposit Calculator"]
        elif "tax" in url_lower or "income" in url_lower:
            titles = ["Income Tax Calculator"]
        else:
            titles = [
                "Personal Loan EMI Calculator",
                "Home Loan EMI Calculator",
                "SIP Mutual Fund Calculator",
                "Fixed Deposit Calculator",
                "Income Tax Calculator"
            ]
        return [{"title": title, "link": url} for title in titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def scrape_digital_banking_from_category(url):
    try:
        url_lower = url.lower()
        if "net" in url_lower:
            titles = ["HDFC NetBanking Portal"]
        elif "mobile" in url_lower:
            titles = ["HDFC Mobile Banking App"]
        elif "payzapp" in url_lower:
            titles = ["PayZapp Wallet & UPI"]
        elif "smartbuy" in url_lower:
            titles = ["SmartBuy Offers Portal"]
        elif "whatsapp" in url_lower:
            titles = ["WhatsApp Banking Services"]
        else:
            titles = [
                "HDFC NetBanking Portal",
                "HDFC Mobile Banking App",
                "PayZapp Wallet & UPI",
                "SmartBuy Offers Portal",
                "WhatsApp Banking Services"
            ]
        return [{"title": title, "link": url} for title in titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def scrape_payments_from_category(url):
    try:
        url_lower = url.lower()
        if "bill" in url_lower:
            titles = ["HDFC BillPay Services"]
        elif "upi" in url_lower:
            titles = ["HDFC UPI Payments"]
        elif "fastag" in url_lower:
            titles = ["HDFC FASTag"]
        elif "merchant" in url_lower or "vyapar" in url_lower:
            titles = ["SmartHub Vyapar Merchant App"]
        elif "transfer" in url_lower or "money" in url_lower:
            titles = ["Money Transfer Systems"]
        else:
            titles = [
                "HDFC BillPay Services",
                "HDFC UPI Payments",
                "HDFC FASTag",
                "SmartHub Vyapar Merchant App",
                "Money Transfer Systems"
            ]
        return [{"title": title, "link": url} for title in titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def get_insurance_category_details(url):
    try:
        url_lower = url.lower()
        if "life" in url_lower:
            category_name = "Life Insurance"
            official_url = "https://www.hdfcbank.com/personal/insure/life-insurance"
            default_desc = "HDFC Life Insurance offers comprehensive plans to secure your family's future, featuring customized payouts, high terminal cover, and valuable tax savings under Section 80C."
        elif "health" in url_lower:
            category_name = "Health Insurance"
            official_url = "https://www.hdfcbank.com/personal/insure/health-insurance"
            default_desc = "HDFC ERGO Health Insurance plans offer premium safety covers with 2X sum assured benefits, 100% cashless treatment at 12,000+ hospitals, and robust Section 80D tax deductions."
        elif "car" in url_lower or "motor" in url_lower or "vehicle" in url_lower:
            category_name = "Motor Insurance"
            official_url = "https://www.hdfcbank.com/personal/insure/motor-insurance"
            default_desc = "HDFC ERGO Motor Insurance plans secure your travel on roads with comprehensive vehicle damage and third-party liabilities cover, instant online setup, and 8,200+ cashless garages."
        elif "travel" in url_lower:
            category_name = "Travel Insurance"
            official_url = "https://www.hdfcbank.com/personal/insure/travel-insurance"
            default_desc = "HDFC ERGO Travel Insurance plans secure your global trips against emergency medical costs, baggage delays, passport losses, and unexpected flight cancellations."
        elif "home" in url_lower:
            category_name = "Home Insurance"
            official_url = "https://www.hdfcbank.com/personal/insure/home-insurance"
            default_desc = "HDFC ERGO Home Insurance protects your valuable home structure and indoor assets from fire, theft, disasters, and unexpected structural damages."
        else:
            category_name = "Insurance"
            official_url = "https://www.hdfcbank.com/personal/insure"
            default_desc = "Explore HDFC Bank's multi-tier insurance policies covering life, health, travel, home, and motor vehicle protection designed to secure your lifetime assets."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. premium, coverage, claims, peace of mind).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        insurance = scrape_insurance_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": insurance,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Insurance",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/insure"
        }


def scrape_specific_insurance_details(insurance_name):
    name_lower = insurance_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "click 2 protect": "Click 2 Protect Super",
            "optima secure": "Optima Secure Health Insurance",
            "car insurance": "HDFC ERGO Car Insurance",
            "travel insurance": "HDFC ERGO Travel Insurance",
            "home insurance": "HDFC ERGO Home Insurance"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_INSURANCE_DB[db_key]
        for db_key in HDFC_INSURANCE_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_INSURANCE_DB[db_key]
        return None

    if g_key:
        try:
            search_query = f"HDFC {insurance_name} features benefits premium claims details"
            results = enhanced_scrape(search_query, "tavily")
            if not results:
                results = enhanced_scrape(search_query, "bing")

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\n\n"

            if combined_text.strip():
                prompt = f"""
                You are a financial analyst. Extract details for: "HDFC {insurance_name}"
                Search results:
                {combined_text}

                Respond in valid raw JSON format EXACTLY:
                {{
                  "features": ["feat1", "feat2", "feat3"],
                  "cashback_or_rewards": "claims/benefits/premium details sentence",
                  "benefits": ["tag1", "tag2"],
                  "apply_url": "url"
                }}
                """
                import json
                genai.configure(api_key=g_key)
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return json.loads(text)
        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"Comprehensive premium features on HDFC {insurance_name}",
            "Flexible coverage options suited to individual requirements",
            "Tax benefits on premium paid under relevant IT Acts",
            "Simplified digital claim settlement assistance"
        ],
        "cashback_or_rewards": f"Secure peace of mind with premium coverage on your HDFC {insurance_name}.",
        "benefits": ["Secure Life", "Tax Saver", "Peace of Mind", "Easy Claims"],
        "apply_url": "https://www.hdfcbank.com/personal/insure"
    }


def get_investment_category_details(url):
    try:
        url_lower = url.lower()
        if "mutual" in url_lower or "fund" in url_lower:
            category_name = "Mutual Funds"
            official_url = "https://www.hdfcbank.com/personal/invest/mutual-funds"
            default_desc = "HDFC Mutual Funds offer professional fund management targeting high long-term appreciation across large, mid, and multi-cap companies, complete with easy systematic investment plans (SIPs)."
        elif "ppf" in url_lower or "provident" in url_lower:
            category_name = "Public Provident Fund"
            official_url = "https://www.hdfcbank.com/personal/save/accounts/public-provident-fund"
            default_desc = "HDFC PPF accounts offer a highly secure, government-backed saving plan with attractive tax-free interest growth and EEE status tax exemptions on maturity values."
        elif "nps" in url_lower or "pension" in url_lower:
            category_name = "National Pension System"
            official_url = "https://www.hdfcbank.com/personal/invest/national-pension-system"
            default_desc = "HDFC NPS services offer a low-cost, systematic pension saving plan with dynamic asset allocations and extra Section 80CCD tax deduction privileges."
        elif "gold" in url_lower or "sgb" in url_lower:
            category_name = "Sovereign Gold Bonds"
            official_url = "https://www.hdfcbank.com/personal/invest/sovereign-gold-bonds"
            default_desc = "HDFC Sovereign Gold Bonds offer an absolutely safe, government-backed digital gold investment earning 2.50% p.a. guaranteed interest with zero capital gains tax at redemption."
        elif "demat" in url_lower or "securities" in url_lower or "trade" in url_lower:
            category_name = "Demat Account"
            official_url = "https://www.hdfcbank.com/personal/invest/demat-account"
            default_desc = "HDFC Securities Demat Account offers an integrated 3-in-1 platform linking banking, demat, and trading to buy stocks, IPOs, bonds, and mutual funds seamlessly."
        else:
            category_name = "Investments"
            official_url = "https://www.hdfcbank.com/personal/invest"
            default_desc = "Maximize your wealth growth with HDFC Bank's extensive range of Investment solutions, including Top Mutual Funds, tax-saving PPF & NPS, Sovereign Gold Bonds, and 3-in-1 Demat Accounts."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. wealth creation, returns, security, tax benefits).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        investment = scrape_investment_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": investment,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Investments",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/invest"
        }


def scrape_specific_investment_details(investment_name):
    name_lower = investment_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "top 100": "HDFC Top 100 Fund",
            "ppf": "Public Provident Fund (PPF)",
            "provident": "Public Provident Fund (PPF)",
            "nps": "National Pension System (NPS)",
            "pension": "National Pension System (NPS)",
            "gold bond": "Sovereign Gold Bonds (SGB)",
            "sgb": "Sovereign Gold Bonds (SGB)",
            "demat": "HDFC Securities Demat Account"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_INVESTMENT_DB[db_key]
        for db_key in HDFC_INVESTMENT_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_INVESTMENT_DB[db_key]
        return None

    if g_key:
        try:
            search_query = f"HDFC {investment_name} features benefits returns details"
            results = enhanced_scrape(search_query, "tavily")
            if not results:
                results = enhanced_scrape(search_query, "bing")

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\n\n"

            if combined_text.strip():
                prompt = f"""
                You are a financial analyst. Extract details for: "HDFC {investment_name}"
                Search results:
                {combined_text}

                Respond in valid raw JSON format EXACTLY:
                {{
                  "features": ["feat1", "feat2", "feat3"],
                  "cashback_or_rewards": "returns/rewards sentence",
                  "benefits": ["tag1", "tag2"],
                  "apply_url": "url"
                }}
                """
                import json
                genai.configure(api_key=g_key)
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return json.loads(text)
        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"Premium financial returns on HDFC {investment_name}",
            "Custom investment tenure options suited to wealth targets",
            "Safe, completely secure government or institutional backed assets",
            "Easy online paperless tracking and portfolio details tools"
        ],
        "cashback_or_rewards": f"Grow your savings systematically with HDFC {investment_name}.",
        "benefits": ["Wealth Build", "Tax Saver", "Secure Returns", "Easy Trade"],
        "apply_url": "https://www.hdfcbank.com/personal/invest"
    }


def get_calculator_category_details(url):
    try:
        url_lower = url.lower()
        if "personal" in url_lower:
            category_name = "Personal Loan Calculator"
            official_url = "https://www.hdfcbank.com/personal/tools-and-calculators/personal-loan-emi-calculator"
            default_desc = "Quickly estimate your monthly personal loan EMIs and see detailed amortization break-downs with HDFC's interactive loan calculators."
        elif "home" in url_lower:
            category_name = "Home Loan Calculator"
            official_url = "https://www.hdfcbank.com/personal/tools-and-calculators/home-loan-emi-calculator"
            default_desc = "Plan your long-term home borrowing with visual sliders, accurate EMI estimations, and interest savings through prepayment planners."
        elif "sip" in url_lower or "mutual" in url_lower:
            category_name = "SIP Calculator"
            official_url = "https://www.hdfcbank.com/personal/tools-and-calculators/sip-calculator"
            default_desc = "Forecast your mutual fund systematic investment wealth compounding over time and plan target milestones effortlessly."
        elif "fixed" in url_lower or "fd" in url_lower:
            category_name = "FD Calculator"
            official_url = "https://www.hdfcbank.com/personal/tools-and-calculators/fixed-deposit-calculator"
            default_desc = "Instantly estimate your fixed deposit maturity value, interest earnings, and senior citizens rate bonuses."
        elif "tax" in url_lower or "income" in url_lower:
            category_name = "Income Tax Calculator"
            official_url = "https://www.hdfcbank.com/personal/tools-and-calculators/income-tax-calculator"
            default_desc = "Compare New vs Old regime tax liabilities and identify top HDFC options to maximize tax savings under Budget guidelines."
        else:
            category_name = "Calculators"
            official_url = "https://www.hdfcbank.com/personal/tools-and-calculators"
            default_desc = "Explore HDFC Bank's premium suite of financial calculators covering Loan EMIs, SIP compounding, FD interest payouts, and Income Tax regimes."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. budgeting, financial planning, simple tools).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        calculator = scrape_calculator_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": calculator,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Calculators",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/tools-and-calculators"
        }


def scrape_specific_calculator_details(calculator_name):
    name_lower = calculator_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "personal loan emi": "Personal Loan EMI Calculator",
            "home loan emi": "Home Loan EMI Calculator",
            "sip calculator": "SIP Mutual Fund Calculator",
            "fixed deposit": "Fixed Deposit Calculator",
            "fd calculator": "Fixed Deposit Calculator",
            "income tax": "Income Tax Calculator"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_CALCULATOR_DB[db_key]
        for db_key in HDFC_CALCULATOR_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_CALCULATOR_DB[db_key]
        return None

    if g_key:
        try:
            search_query = f"HDFC {calculator_name} tool details features benefits"
            results = enhanced_scrape(search_query, "tavily")
            if not results:
                results = enhanced_scrape(search_query, "bing")

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\n\n"

            if combined_text.strip():
                prompt = f"""
                You are a financial analyst. Extract details for: "HDFC {calculator_name}"
                Search results:
                {combined_text}

                Respond in valid raw JSON format EXACTLY:
                {{
                  "features": ["feat1", "feat2", "feat3"],
                  "cashback_or_rewards": "benefit/returns sentence",
                  "benefits": ["tag1", "tag2"],
                  "apply_url": "url"
                }}
                """
                import json
                genai.configure(api_key=g_key)
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return json.loads(text)
        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"Interactive calculations on HDFC {calculator_name}",
            "Simple sliders to vary parameters and verify adjustments",
            "Clear graphic layouts representing amortization schedules",
            "Completely updated to comply with current government rates"
        ],
        "cashback_or_rewards": f"Plan your financial budget accurately with our free online HDFC {calculator_name}.",
        "benefits": ["Instant estimates", "Interactive Sliders", "Accurate commit", "Zero Cost"],
        "apply_url": "https://www.hdfcbank.com/personal/tools-and-calculators"
    }


def get_digital_banking_category_details(url):
    try:
        url_lower = url.lower()
        if "net" in url_lower:
            category_name = "NetBanking"
            official_url = "https://www.hdfcbank.com/personal/useful-links/net-banking"
            default_desc = "HDFC NetBanking secures over 200+ daily banking tasks, card recharges, checks management, and investment setups in a safe 24/7 web portal."
        elif "mobile" in url_lower:
            category_name = "MobileBanking"
            official_url = "https://www.hdfcbank.com/personal/ways-to-bank/mobile-banking"
            default_desc = "Bank from anywhere with the fingerprint/face-ID secure HDFC Mobile Banking application featuring quick summaries and instant transfers."
        elif "payzapp" in url_lower:
            category_name = "PayZapp App"
            official_url = "https://www.hdfcbank.com/personal/pay/payment-solutions/payzapp"
            default_desc = "HDFC PayZapp is your single-checkout UPI, mobile recharge, utility payments, and card wallet application packed with instant rewards."
        elif "smartbuy" in url_lower:
            category_name = "SmartBuy Portal"
            official_url = "https://smartbuy.hdfcbank.com"
            default_desc = "SmartBuy delivers premium shopping comparisons, flight/hotel aggregations, and high cashbacks or 10X reward multipliers on HDFC cards."
        elif "whatsapp" in url_lower:
            category_name = "WhatsApp Banking"
            official_url = "https://www.hdfcbank.com/personal/ways-to-bank/social-media-banking/whatsapp-banking"
            default_desc = "Get basic details like account balance, mini statements, and block lost credit cards instantly over encrypted WhatsApp chats."
        else:
            category_name = "Digital Banking"
            official_url = "https://www.hdfcbank.com/personal/ways-to-bank"
            default_desc = "Experience seamless, safe digital banking with HDFC's internet banking, Mobile apps, PayZapp wallets, WhatsApp assistant, and SmartBuy portal."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. convenience, digital access, security, rewards).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        banking = scrape_digital_banking_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": banking,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Digital Banking",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/ways-to-bank"
        }


def scrape_specific_digital_banking_details(banking_name):
    name_lower = banking_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "netbanking": "HDFC NetBanking Portal",
            "net banking": "HDFC NetBanking Portal",
            "mobilebanking": "HDFC Mobile Banking App",
            "mobile banking": "HDFC Mobile Banking App",
            "payzapp": "PayZapp Wallet & UPI",
            "smartbuy": "SmartBuy Offers Portal",
            "whatsapp": "WhatsApp Banking Services"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_DIGITAL_BANKING_DB[db_key]
        for db_key in HDFC_DIGITAL_BANKING_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_DIGITAL_BANKING_DB[db_key]
        return None

    if g_key:
        try:
            search_query = f"HDFC {banking_name} features benefits security details"
            results = enhanced_scrape(search_query, "tavily")
            if not results:
                results = enhanced_scrape(search_query, "bing")

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\n\n"

            if combined_text.strip():
                prompt = f"""
                You are a financial analyst. Extract details for: "HDFC {banking_name}"
                Search results:
                {combined_text}

                Respond in valid raw JSON format EXACTLY:
                {{
                  "features": ["feat1", "feat2", "feat3"],
                  "cashback_or_rewards": "returns/rewards sentence",
                  "benefits": ["tag1", "tag2"],
                  "apply_url": "url"
                }}
                """
                import json
                genai.configure(api_key=g_key)
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return json.loads(text)
        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"Easy secure login to HDFC {banking_name}",
            "Manage transfers, statements, card recharges 24/7",
            "Advanced multi-factor device binding security protection",
            "Direct link to unified smart payment gateways"
        ],
        "cashback_or_rewards": f"Enjoy seamless digital bank operations with HDFC {banking_name}.",
        "benefits": ["24x7 Control", "Top Security", "Paperless setup", "Live Updates"],
        "apply_url": "https://www.hdfcbank.com/personal/ways-to-bank"
    }


def get_payments_category_details(url):
    try:
        url_lower = url.lower()
        if "bill" in url_lower:
            category_name = "Bill Payments"
            official_url = "https://www.hdfcbank.com/personal/pay/bill-payments-and-recharge/billpay"
            default_desc = "Consolidate and automate monthly utility bill payments safely on your HDFC cards with zero late fee recharges."
        elif "upi" in url_lower:
            category_name = "UPI Payments"
            official_url = "https://www.hdfcbank.com/personal/ways-to-bank/mobile-banking/unified-payment-interface-upi"
            default_desc = "Accept or send zero-charge direct payments within seconds linking @hdfcbank handle to QR codes."
        elif "fastag" in url_lower:
            category_name = "FASTag"
            official_url = "https://www.hdfcbank.com/personal/pay/payment-solutions/fastag"
            default_desc = "Speed past toll plazas with HDFC reloadable FASTags debiting direct wallet balances instantly."
        elif "merchant" in url_lower or "vyapar" in url_lower:
            category_name = "Merchant Payments"
            official_url = "https://www.hdfcbank.com/personal/pay/payment-solutions/smarthub-vyapar"
            default_desc = "SmartHub Vyapar apps secure multi-mode payment collection, same-day settlement, and overdrafts for shop owners."
        elif "transfer" in url_lower or "money" in url_lower:
            category_name = "Money Transfer"
            official_url = "https://www.hdfcbank.com/personal/pay/money-transfer"
            default_desc = "Move funds safely across banks utilizing instant IMPS clearing, NEFT clearing, or heavy corporate RTGS."
        else:
            category_name = "Payments"
            official_url = "https://www.hdfcbank.com/personal/pay"
            default_desc = "Manage seamless daily payments with HDFC Bank's secure utility BillPay, high-speed UPI, highway FASTags, merchant app settlement, and wire transfers."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. fast payments, cashless, online setup, security).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        payments = scrape_payments_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": payments,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Payments",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/pay"
        }


def scrape_specific_payments_details(payment_name):
    name_lower = payment_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "billpay": "HDFC BillPay Services",
            "bill pay": "HDFC BillPay Services",
            "upi": "HDFC UPI Payments",
            "fastag": "HDFC FASTag",
            "smarthub": "SmartHub Vyapar Merchant App",
            "vyapar": "SmartHub Vyapar Merchant App",
            "transfer": "Money Transfer Systems",
            "money": "Money Transfer Systems"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_PAYMENTS_DB[db_key]
        for db_key in HDFC_PAYMENTS_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_PAYMENTS_DB[db_key]
        return None

    if g_key:
        try:
            search_query = f"HDFC {payment_name} details features benefits charges"
            results = enhanced_scrape(search_query, "tavily")
            if not results:
                results = enhanced_scrape(search_query, "bing")

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\n\n"

            if combined_text.strip():
                prompt = f"""
                You are a financial analyst. Extract details for: "HDFC {payment_name}"
                Search results:
                {combined_text}

                Respond in valid raw JSON format EXACTLY:
                {{
                  "features": ["feat1", "feat2", "feat3"],
                  "cashback_or_rewards": "cashback/rewards sentence",
                  "benefits": ["tag1", "tag2"],
                  "apply_url": "url"
                }}
                """
                import json
                genai.configure(api_key=g_key)
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                return json.loads(text)
        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"High speed direct processing of HDFC {payment_name}",
            "Unified payments setups linking bank cards and UPI profiles",
            "Automatic instant transaction confirmations and SMS alerts",
            "Secure encrypted transactions meeting government safety norms"
        ],
        "cashback_or_rewards": f"Fast-track your payments safely with HDFC {payment_name}.",
        "benefits": ["High-Speed Pay", "Zero Cost Options", "Automatic Alerts", "Top Encryption"],
        "apply_url": "https://www.hdfcbank.com/personal/pay"
    }


def scrape_accounts_from_category(url):
    try:
        url_lower = url.lower()
        if "savings" in url_lower:
            account_titles = [
                "Speciale Platinum Savings Account",
                "Speciale Gold Savings Account",
                "Regular Savings Account",
                "Women's Advantage Savings Account",
                "Senior Citizens Savings Account",
                "Kids Savings Account"
            ]
        elif "salary" in url_lower:
            account_titles = [
                "Premium Salary Account",
                "Regular Salary Account",
                "Defence Salary Account",
                "Classic Salary Account"
            ]
        elif "current" in url_lower:
            account_titles = [
                "Apex Current Account",
                "Max Current Account",
                "E-Commerce Current Account",
                "Regular Current Account"
            ]
        elif "rural" in url_lower:
            account_titles = [
                "HDFC Farmer Savings Account",
                "Kisan Club Current Account",
                "Shakti Savings Account"
            ]
        else:
            account_titles = []
        
        accounts = [{"title": title, "link": url} for title in account_titles]
        return accounts
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]

def get_account_category_details(url):
    try:
        url_lower = url.lower()
        if "savings" in url_lower:
            category_name = "Savings Accounts"
            official_url = "https://www.hdfcbank.com/personal/save/accounts/savings-accounts"
            default_desc = "HDFC Bank Savings Accounts are designed to keep your money safe while growing it. Tailored to fit diverse customer needs, HDFC's savings options include Speciale premium accounts for customized high-value privileges, co-branded women's savings with shopping rewards, senior citizens products offering health care deals, and kids savings accounts. These accounts feature secure NetBanking, robust interest rates, domestic lounge access options, and standard accident insurance coverage."
        elif "salary" in url_lower:
            category_name = "Salary Accounts"
            official_url = "https://www.hdfcbank.com/personal/save/accounts/salary-accounts"
            default_desc = "HDFC Bank Salary Accounts are zero-balance corporate payroll solutions designed to offer seamless daily banking and specialized financial benefits for corporate employees. Cardholders enjoy free debit cards with cashback, zero banking transaction charges, high ATM withdrawal limits, and complimentary personal accidental covers. Special segments include Defence Salary Accounts dedicated to armed forces personnel with high-value customized perks."
        elif "current" in url_lower:
            category_name = "Current Accounts"
            official_url = "https://www.hdfcbank.com/personal/save/accounts/current-accounts"
            default_desc = "HDFC Bank Current Accounts are premium business banking solutions crafted for merchants, retail shops, traders, and corporate houses. Designed to facilitate high-volume business activities, they offer dynamic cash deposit limits, instant payment and clearing services, digital banking tools, and seamless trade integrations. Account choices range from Apex high-tier corporate accounts to E-Commerce current accounts built for online businesses."
        elif "rural" in url_lower:
            category_name = "Rural Accounts"
            official_url = "https://www.hdfcbank.com/personal/save/accounts/rural-accounts"
            default_desc = "HDFC Bank Rural Accounts are custom-engineered savings and current accounts designed to meet the financial cycles of agricultural communities and rural households. Matching crop-harvest timings, these accounts offer half-yearly balance requirements, agricultural loan eligibility, and government direct benefit transfers (DBT). Variants like Kisan Club and Shakti Savings enable budget-friendly transaction tools to foster secure banking in rural India."
        else:
            category_name = "Accounts"
            official_url = "https://www.hdfcbank.com/personal/save/accounts"
            default_desc = "Explore HDFC Bank's wide range of savings, salary, current, and rural accounts designed to fit every transaction and saving need."
        
        description = default_desc
        
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. interest rates, debit cards, digital banking, and security).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass
        
        accounts = scrape_accounts_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": accounts,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Accounts",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/save/accounts"
        }

def scrape_specific_account_details(account_name):
    name_lower = account_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
    
    def get_local_db_match(name):
        keywords_mapping = {
            "speciale platinum": "Speciale Platinum Savings Account",
            "speciale gold": "Speciale Gold Savings Account",
            "regular savings": "Regular Savings Account",
            "woman's advantage": "Women's Advantage Savings Account",
            "womens advantage": "Women's Advantage Savings Account",
            "senior citizen": "Senior Citizens Savings Account",
            "kids savings": "Kids Savings Account"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_ACCOUNTS_DB[db_key]
        for db_key in HDFC_ACCOUNTS_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_ACCOUNTS_DB[db_key]
        return None

    if g_key:
        try:
            is_savings = "savings" in name_lower
            is_salary = "salary" in name_lower
            is_current = "current" in name_lower
            is_rural = "rural" in name_lower or "farmer" in name_lower or "kisan" in name_lower
            
            if is_savings:
                search_query = f"HDFC {account_name} savings account features benefits minimum balance interest rate debit card"
            elif is_salary:
                search_query = f"HDFC {account_name} salary account zero balance features benefits debit card insurance"
            elif is_current:
                search_query = f"HDFC {account_name} current account features benefits limits charges transaction limits"
            elif is_rural:
                search_query = f"HDFC {account_name} features benefits agriculture farmer rural balance"
            else:
                search_query = f"HDFC {account_name} account features benefits interest rate"
                
            results = []
            try:
                results = enhanced_scrape(search_query, "tavily")
            except:
                pass
            if not results:
                try:
                    results = enhanced_scrape(search_query, "serpapi")
                except:
                    pass
            if not results:
                try:
                    results = enhanced_scrape(search_query, "bing")
                except:
                    pass
                    
            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\nLink: {r.get('link')}\n\n"
                    
            if not combined_text.strip():
                combined_text = f"Could not find exact web results for HDFC {account_name}."
                
            prompt = f"""
            You are an expert financial researcher.
            Analyze the following search results for the bank account: "HDFC {account_name}" and extract its specific details.
            
            Search results collected:
            {combined_text}
            
            Please structure the information into a neat, valid JSON format.
            Format your response EXACTLY as a JSON object, with no markdown surrounding it (no ```json ... ``` blocks, just the raw JSON text starting with {{ and ending with }}).
            
            Fields required in JSON:
            - "features": A list of 3 to 5 key features (e.g. "Zero Balance corporate salary account", "Complimentary Debit Card with 1 Lakh limit", etc.)
            - "cashback_or_rewards": A short paragraph or sentence explaining the cashback, rewards, or interest benefits (e.g. "Earn competitive savings interest rates and 1% cashback on debit spends.")
            - "benefits": A list of up to 4 tags representing categories of benefits (e.g. ["Zero Balance", "High ATM Limit", "Locker Discount", "Insurance Cover"])
            - "apply_url": A URL to apply or read more. If you can find the actual link from the search results, use that. Otherwise, use a general HDFC accounts page link.
            
            Ensure all string lists are clean and professional.
            """
            import json
            genai.configure(api_key=g_key)
            local_model = genai.GenerativeModel(available_model)
            response = local_model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
                
            data = json.loads(text)
            
            if "features" not in data or not isinstance(data["features"], list):
                data["features"] = [f"Premium account features for HDFC {account_name}"]
            if "cashback_or_rewards" not in data:
                data["cashback_or_rewards"] = "Competitive interest rate and retail banking privileges."
            if "benefits" not in data or not isinstance(data["benefits"], list):
                data["benefits"] = ["Convenient", "Secure"]
            if "apply_url" not in data:
                data["apply_url"] = "https://www.hdfcbank.com/personal/save/accounts"
                
            return data
        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match
        
    features = [
        f"Complimentary customized debit card with high ATM withdrawal and shopping limits",
        f"Free access to HDFC Bank's secure NetBanking, MobileBanking, and vast branch network",
        "Zero liability coverage protection against unauthorized and fraudulent debit card usage",
        "Convert additional idle funds into high-yield sweep-in fixed deposits automatically"
    ]
    cashback_or_rewards = f"Earn competitive quarterly interest payouts and special shopping discount offers."
    benefits = ["ATM Access", "Secure Banking", "Interest Earn", "High Limit"]
    
    if "salary" in name_lower:
        features[0] = "Zero-balance payroll account with free high-limit debit card"
        cashback_or_rewards = "Get zero-balance convenience and complimentary personal accidental cover of up to Rs. 10 Lakhs."
        benefits = ["Zero Balance", "Accident Cover", "Payroll Special", "Debit Card"]
    elif "current" in name_lower:
        features[0] = "Dynamic cash deposit limit based on average balance, suited for large transactions"
        cashback_or_rewards = "Enjoy specialized payment integrations and merchant merchant QR codes."
        benefits = ["Business Tool", "High Deposits", "QR Merchant", "Fast Clearing"]
    elif "rural" in name_lower or "farmer" in name_lower or "kisan" in name_lower:
        features[0] = "Half-yearly minimum balance requirements designed to match your crop-harvest cycles"
        cashback_or_rewards = "Get seamless agricultural loan eligibility and direct benefits transfer (DBT) support."
        benefits = ["Agri Special", "Crop Matching", "DBT Support", "Low Balance"]

    return {
        "features": features,
        "cashback_or_rewards": cashback_or_rewards,
        "benefits": benefits,
        "apply_url": "https://www.hdfcbank.com/personal/save/accounts"
    }

# ---------- SMART FALLBACK GENERATOR ----------
def generate_fallback_details(card_name):
    name_lower = card_name.lower().strip()
    
    # 1. Determine card type (Credit/Debit/Prepaid/Forex)
    is_debit = "debit" in name_lower
    is_forex = "forex" in name_lower
    is_prepaid = "prepaid" in name_lower
    
    features = []
    benefits = []
    cashback_or_rewards = ""
    
    # 2. Check by Card Type first to completely prevent keyword collisions (e.g., Regalia Forex matching premium Credit Card)
    if is_forex:
        if "regalia" in name_lower:
            features = [
                "Zero cross-currency markup charges on international transactions in loaded currencies",
                "Earn 4 premium Reward Points for every Rs. 150 equivalent spent abroad",
                "Complimentary international airport lounge access via Priority Pass",
                "Dedicated 24/7 global concierge assistance for flight and hotel bookings"
            ]
            cashback_or_rewards = "Premium travel card with 0% currency conversion markup, offering maximum overseas savings."
            benefits = ["Zero Markup", "Travel", "Lounge Access", "Rewards"]
        elif "student" in name_lower or "isic" in name_lower:
            features = [
                "Co-branded with International Student Identity Card (ISIC) for worldwide student benefits",
                "Exclusive student discounts on global flights, accommodation, books, and dining",
                "Locked-in exchange rates protect you from market currency fluctuations during study",
                "Complimentary insurance coverage against baggage loss, card fraud, and passport loss"
            ]
            cashback_or_rewards = "Access to 1.5 lakh+ student discounts in 130+ countries and student special low markup rates."
            benefits = ["Student Deals", "Global Travel", "Rate Lock", "Discounts"]
        elif "haj" in name_lower or "riyal" in name_lower:
            features = [
                "Tailored specifically for pilgrims visiting Saudi Arabia for Haj and Umrah",
                "Pre-loaded with Saudi Riyals (SAR) to avoid local conversion charges and cash exchange hassle",
                "Locked-in exchange rate protecting you from daily currency market fluctuations",
                "Emergency backup cash delivery service in Saudi Arabia in case of lost card"
            ]
            cashback_or_rewards = "Zero hidden conversion charges and specialized pilgrimage travel protection benefits."
            benefits = ["Pilgrimage", "SAR Currency", "Travel Secure", "Emergency Cash"]
        else:
            features = [
                "Load up to 22 global currencies on a single multicurrency card for seamless travel",
                "Locked-in exchange rates protect you from market volatility during your overseas trip",
                "Complimentary insurance cover against counterfeit card fraud, baggage loss, and theft",
                "Emergency cash delivery service globally and free international ATM withdrawal offers"
            ]
            cashback_or_rewards = "Saves up to 3.5% currency markup charges. Peace of mind with pre-loaded locked exchange rates."
            benefits = ["Travel Forex", "Multi-Currency", "Rate Lock", "Global Secure"]
            
    elif is_prepaid:
        if "gift" in name_lower or "voucher" in name_lower:
            features = [
                "Perfect gifting solution accepted at over 10 lakh merchant outlets in India",
                "Non-reloadable secure card valid for up to 1 year with dynamic PIN",
                "Safe, card-based transactions to avoid cash carrying hazards",
                "Available in flexible denominations ranging from Rs. 100 to Rs. 50,000"
            ]
            cashback_or_rewards = "Get access to exclusive merchant discounts and corporate seasonal deals."
            benefits = ["Gifting", "Shopping", "Secure", "Convenient"]
        elif "food" in name_lower or "meal" in name_lower or "foodplus" in name_lower:
            features = [
                "Tax savings on meal allowances under Income Tax guidelines for corporate employees",
                "Accepted at all food outlets, restaurants, and grocery merchants across India",
                "Easy online loading by employers and real-time transaction SMS alerts",
                "Daily and monthly limit configuration via NetBanking for secure usage"
            ]
            cashback_or_rewards = "Saves tax on every dining and grocery spend (up to Rs. 3,000 monthly meal allowance)."
            benefits = ["Tax Savings", "Dining", "Corporate", "Meal Allowance"]
        elif "medical" in name_lower or "apollo" in name_lower:
            features = [
                "Tailored prepaid card for medical allowances and pharmacy spends",
                "Exclusive discounts at partner hospitals and Apollo pharmacies in India",
                "Secure payments for consultations, lab tests, and health check-ups",
                "Easy employer payouts and separate medical tax benefits support"
            ]
            cashback_or_rewards = "Get up to 10% discount on medicines and customized health packages at partner networks."
            benefits = ["Healthcare", "Medical Spends", "Discounts", "Secure"]
        else:
            features = [
                "Convenient prepaid budgeting tool to control daily personal spends",
                "Easily reloadable via HDFC NetBanking, Debit Cards, or MobileBanking",
                "Secure contactless transaction support with transaction limit controls",
                "Zero liability protection for lost or stolen prepaid cards upon immediate blocking"
            ]
            cashback_or_rewards = "Earn special retail discounts and periodic cashback offers across partner web stores."
            benefits = ["Budgeting", "Secure", "Reloadable", "Contactless"]
            
    elif is_debit:
        if "millennia" in name_lower:
            features = [
                "5% Cashback Points on shopping via PayZapp and SmartBuy",
                "2.5% Cashback Points on all online shopping transactions",
                "1% Cashback Points on offline spends and wallet loads",
                "4 Complimentary Domestic Airport Lounge Access per year"
            ]
            cashback_or_rewards = "Up to 5% cashback points on online and smart buy transactions, redeemable for statement balance."
            benefits = ["Cashback", "Lounge Access", "Shopping", "Digital Spends"]
        elif "regalia" in name_lower:
            features = [
                "Earn 4 reward points for every Rs. 150 spent on all retail merchant outlets",
                "2 Complimentary Domestic Airport Lounge Access per quarter (8 per year)",
                "High daily limits: ATM withdrawals up to Rs. 1 Lakh and shopping up to Rs. 5 Lakhs",
                "Comprehensive Air Accidental Death insurance cover of up to Rs. 1 Crore"
            ]
            cashback_or_rewards = "Earn premium reward points similar to a credit card, redeemable for air tickets and hotels."
            benefits = ["Premium Debit", "Lounge Access", "High Insurance", "Travel Perks"]
        elif "platinum" in name_lower:
            features = [
                "1% Cashback on purchases made at apparel, grocery, electronics, and travel stores",
                "1 Cashback Point for every Rs. 100 spent on select categories",
                "Daily Domestic ATM withdrawal limit of Rs. 1 Lakh and shopping limit of Rs. 5 Lakhs",
                "2 Complimentary Domestic Airport Lounge Access per quarter"
            ]
            cashback_or_rewards = "Earn cashback points on every point-of-sale purchase, redeemable directly as cash in your account."
            benefits = ["Cashback", "Lounge Access", "ATM Limits", "Shopping"]
        else:
            features = [
                f"Earn cashback points or shopping reward points on all store purchases",
                "High daily cash withdrawal limit at ATMs and high daily shopping limits",
                "Complimentary domestic airport lounge access quarterly",
                "Zero liability protection for unauthorized or fraudulent transactions"
            ]
            cashback_or_rewards = "Earn cashback points on point-of-sale retail transactions, redeemable directly as account balance."
            benefits = ["Debit Card", "Cashback", "ATM Limit", "Secure"]
            
    else:
        # Credit Card fallbacks based on keywords
        if "fuel" in name_lower or "oil" in name_lower or "petrol" in name_lower:
            features = [
                f"Earn 5% Fuel Points on all transactions at partner oil outlets",
                "1% Fuel Surcharge Waiver on transactions between Rs. 400 and Rs. 5,000",
                f"Complimentary membership to partner fuel loyalty programs",
                f"Earn 1 Fuel Point for every Rs. 150 spent on all other categories"
            ]
            cashback_or_rewards = f"Get 5% value back in the form of Fuel Points at partner pumps, redeemable for free fuel."
            benefits = ["Fuel", "Cashback", "Rewards", "Surcharge Waiver"]
            
        elif "travel" in name_lower or "irctc" in name_lower or "indigo" in name_lower or "railway" in name_lower:
            features = [
                f"Earn up to 5X reward points on all travel and booking transactions",
                "Complimentary access to domestic railway or airport lounges across India",
                "1% transaction charge waiver on booking portals",
                "Special discounts on flight tickets and hotel partner bookings"
            ]
            cashback_or_rewards = f"Earn high-value points on travel bookings redeemable directly for tickets and hotel stays."
            benefits = ["Travel", "Lounge", "Tickets", "Rewards"]
            
        elif "shoppers" in name_lower or "stop" in name_lower or "tata" in name_lower or "croma" in name_lower or "swiggy" in name_lower:
            features = [
                f"Earn up to 5% reward points on partner brand outlets and portals",
                "Additional 1% reward points on other general online and offline purchases",
                "Complimentary membership or upgrade to partner loyalty clubs",
                "Special seasonal discounts and members-only shopping deals"
            ]
            cashback_or_rewards = f"Earn co-branded points/NeuCoins/Cashback redeemable directly at partner store outlets."
            benefits = ["Shopping", "Co-Branded", "Discounts", "Cashback"]
            
        elif "millennia" in name_lower:
            features = [
                "5% Cashback on Amazon, Flipkart, flight & hotel bookings via SmartBuy",
                "1% Cashback on all other online and offline retail transactions",
                "Complimentary access to domestic airport lounges quarterly",
                "1% Fuel Surcharge Waiver on spends between Rs. 400 and Rs. 5,000"
            ]
            cashback_or_rewards = "Get 5% cashback on online partners, 1% cashback on all other online/offline spends."
            benefits = ["Cashback", "Lounge", "Shopping", "Dining"]
            
        elif "regalia" in name_lower or "gold" in name_lower or "infinia" in name_lower or "platinum" in name_lower:
            features = [
                "Premium reward points on all retail and online transactions",
                "Complimentary airport lounge access globally and within India",
                "Exclusive dining discounts and privileges at select restaurants",
                "Dedicated 24/7 global concierge service for all travel and booking needs"
            ]
            cashback_or_rewards = "Earn premium reward points redeemable for flights, luxury products, and statement balance."
            benefits = ["Premium", "Lounge", "Luxury", "Travel"]
            
        else:
            # Smart fallback tailored to HDFC credit cards
            features = [
                f"Earn attractive reward points on every transaction made with your card",
                "Enjoy fuel surcharge waiver at fuel outlets across India",
                "Convert high-value purchases into easy monthly installments (SmartEMIs)",
                "Safe, secure, and contactless payments with zero lost card liability"
            ]
            cashback_or_rewards = f"Earn competitive reward points or cashback on your HDFC {card_name} spends."
            benefits = ["Rewards", "Shopping", "EMI Option", "Secure"]
        
    return {
        "features": features,
        "cashback_or_rewards": cashback_or_rewards,
        "benefits": benefits,
        "apply_url": "https://www.hdfcbank.com/personal/pay/cards"
    }


# ---------- SPECIFIC CARD DETAILS ----------
def scrape_specific_card_details(card_name):
    name_lower = card_name.lower().strip()
    
    # 1. Check if Gemini Key is available from any casing of the environment variable
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
    
    # 2. Helper function to find a match in the local DB
    def get_local_db_match(name):
        # Keyword short-mapping
        keywords_mapping = {
            "millennia credit": "Millennia Credit Card",
            "millennia debit": "Millennia Debit Card",
            "indianoil": "Indian Oil HDFC Bank Credit Card",
            "indian oil": "Indian Oil HDFC Bank Credit Card",
            "pixel": "Pixel Credit Card",
            "freedom": "Freedom Credit Card",
            "moneyback": "MoneyBack+ Credit Card",
            "regalia gold": "Regalia Gold Credit Card",
            "infinia": "Infinia Credit Card",
            "tata neu plus": "Tata Neu Plus HDFC Bank Credit Card",
            "tata neu infinity": "Tata Neu Infinity HDFC Bank Credit Card",
            "swiggy": "Swiggy HDFC Bank Credit Card",
            "easyshop platinum": "EasyShop Platinum Debit Card",
            "easyshop titanium": "EasyShop Titanium Debit Card",
            "rupay premium": "EasyShop RuPay Premium Debit Card",
            "regalia debit": "HDFC Regalia Debit Card",
            "multicurrency": "HDFC Multicurrency Forex Card",
            "regalia forex": "HDFC Regalia Forex Card",
            "irctc": "IRCTC HDFC Bank Credit Card",
            "shoppers stop": "HDFC Shoppers Stop Credit Card",
            "marriott": "Marriott Bonvoy HDFC Bank Credit Card"
        }
        # Try exact or short keywords mapping
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_CARDS_DB[db_key]
                
        # Try direct inclusion match in full DB keys
        for db_key in HDFC_CARDS_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_CARDS_DB[db_key]
        return None

    # 3. If Gemini Key IS available, try Dynamic Search & AI Generation FIRST!
    if g_key:
        try:
            # Dynamic Search + AI Parsing - construct targeted query based on card type
            is_debit = "debit" in name_lower
            is_forex = "forex" in name_lower
            is_prepaid = "prepaid" in name_lower
            
            if is_forex:
                search_query = f"HDFC {card_name} features benefits currency markup lounge"
            elif is_prepaid:
                search_query = f"HDFC {card_name} features benefits limits load fee"
            elif is_debit:
                search_query = f"HDFC {card_name} debit card features benefits ATM limits"
            else:
                search_query = f"HDFC {card_name} credit card features benefits reward points"
            results = []
            
            try:
                results = enhanced_scrape(search_query, "tavily")
            except:
                pass
                
            if not results:
                try:
                    results = enhanced_scrape(search_query, "serpapi")
                except:
                    pass
                    
            if not results:
                try:
                    results = enhanced_scrape(search_query, "bing")
                except:
                    pass
                    
            if not results:
                try:
                    results = enhanced_scrape(search_query, "duckduckgo")
                except:
                    pass

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\nLink: {r.get('link')}\n\n"
                
            if not combined_text.strip():
                combined_text = f"Could not find exact web results for HDFC {card_name}."

            prompt = f"""
            You are an expert financial researcher.
            Analyze the following search results for the card: "HDFC {card_name}" and extract its specific details.
            
            Search results collected:
            {combined_text}
            
            Please structure the information into a neat, valid JSON format.
            Format your response EXACTLY as a JSON object, with no markdown surrounding it (no ```json ... ``` blocks, just the raw JSON text starting with {{ and ending with }}).
            
            Fields required in JSON:
            - "features": A list of 3 to 5 key features (e.g. "5% Cashback on Amazon, Flipkart, Myntra, Swiggy", etc.)
            - "cashback_or_rewards": A short paragraph or sentence explaining the cashback or reward system (e.g. "Get 5% cashback on online partners, 1% cashback on all other spends.")
            - "benefits": A list of up to 4 tags representing categories of benefits (e.g. ["Shopping", "Dining", "Travel", "Fuel"])
            - "apply_url": A URL to apply or read more. If you can find the actual link from the search results, use that. Otherwise, use a general HDFC card category link.
            
            Ensure all string lists are clean and professional.
            """
            
            import json
            # Ensure genai is configured with the active key
            genai.configure(api_key=g_key)
            local_model = genai.GenerativeModel(available_model)
            response = local_model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()
                
            data = json.loads(text)
            
            if "features" not in data or not isinstance(data["features"], list):
                data["features"] = [f"Premium card features for HDFC {card_name}"]
            if "cashback_or_rewards" not in data:
                data["cashback_or_rewards"] = "Attractive reward points or cashback on daily spends."
            if "benefits" not in data or not isinstance(data["benefits"], list):
                data["benefits"] = ["Shopping", "Lifestyle"]
            if "apply_url" not in data:
                data["apply_url"] = "https://www.hdfcbank.com/personal/pay/cards"
                
            return data
            
        except Exception as e:
            # If dynamic fetch fails, gracefully log and fall back to local DB/generator
            pass

    # 4. Fallback: Search local DB
    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    # 5. Smart rule fallback if still not found
    return generate_fallback_details(card_name)


# ---------- DEPOSITS FROM CATEGORY ----------
def scrape_deposits_from_category(url):
    try:
        url_lower = url.lower()
        if "fixed" in url_lower:
            deposit_titles = [
                "Regular Fixed Deposit",
                "5-Year Tax Saving Fixed Deposit",
                "HDFC Floating Rate Fixed Deposit"
            ]
        elif "recurring" in url_lower:
            deposit_titles = [
                "Regular Recurring Deposit",
                "SureSave Recurring Deposit"
            ]
        else:
            deposit_titles = [
                "Regular Fixed Deposit",
                "5-Year Tax Saving Fixed Deposit",
                "HDFC Floating Rate Fixed Deposit",
                "Regular Recurring Deposit",
                "SureSave Recurring Deposit"
            ]
        return [{"title": title, "link": url} for title in deposit_titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def get_deposit_category_details(url):
    try:
        url_lower = url.lower()
        if "fixed" in url_lower:
            category_name = "Fixed Deposits"
            official_url = "https://www.hdfcbank.com/personal/save/deposits/fixed-deposits"
            default_desc = "HDFC Bank Fixed Deposits offer guaranteed returns with attractive interest rates up to 7.75% p.a. for senior citizens. With tenures ranging from 7 days to 10 years, they are ideal for both short-term parking and long-term wealth creation. HDFC FDs come with benefits like loan against deposit, auto-renewal, tax-saving options under Section 80C, and flexible interest payout schedules — monthly, quarterly, or on maturity."
        elif "recurring" in url_lower:
            category_name = "Recurring Deposits"
            official_url = "https://www.hdfcbank.com/personal/save/deposits/recurring-deposits"
            default_desc = "HDFC Bank Recurring Deposits help you build a disciplined savings habit through fixed monthly contributions with compounded interest returns equivalent to Fixed Deposit rates. Starting at just Rs. 1,000 per month with tenures up to 10 years, HDFC RDs are perfect for goal-based savings. They include loan-against-RD facility, auto-debit from savings accounts, and a missed installment flexibility to keep your savings plan on track."
        else:
            category_name = "Deposits"
            official_url = "https://www.hdfcbank.com/personal/save/deposits"
            default_desc = "Explore HDFC Bank's comprehensive range of Fixed and Recurring Deposits designed to maximize your savings with guaranteed returns, tax benefits, and flexible payout options."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. interest rates, tenure, tax saving, loan facility).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        deposits = scrape_deposits_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": deposits,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Deposits",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/save/deposits"
        }


def scrape_specific_deposit_details(deposit_name):
    name_lower = deposit_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "regular fixed": "Regular Fixed Deposit",
            "tax saving": "5-Year Tax Saving Fixed Deposit",
            "5 year": "5-Year Tax Saving Fixed Deposit",
            "floating rate": "HDFC Floating Rate Fixed Deposit",
            "floating": "HDFC Floating Rate Fixed Deposit",
            "regular recurring": "Regular Recurring Deposit",
            "suresave": "SureSave Recurring Deposit",
            "sure save": "SureSave Recurring Deposit"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_DEPOSITS_DB[db_key]
        for db_key in HDFC_DEPOSITS_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_DEPOSITS_DB[db_key]
        return None

    if g_key:
        try:
            is_fd = "fixed" in name_lower
            is_rd = "recurring" in name_lower
            is_tax = "tax" in name_lower

            if is_tax:
                search_query = f"HDFC {deposit_name} 80C tax saving features interest rate lock-in period"
            elif is_fd:
                search_query = f"HDFC {deposit_name} fixed deposit interest rate tenure benefits features"
            elif is_rd:
                search_query = f"HDFC {deposit_name} recurring deposit features monthly installment interest rate"
            else:
                search_query = f"HDFC {deposit_name} deposit features benefits interest rate"

            results = []
            try:
                results = enhanced_scrape(search_query, "tavily")
            except:
                pass
            if not results:
                try:
                    results = enhanced_scrape(search_query, "serpapi")
                except:
                    pass
            if not results:
                try:
                    results = enhanced_scrape(search_query, "bing")
                except:
                    pass

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\nLink: {r.get('link')}\n\n"

            if not combined_text.strip():
                combined_text = f"Could not find exact web results for HDFC {deposit_name}."

            prompt = f"""
            You are an expert financial researcher.
            Analyze the following search results for the deposit product: "HDFC {deposit_name}" and extract its specific details.

            Search results collected:
            {combined_text}

            Please structure the information into a neat, valid JSON format.
            Format your response EXACTLY as a JSON object with no markdown (no ```json ... ``` blocks, just raw JSON starting with {{ and ending with }}).

            Fields required:
            - "features": A list of 3 to 5 key features (e.g. "Interest rate up to 7.25% p.a.", "Tenure from 7 days to 10 years", etc.)
            - "cashback_or_rewards": A short sentence explaining the returns or interest benefits
            - "benefits": A list of up to 4 benefit tags (e.g. ["High Returns", "Tax Saving", "Loan Facility", "Auto-Renewal"])
            - "apply_url": A URL to apply or read more. Use the actual HDFC link if found, otherwise use https://www.hdfcbank.com/personal/save/deposits

            Ensure all string lists are clean and professional.
            """

            import json
            genai.configure(api_key=g_key)
            local_model = genai.GenerativeModel(available_model)
            response = local_model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            data = json.loads(text)

            if "features" not in data or not isinstance(data["features"], list):
                data["features"] = [f"Key features of HDFC {deposit_name}"]
            if "cashback_or_rewards" not in data:
                data["cashback_or_rewards"] = "Earn guaranteed returns at competitive interest rates."
            if "benefits" not in data or not isinstance(data["benefits"], list):
                data["benefits"] = ["Fixed Returns", "Secure Investment"]
            if "apply_url" not in data:
                data["apply_url"] = "https://www.hdfcbank.com/personal/save/deposits"

            return data

        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"Guaranteed returns on your HDFC {deposit_name}",
            "Flexible tenure options from short to long term",
            "Loan against deposit available up to 90% of deposited value",
            "Auto-renewal and flexible interest payout options"
        ],
        "cashback_or_rewards": f"Earn competitive fixed returns on your HDFC {deposit_name} with assured payouts.",
        "benefits": ["Fixed Returns", "Secure", "Loan Facility", "Flexible Tenure"],
        "apply_url": "https://www.hdfcbank.com/personal/save/deposits"
    }


# ---------- LOANS FROM CATEGORY ----------
def scrape_loans_from_category(url):
    try:
        url_lower = url.lower()
        if "personal" in url_lower:
            loan_titles = [
                "Personal Loan",
                "Wedding Loan",
                "Travel Loan",
                "Medical Emergency Loan",
                "Home Renovation Loan"
            ]
        elif "home" in url_lower:
            loan_titles = [
                "Home Loan",
                "Home Improvement Loan",
                "Home Extension Loan",
                "Plot Loan",
                "Balance Transfer Home Loan"
            ]
        elif "car" in url_lower or "vehicle" in url_lower:
            loan_titles = [
                "Car Loan",
                "Two Wheeler Loan",
                "Used Car Loan",
                "Commercial Vehicle Loan"
            ]
        elif "education" in url_lower:
            loan_titles = [
                "Education Loan",
                "Study Abroad Loan",
                "Skill Development Loan"
            ]
        elif "business" in url_lower:
            loan_titles = [
                "Business Loan",
                "Working Capital Loan",
                "Loan Against Property",
                "MSME Loan"
            ]
        else:
            loan_titles = [
                "Personal Loan",
                "Home Loan",
                "Car Loan",
                "Two Wheeler Loan",
                "Education Loan",
                "Business Loan"
            ]
        return [{"title": title, "link": url} for title in loan_titles]
    except Exception as e:
        return [{"title": "Error", "link": "", "content": str(e)}]


def get_loan_category_details(url):
    try:
        url_lower = url.lower()
        if "personal" in url_lower:
            category_name = "Personal Loans"
            official_url = "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/personal-loan"
            default_desc = "HDFC Bank Personal Loans offer instant access to funds up to Rs. 40 Lakhs without any collateral, with approvals in as fast as 10 seconds for pre-approved customers. Designed for salaried and self-employed individuals, these loans cover medical emergencies, weddings, travel, home renovation, and more. With flexible tenures from 12 to 60 months and competitive interest rates starting at 10.50% p.a., HDFC Personal Loans are among the fastest and most reliable in India."
        elif "home" in url_lower:
            category_name = "Home Loans"
            official_url = "https://www.hdfcbank.com/personal/borrow/home-loans"
            default_desc = "HDFC Bank Home Loans help you realize your dream of owning a home with loan amounts up to Rs. 10 Crore and repayment tenures up to 30 years. Featuring competitive floating and fixed interest rates from 8.75% p.a., step-up EMI options, top-up loan facilities, and seamless balance transfer solutions, HDFC Home Loans are designed to make home ownership affordable, transparent, and hassle-free for every life stage."
        elif "car" in url_lower or "vehicle" in url_lower:
            category_name = "Vehicle Loans"
            official_url = "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/car-loan"
            default_desc = "HDFC Bank Vehicle Loans offer financing solutions for new cars, used cars, and two-wheelers with up to 100% on-road funding. With competitive rates from 8.85% p.a., instant digital approvals, doorstep document collection, and special schemes for EVs, HDFC Vehicle Loans make owning your dream vehicle effortless. Pre-approved offers and special tie-ups with leading car manufacturers ensure you get the best deals at your dealership."
        elif "education" in url_lower:
            category_name = "Education Loans"
            official_url = "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/educational-loan"
            default_desc = "HDFC Bank Education Loans support your academic ambitions with funding up to Rs. 150 Lakhs for top international universities and up to Rs. 20 Lakhs for premier Indian institutions. These loans cover tuition, hostel, equipment, and travel expenses, with a moratorium period during study and repayment beginning after job placement. Tax deduction on interest under Section 80E with no upper cap makes HDFC Education Loans a smart financial investment in your future."
        elif "business" in url_lower:
            category_name = "Business Loans"
            official_url = "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/business-loan"
            default_desc = "HDFC Bank Business Loans deliver fast, collateral-free financing up to Rs. 50 Lakhs for SMEs, traders, and self-employed professionals. With minimal documentation, same-day disbursal, and flexible tenures up to 48 months, these loans support working capital, business expansion, equipment purchase, and operational needs. Pre-approved offers for HDFC current account holders and an overdraft facility option provide maximum financial flexibility."
        else:
            category_name = "Loans"
            official_url = "https://www.hdfcbank.com/personal/borrow"
            default_desc = "Explore HDFC Bank's comprehensive loan portfolio — from Personal and Home Loans to Car, Education, and Business Loans — designed to fund every life goal with competitive rates and fast approvals."

        description = default_desc
        g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")
        if g_key:
            try:
                genai.configure(api_key=g_key)
                prompt = f"""
                You are a professional financial writer.
                Write a detailed, premium, and highly engaging summary description of HDFC {category_name}.
                Explain what they are, who they are designed for, and their general benefits (e.g. interest rates, tenure, quick approval, collateral-free).
                Keep the paragraph professional, informative, and around 80-120 words. Do not use any markdown formatting or bullet points. Just return the raw text.
                """
                local_model = genai.GenerativeModel(available_model)
                response = local_model.generate_content(prompt)
                response_text = response.text.strip()
                if response_text:
                    description = response_text
            except Exception:
                pass

        loans = scrape_loans_from_category(url)
        return {
            "category_name": category_name,
            "description": description,
            "results": loans,
            "official_url": official_url
        }
    except Exception as e:
        return {
            "category_name": "Loans",
            "description": f"Failed to get details: {str(e)}",
            "results": [],
            "official_url": "https://www.hdfcbank.com/personal/borrow"
        }


def scrape_specific_loan_details(loan_name):
    name_lower = loan_name.lower().strip()
    g_key = os.getenv("GEMINI_API_KEY") or os.getenv("Gemini_API_KEY") or os.getenv("gemini_api_key")

    def get_local_db_match(name):
        keywords_mapping = {
            "personal": "Personal Loan",
            "home loan": "Home Loan",
            "car": "Car Loan",
            "two wheeler": "Two Wheeler Loan",
            "bike": "Two Wheeler Loan",
            "education": "Education Loan",
            "study": "Education Loan",
            "business": "Business Loan",
            "msme": "Business Loan"
        }
        for kw, db_key in keywords_mapping.items():
            if kw in name:
                return HDFC_LOANS_DB[db_key]
        for db_key in HDFC_LOANS_DB.keys():
            if db_key.lower() in name or name in db_key.lower():
                return HDFC_LOANS_DB[db_key]
        return None

    if g_key:
        try:
            is_home = "home" in name_lower
            is_car = "car" in name_lower or "vehicle" in name_lower
            is_edu = "education" in name_lower or "study" in name_lower
            is_business = "business" in name_lower or "msme" in name_lower

            if is_home:
                search_query = f"HDFC {loan_name} interest rate tenure eligibility features benefits"
            elif is_car:
                search_query = f"HDFC {loan_name} interest rate on-road price funding EMI features"
            elif is_edu:
                search_query = f"HDFC {loan_name} amount moratorium 80E tax benefit features eligibility"
            elif is_business:
                search_query = f"HDFC {loan_name} collateral-free amount tenure features SME"
            else:
                search_query = f"HDFC {loan_name} interest rate features benefits eligibility"

            results = []
            try:
                results = enhanced_scrape(search_query, "tavily")
            except:
                pass
            if not results:
                try:
                    results = enhanced_scrape(search_query, "serpapi")
                except:
                    pass
            if not results:
                try:
                    results = enhanced_scrape(search_query, "bing")
                except:
                    pass

            combined_text = ""
            if results and isinstance(results, list):
                for r in results[:5]:
                    combined_text += f"Title: {r.get('title')}\nContent: {r.get('content')}\nLink: {r.get('link')}\n\n"

            if not combined_text.strip():
                combined_text = f"Could not find exact web results for HDFC {loan_name}."

            prompt = f"""
            You are an expert financial researcher.
            Analyze the following search results for the loan product: "HDFC {loan_name}" and extract its specific details.

            Search results collected:
            {combined_text}

            Please structure the information into a neat, valid JSON format.
            Format your response EXACTLY as a JSON object with no markdown (no ```json ... ``` blocks, just raw JSON starting with {{ and ending with }}).

            Fields required:
            - "features": A list of 3 to 5 key features (e.g. "Loan up to Rs. 40 Lakhs", "Tenure up to 60 months", "No collateral required", etc.)
            - "cashback_or_rewards": A short sentence explaining the interest rate or key financial benefit
            - "benefits": A list of up to 4 benefit tags (e.g. ["Quick Approval", "No Collateral", "Flexible EMI", "High Amount"])
            - "apply_url": A URL to apply or read more. Use the actual HDFC link if found, otherwise use https://www.hdfcbank.com/personal/borrow

            Ensure all string lists are clean and professional.
            """

            import json
            genai.configure(api_key=g_key)
            local_model = genai.GenerativeModel(available_model)
            response = local_model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            data = json.loads(text)

            if "features" not in data or not isinstance(data["features"], list):
                data["features"] = [f"Key features of HDFC {loan_name}"]
            if "cashback_or_rewards" not in data:
                data["cashback_or_rewards"] = "Competitive interest rates with flexible repayment options."
            if "benefits" not in data or not isinstance(data["benefits"], list):
                data["benefits"] = ["Quick Approval", "Flexible EMI"]
            if "apply_url" not in data:
                data["apply_url"] = "https://www.hdfcbank.com/personal/borrow"

            return data

        except Exception:
            pass

    local_match = get_local_db_match(name_lower)
    if local_match:
        return local_match

    return {
        "features": [
            f"Competitive interest rates on HDFC {loan_name}",
            "Flexible repayment tenures to fit your financial plan",
            "Quick approval with minimal documentation required",
            "Pre-approved offers available for existing HDFC Bank customers"
        ],
        "cashback_or_rewards": f"Benefit from competitive rates and fast disbursal on your HDFC {loan_name}.",
        "benefits": ["Quick Approval", "Flexible EMI", "Low Rates", "Minimal Docs"],
        "apply_url": "https://www.hdfcbank.com/personal/borrow"
    }