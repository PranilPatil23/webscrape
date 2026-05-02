from flask import Flask, request, jsonify, send_file, render_template
from scraper import detect_input, fix_url, scrape_static, enhanced_scrape, ai_summary, deep_research
from utils import save_to_excel, save_to_json, save_to_word
from requests_html import HTMLSession
import os
import uuid

app = Flask(__name__)

# Folder to store generated files
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# ---------- HOME ----------
@app.route("/")
def home():
    return render_template("index.html")


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
       
        # 🔥 Description from SerpAPI results
        description = ""

        for item in result:
            if item.get("content"):
                description += item["content"] + " "

        description = description[:500]  # limit length

        return jsonify({
            "summary": description,
            "results": result
        })

    except Exception as e:
        return jsonify({"error": f"Scrape Error: {str(e)}"}), 500

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
        # Unique filename (important for multiple users)
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

def scrape_dynamic(url):
    session = HTMLSession()
    r = session.get(url)
    r.html.render(timeout=20)

    paragraphs = r.html.find("p")
    content = " ".join([p.text for p in paragraphs[:10]])

    return [{
        "title": "Dynamic Page",
        "content": content,
        "link": url
    }]
    result = scrape_static(url)

    if not result or "Content not available" in result[0]["content"]:
        result = scrape_dynamic(url)                    
        
# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True, port=5000)