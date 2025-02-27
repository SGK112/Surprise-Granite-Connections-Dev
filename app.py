from flask import Flask, request, jsonify
import os
import openai
from flask_cors import CORS
import requests, csv
from io import StringIO

app = Flask(__name__)

# Enable CORS for specific domains
CORS(app, resources={r"/*": {"origins": ["https://www.surprisegranite.com", "https://www.remodely.ai"]}})

# Load OpenAI API Key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API Key. Please set it in environment variables.")

# Set the API key for the OpenAI library
openai.api_key = OPENAI_API_KEY

def get_pricing_data():
    """
    Fetch pricing data from the Google Sheets CSV.
    Expected CSV columns: Material, Price
    Example rows:
       Material,Price
       granite and quartz,45
       quartzite and marble,65
       dekton and porcelain,85
    """
    url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRWyYuTQxC8_fKNBg9_aJiB7NMFztw6mgdhN35lo8sRL45MvncRg4D217lopZxuw39j5aJTN6TP4Elh/pub?output=csv"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Could not fetch pricing data")
    csv_text = response.text
    csv_file = StringIO(csv_text)
    reader = csv.DictReader(csv_file)
    pricing = {}
    for row in reader:
        material = row["Material"].strip().lower()
        price = float(row["Price"])
        pricing[material] = price
    return pricing

@app.route("/")
def home():
    return "<h1>Surprise Granite AI Chatbot</h1><p>Your AI assistant is ready.</p>"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "")
    if not user_input:
        return jsonify({"error": "Missing user input"}), 400
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful remodeling assistant."},
                {"role": "user", "content": user_input}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/estimate", methods=["POST", "OPTIONS"])
def estimate():
    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    if not data or not data.get("totalSqFt"):
        return jsonify({"error": "Missing project data"}), 400
    try:
        # Extract and process input data
        total_sq_ft = float(data.get("totalSqFt", 0))
        vendor = data.get("vendor", "default vendor")
        color = data.get("color", "default color")
        demo = data.get("demo", "no")
        
        # New fields:
        # Material type to determine price per sq ft, e.g., "granite and quartz", "quartzite and marble", "dekton and porcelain"
        material_type = data.get("materialType", "granite and quartz").strip().lower()
        # Sink and cooktop cuts are now quantities
        sink_qty = float(data.get("sinkQty", 0))
        cooktop_qty = float(data.get("cooktopQty", 0))
        sink_type = data.get("sinkType", "standard")
        cooktop_type = data.get("cooktopType", "standard")
        backsplash = data.get("backsplash", "no")
        edge_detail = data.get("edgeDetail", "standard")

        # Fetch pricing data from Google Sheets; if material_type not found, default to $50 per sq ft
        pricing_data = get_pricing_data()
        price_per_sqft = pricing_data.get(material_type, 50)
        
        # Calculate material cost based on the dynamic price per sq ft
        material_cost = total_sq_ft * price_per_sqft
        if demo.lower() == "yes":
            material_cost *= 1.10  # 10% extra if demo is required

        # Calculate sink cost: standard $100 per cut, premium $150 per cut
        if sink_type.lower() == "premium":
            sink_cost = sink_qty * 150
        else:
            sink_cost = sink_qty * 100

        # Calculate cooktop cost: standard $120 per cut, premium $160 per cut
        if cooktop_type.lower() == "premium":
            cooktop_cost = cooktop_qty * 160
        else:
            cooktop_cost = cooktop_qty * 120

        # Backsplash cost: if required, add $20 per sq ft
        if backsplash.lower() == "yes":
            backsplash_cost = total_sq_ft * 20
        else:
            backsplash_cost = 0

        # Adjust material cost for edge details
        if edge_detail.lower() == "premium":
            multiplier = 1.05
        elif edge_detail.lower() == "custom":
            multiplier = 1.10
        else:
            multiplier = 1.0
        material_cost *= multiplier

        preliminary_total = material_cost + sink_cost + cooktop_cost + backsplash_cost

        # Calculate the number of slabs needed (assuming each slab covers 100 sq ft)
        slab_size = 100  
        slab_count = int((total_sq_ft + slab_size - 1) // slab_size)

        # Build a prompt for GPT-4 to generate a detailed, professional estimate
        prompt = (
            f"Customer: {data.get('customerName', 'N/A')}\n"
            f"Project Area: {total_sq_ft} sq ft\n"
            f"Vendor: {vendor}\n"
            f"Color: {color}\n"
            f"Material Type: {material_type}\n"
            f"Demo Required: {demo}\n"
            f"Sink Cuts (Qty): {sink_qty} ({sink_type})\n"
            f"Cooktop Cuts (Qty): {cooktop_qty} ({cooktop_type})\n"
            f"Backsplash: {backsplash}\n"
            f"Edge Detail: {edge_detail}\n"
            f"Price per Sq Ft for {material_type}: ${price_per_sqft:.2f}\n"
            f"Material Cost: ${material_cost:.2f}\n"
            f"Sink Cost: ${sink_cost:.2f}\n"
            f"Cooktop Cost: ${cooktop_cost:.2f}\n"
            f"Backsplash Cost: ${backsplash_cost:.2f}\n"
            f"Preliminary Total: ${preliminary_total:.2f}\n"
            f"Slab Count: {slab_count}\n\n"
            "Generate a detailed, professional estimate that includes a breakdown of costs, "
            "installation notes, and a personalized message for the customer."
        )

        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert estimator in remodeling and construction."},
                {"role": "user", "content": prompt}
            ]
        )
        narrative = ai_response.choices[0].message.content

        return jsonify({
            "preliminary": {
                "material_cost": material_cost,
                "sink_cost": sink_cost,
                "cooktop_cost": cooktop_cost,
                "backsplash_cost": backsplash_cost,
                "preliminary_total": preliminary_total,
                "slab_count": slab_count
            },
            "estimate": narrative
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
