from flask import Flask, request, jsonify, send_file, render_template
from scraper import (
    detect_input, fix_url, scrape_static, enhanced_scrape, ai_summary,
    deep_research, scrape_hdfc_categories, scrape_cards_from_category,
    scrape_dynamic, smart_hdfc_search, scrape_specific_card_details,
    get_category_details, get_account_category_details, scrape_specific_account_details,
    get_deposit_category_details, scrape_specific_deposit_details,
    get_loan_category_details, scrape_specific_loan_details,
    get_insurance_category_details, scrape_specific_insurance_details,
    get_investment_category_details, scrape_specific_investment_details,
    get_calculator_category_details, scrape_specific_calculator_details,
    get_digital_banking_category_details, scrape_specific_digital_banking_details,
    get_payments_category_details, scrape_specific_payments_details
)
from utils import save_to_excel, save_to_json, save_to_word
import os
import uuid

app = Flask(__name__)

# Folder to store generated files
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# ---------- ERROR HANDLERS FOR VERCEL ----------
@app.errorhandler(500)
def handle_500_error(error):
    """Catches unhandled exceptions and returns proper JSON response"""
    return jsonify({
        "error": "Internal server error. Please try again.",
        "details": str(error)[:200]
    }), 500


@app.errorhandler(Exception)
def handle_all_errors(error):
    """Catches any uncaught exception to prevent function invocation failure"""
    import traceback
    return jsonify({
        "error": "An unexpected error occurred",
        "details": str(error)[:200]
    }), 500


# ---------- HOME ----------
@app.route("/")
def home():
    return render_template("index.html")


# ---------- HEALTH CHECK ----------
@app.route("/health", methods=["GET"])
def health_check():
    """Vercel health check endpoint"""
    return jsonify({
        "status": "ok",
        "service": "Web Scraper API",
        "version": "1.0.0"
    }), 200


# ---------- SCRAPE ----------
@app.route("/scrape", methods=["POST"])
def scrape():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No input provided"}), 400

    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Provide a URL, keyword, or sentence"}), 400

    try:
        # 🔥 HDFC Category and Cards Routing
        query_lower = query.lower().strip()
        clean_query = query_lower.replace("hdfc", "").replace("bank", "").replace("  ", " ").strip()
        normalized = clean_query.rstrip("s")
        
        is_generic_cards_query = normalized in [
            "card", "cards", "hdfc card", "hdfc cards",
            "credit", "credit card", "credit cards",
            "debit", "debit card", "debit cards",
            "prepaid", "prepaid card", "prepaid cards",
            "forex", "forex card", "forex cards"
        ]
        
        if is_generic_cards_query:
            categories = [
                {"title": "Credit Cards", "link": "https://www.hdfcbank.com/personal/pay/cards/credit-cards"},
                {"title": "Debit Cards", "link": "https://www.hdfcbank.com/personal/pay/cards/debit-cards"},
                {"title": "Prepaid Cards", "link": "https://www.hdfcbank.com/personal/pay/cards/prepaid-cards"},
                {"title": "Forex Cards", "link": "https://www.hdfcbank.com/personal/pay/cards/forex-cards"}
            ]
            return jsonify({
                "type": "category",
                "results": categories,
                "summary": "Welcome to HDFC Card Hub! Click on any category below to view full details, card types, and official portals."
            })

        is_generic_accounts_query = normalized in [
            "account", "accounts", "hdfc account", "hdfc accounts",
            "saving", "savings", "salary", "current", "rural"
        ]

        if is_generic_accounts_query:
            categories = [
                {"title": "Savings Accounts", "link": "https://www.hdfcbank.com/personal/save/accounts/savings-accounts"},
                {"title": "Salary Accounts", "link": "https://www.hdfcbank.com/personal/save/accounts/salary-accounts"},
                {"title": "Current Accounts", "link": "https://www.hdfcbank.com/personal/save/accounts/current-accounts"},
                {"title": "Rural Accounts", "link": "https://www.hdfcbank.com/personal/save/accounts/rural-accounts"}
            ]
            return jsonify({
                "type": "account_category",
                "results": categories,
                "summary": "Explore HDFC Bank's range of premium savings, corporate salary, high-volume current, and harvest-aligned rural accounts. Each is designed to deliver seamless digital banking, robust interest growth, secure transaction limits, and customized lifestyle benefits."
            })

        is_generic_deposits_query = normalized in [
            "deposit", "deposits", "hdfc deposit", "hdfc deposits",
            "fixed deposit", "fixed deposits", "fd", "recurring deposit",
            "recurring deposits", "rd", "tax saving deposit", "tax saving fd"
        ]

        if is_generic_deposits_query:
            categories = [
                {"title": "Fixed Deposits", "link": "https://www.hdfcbank.com/personal/save/deposits/fixed-deposits"},
                {"title": "Recurring Deposits", "link": "https://www.hdfcbank.com/personal/save/deposits/recurring-deposits"}
            ]
            return jsonify({
                "type": "deposit_category",
                "results": categories,
                "summary": "Grow your money safely with HDFC Bank's Fixed and Recurring Deposits. Earn guaranteed returns up to 7.75% p.a. with flexible tenures, tax-saving options, and loan-against-deposit facilities."
            })

        is_generic_loans_query = normalized in [
            "loan", "loans", "hdfc loan", "hdfc loans",
            "personal loan", "home loan", "car loan", "vehicle loan",
            "education loan", "business loan", "two wheeler loan", "bike loan"
        ]

        if is_generic_loans_query:
            categories = [
                {"title": "Personal Loans", "link": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/personal-loan"},
                {"title": "Home Loans", "link": "https://www.hdfcbank.com/personal/borrow/home-loans"},
                {"title": "Vehicle Loans", "link": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/car-loan"},
                {"title": "Education Loans", "link": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/educational-loan"},
                {"title": "Business Loans", "link": "https://www.hdfcbank.com/personal/borrow/loan-for-every-need/business-loan"}
            ]
            return jsonify({
                "type": "loan_category",
                "results": categories,
                "summary": "HDFC Bank offers a complete suite of loan products — from instant Personal Loans and affordable Home Loans to Car, Education, and Business Loans. Get quick approvals, competitive rates, and flexible EMIs tailored to your financial needs."
            })

        is_generic_insurance_query = normalized in [
            "insurance", "insurances", "hdfc insurance", "hdfc insurances",
            "life insurance", "health insurance", "motor insurance", "car insurance",
            "travel insurance", "home insurance"
        ]

        if is_generic_insurance_query:
            categories = [
                {"title": "Life Insurance", "link": "https://www.hdfcbank.com/personal/insure/life-insurance"},
                {"title": "Health Insurance", "link": "https://www.hdfcbank.com/personal/insure/health-insurance"},
                {"title": "Motor Insurance", "link": "https://www.hdfcbank.com/personal/insure/motor-insurance"},
                {"title": "Travel Insurance", "link": "https://www.hdfcbank.com/personal/insure/travel-insurance"},
                {"title": "Home Insurance", "link": "https://www.hdfcbank.com/personal/insure/home-insurance"}
            ]
            return jsonify({
                "type": "insurance_category",
                "results": categories,
                "summary": "Protect what matters most with HDFC Bank's comprehensive Insurance plans. Choose from custom life insurance covers, 100% cashless health insurance networks, auto damage motor insurance, global travel insurance, and secure home protection."
            })

        is_generic_investments_query = normalized in [
            "investment", "investments", "hdfc investment", "hdfc investments",
            "invest", "mutual fund", "mutual funds", "ppf", "nps", "sgb", "demat"
        ]

        if is_generic_investments_query:
            categories = [
                {"title": "Mutual Funds", "link": "https://www.hdfcbank.com/personal/invest/mutual-funds"},
                {"title": "Public Provident Fund (PPF)", "link": "https://www.hdfcbank.com/personal/save/accounts/public-provident-fund"},
                {"title": "National Pension System (NPS)", "link": "https://www.hdfcbank.com/personal/invest/national-pension-system"},
                {"title": "Sovereign Gold Bonds (SGB)", "link": "https://www.hdfcbank.com/personal/invest/sovereign-gold-bonds"},
                {"title": "Demat Account", "link": "https://www.hdfcbank.com/personal/invest/demat-account"}
            ]
            return jsonify({
                "type": "investment_category",
                "results": categories,
                "summary": "Grow your wealth and secure your future with HDFC Bank's high-yielding investment plans. Explore expert-managed Mutual Funds, tax-free PPF, voluntary NPS retirement plans, interest-bearing Sovereign Gold Bonds, and 3-in-1 integrated Demat Accounts."
            })

        is_generic_calculators_query = normalized in [
            "calculator", "calculators", "hdfc calculator", "hdfc calculators",
            "emi calculator", "sip calculator", "fd calculator", "tax calculator"
        ]

        if is_generic_calculators_query:
            categories = [
                {"title": "Personal Loan EMI Calculator", "link": "https://www.hdfcbank.com/personal/tools-and-calculators/personal-loan-emi-calculator"},
                {"title": "Home Loan EMI Calculator", "link": "https://www.hdfcbank.com/personal/tools-and-calculators/home-loan-emi-calculator"},
                {"title": "SIP Mutual Fund Calculator", "link": "https://www.hdfcbank.com/personal/tools-and-calculators/sip-calculator"},
                {"title": "Fixed Deposit Calculator", "link": "https://www.hdfcbank.com/personal/tools-and-calculators/fixed-deposit-calculator"},
                {"title": "Income Tax Calculator", "link": "https://www.hdfcbank.com/personal/tools-and-calculators/income-tax-calculator"}
            ]
            return jsonify({
                "type": "calculator_category",
                "results": categories,
                "summary": "Plan your financial budgets effortlessly using HDFC Bank's interactive online calculators. Instantly calculate loan EMIs, project mutual fund SIP growth, estimate FD interest returns, and compare income tax regime liabilities."
            })

        is_generic_digital_banking_query = normalized in [
            "digital banking", "netbanking", "net banking", "mobilebanking", "mobile banking",
            "payzapp", "smartbuy", "whatsapp banking"
        ]

        if is_generic_digital_banking_query:
            categories = [
                {"title": "NetBanking Portal", "link": "https://www.hdfcbank.com/personal/useful-links/net-banking"},
                {"title": "Mobile Banking App", "link": "https://www.hdfcbank.com/personal/ways-to-bank/mobile-banking"},
                {"title": "PayZapp Wallet & UPI", "link": "https://www.hdfcbank.com/personal/pay/payment-solutions/payzapp"},
                {"title": "SmartBuy Offers Portal", "link": "https://smartbuy.hdfcbank.com"},
                {"title": "WhatsApp Banking Services", "link": "https://www.hdfcbank.com/personal/ways-to-bank/social-media-banking/whatsapp-banking"}
            ]
            return jsonify({
                "type": "digital_banking_category",
                "results": categories,
                "summary": "Experience smart, secure, 24/7 banking on the go. Utilize HDFC NetBanking for over 200+ services, the Mobile Banking App with biometric security, the all-in-one PayZapp UPI wallet, SmartBuy exclusive portals, and instant WhatsApp chat banking."
            })

        is_generic_payments_query = normalized in [
            "payment", "payments", "pay", "billpay", "bill pay", "upi", "fastag", "smarthub", "money transfer"
        ]

        if is_generic_payments_query:
            categories = [
                {"title": "BillPay Services", "link": "https://www.hdfcbank.com/personal/pay/bill-payments-and-recharge/billpay"},
                {"title": "UPI Payments", "link": "https://www.hdfcbank.com/personal/ways-to-bank/mobile-banking/unified-payment-interface-upi"},
                {"title": "FASTag toll", "link": "https://www.hdfcbank.com/personal/pay/payment-solutions/fastag"},
                {"title": "SmartHub Vyapar Merchant", "link": "https://www.hdfcbank.com/personal/pay/payment-solutions/smarthub-vyapar"},
                {"title": "Money Transfer Systems", "link": "https://www.hdfcbank.com/personal/pay/money-transfer"}
            ]
            return jsonify({
                "type": "payments_category",
                "results": categories,
                "summary": "Make seamless, secure daily payments with HDFC Bank. Easily consolidate utility bills on AutoPay, scan and pay via zero-charge UPI, reload FASTag toll passes, settle merchant app sales, and execute secure wire transfers."
            })

        if "hdfc" in query.lower():
            result = smart_hdfc_search(query)
            summary = ai_summary(result, query)
            return jsonify({
                "type": "normal",
                "results": result,
                "summary": summary
            })

        input_type = detect_input(query)

        if input_type == "url":
            result = scrape_static(query)
        else:
            engine = data.get("engine", "duckduckgo")

            if engine == "deep":
                result = deep_research(query)
            else:   
                result = enhanced_scrape(query, engine) 

        if isinstance(result, dict) and "error" in result:
            return jsonify(result), 500
       
        # 🔥 Description from results
        description = ""

        for item in result:
            if item.get("content"):
                description += item["content"] + " "

        description = description[:500]

        return jsonify({
            "type": "normal",
            "summary": description,
            "results": result
        })

    except Exception as e:
        return jsonify({"error": f"Scrape Error: {str(e)}"}), 500


# ---------- CATEGORY → CARDS ----------
@app.route("/category-cards", methods=["POST"])
def category_cards():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        details = get_category_details(url)
        return jsonify({
            "type": "cards",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CARD DETAILS ----------
@app.route("/card-details", methods=["POST"])
def card_details():
    data = request.get_json()
    card_name = data.get("card_name")
    url = data.get("url")

    if not url and not card_name:
        return jsonify({"error": "No URL or Card Name provided"}), 400

    try:
        if card_name:
            # Dynamically fetch specific card details (features, cashback, benefits, apply link)
            details = scrape_specific_card_details(card_name)
            return jsonify(details)

        try:
            result = scrape_static(url)

            # 🔥 fallback if blocked (slightly improved condition)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)

        except:
            result = scrape_dynamic(url)        

        return jsonify({
            "description": result[0]["content"],
            "link": url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → ACCOUNTS ----------
@app.route("/category-accounts", methods=["POST"])
def category_accounts():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        details = get_account_category_details(url)
        return jsonify({
            "type": "accounts",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- ACCOUNT DETAILS ----------
@app.route("/account-details", methods=["POST"])
def account_details():
    data = request.get_json()
    account_name = data.get("account_name")
    url = data.get("url")

    if not url and not account_name:
        return jsonify({"error": "No URL or Account Name provided"}), 400

    try:
        if account_name:
            details = scrape_specific_account_details(account_name)
            return jsonify(details)

        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)        

        return jsonify({
            "description": result[0]["content"],
            "link": url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- DOWNLOAD ----------
@app.route("/download", methods=["POST"])
def download():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data received"}), 400

    results = data.get("results", [])
    summary = data.get("summary", "")
    format_type = data.get("format", "excel")

    if not results:
        return jsonify({"error": "No results to download"}), 400

    try:
        file_id = str(uuid.uuid4())

        if format_type == "excel":
            file_path = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.xlsx")
            save_to_excel(results, file_path)

        elif format_type == "json":
            file_path = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.json")
            save_to_json(results, file_path)

        elif format_type == "word":
            file_path = os.path.join(DOWNLOAD_FOLDER, f"{file_id}.docx")
            save_to_word(results, summary, file_path)

        else:
            return jsonify({"error": "Invalid format"}), 400

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        return jsonify({"error": f"Download Error: {str(e)}"}), 500


# ---------- CATEGORY → DEPOSITS ----------
@app.route("/category-deposits", methods=["POST"])
def category_deposits():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        details = get_deposit_category_details(url)
        return jsonify({
            "type": "deposits",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- DEPOSIT DETAILS ----------
@app.route("/deposit-details", methods=["POST"])
def deposit_details():
    data = request.get_json()
    deposit_name = data.get("deposit_name")
    url = data.get("url")

    if not url and not deposit_name:
        return jsonify({"error": "No URL or Deposit Name provided"}), 400

    try:
        if deposit_name:
            details = scrape_specific_deposit_details(deposit_name)
            return jsonify(details)

        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)

        return jsonify({
            "description": result[0]["content"],
            "link": url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → LOANS ----------
@app.route("/category-loans", methods=["POST"])
def category_loans():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        details = get_loan_category_details(url)
        return jsonify({
            "type": "loans",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- LOAN DETAILS ----------
@app.route("/loan-details", methods=["POST"])
def loan_details():
    data = request.get_json()
    loan_name = data.get("loan_name")
    url = data.get("url")

    if not url and not loan_name:
        return jsonify({"error": "No URL or Loan Name provided"}), 400

    try:
        if loan_name:
            details = scrape_specific_loan_details(loan_name)
            return jsonify(details)

        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)

        return jsonify({
            "description": result[0]["content"],
            "link": url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → INSURANCE ----------
@app.route("/category-insurance", methods=["POST"])
def category_insurance():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        details = get_insurance_category_details(url)
        return jsonify({
            "type": "insurance",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- INSURANCE DETAILS ----------
@app.route("/insurance-details", methods=["POST"])
def insurance_details():
    data = request.get_json()
    insurance_name = data.get("insurance_name")
    url = data.get("url")
    if not url and not insurance_name:
        return jsonify({"error": "No URL or Insurance Name provided"}), 400
    try:
        if insurance_name:
            details = scrape_specific_insurance_details(insurance_name)
            return jsonify(details)
        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)
        return jsonify({
            "description": result[0]["content"],
            "link": url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → INVESTMENT ----------
@app.route("/category-investment", methods=["POST"])
def category_investment():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        details = get_investment_category_details(url)
        return jsonify({
            "type": "investment",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- INVESTMENT DETAILS ----------
@app.route("/investment-details", methods=["POST"])
def investment_details():
    data = request.get_json()
    investment_name = data.get("investment_name")
    url = data.get("url")
    if not url and not investment_name:
        return jsonify({"error": "No URL or Investment Name provided"}), 400
    try:
        if investment_name:
            details = scrape_specific_investment_details(investment_name)
            return jsonify(details)
        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)
        return jsonify({
            "description": result[0]["content"],
            "link": url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → CALCULATOR ----------
@app.route("/category-calculator", methods=["POST"])
def category_calculator():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        details = get_calculator_category_details(url)
        return jsonify({
            "type": "calculator",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CALCULATOR DETAILS ----------
@app.route("/calculator-details", methods=["POST"])
def calculator_details():
    data = request.get_json()
    calculator_name = data.get("calculator_name")
    url = data.get("url")
    if not url and not calculator_name:
        return jsonify({"error": "No URL or Calculator Name provided"}), 400
    try:
        if calculator_name:
            details = scrape_specific_calculator_details(calculator_name)
            return jsonify(details)
        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)
        return jsonify({
            "description": result[0]["content"],
            "link": url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → DIGITAL BANKING ----------
@app.route("/category-digital-banking", methods=["POST"])
def category_digital_banking():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        details = get_digital_banking_category_details(url)
        return jsonify({
            "type": "digital_banking",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- DIGITAL BANKING DETAILS ----------
@app.route("/digital-banking-details", methods=["POST"])
def digital_banking_details():
    data = request.get_json()
    banking_name = data.get("banking_name")
    url = data.get("url")
    if not url and not banking_name:
        return jsonify({"error": "No URL or Banking Name provided"}), 400
    try:
        if banking_name:
            details = scrape_specific_digital_banking_details(banking_name)
            return jsonify(details)
        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)
        return jsonify({
            "description": result[0]["content"],
            "link": url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- CATEGORY → PAYMENTS ----------
@app.route("/category-payments", methods=["POST"])
def category_payments():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        details = get_payments_category_details(url)
        return jsonify({
            "type": "payments",
            "category_name": details["category_name"],
            "description": details["description"],
            "results": details["results"],
            "official_url": details["official_url"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- PAYMENTS DETAILS ----------
@app.route("/payments-details", methods=["POST"])
def payments_details():
    data = request.get_json()
    payment_name = data.get("payment_name")
    url = data.get("url")
    if not url and not payment_name:
        return jsonify({"error": "No URL or Payment Name provided"}), 400
    try:
        if payment_name:
            details = scrape_specific_payments_details(payment_name)
            return jsonify(details)
        try:
            result = scrape_static(url)
            if not result or "Status code" in result[0]["content"] or "Error" in result[0]["title"]:
                result = scrape_dynamic(url)
        except:
            result = scrape_dynamic(url)
        return jsonify({
            "description": result[0]["content"],
            "link": url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True, port=5000)