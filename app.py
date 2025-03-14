from flask import Flask, request, jsonify
import os
import openai
from flask_cors import CORS
import requests, csv, math
from io import StringIO

app = Flask(__name__)

# Approved domains exactly as they appear in the browser
approved_origins = [
    "https://www.surprisegranite.com",
    "https://www.remodely.ai"
]

# Enable CORS for all routes for the approved origins
CORS(app, resources={r"/*": {"origins": approved_origins}})

# Load OpenAI API Key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Missing OpenAI API Key. Please set it in environment variables.")
openai.api_key = OPENAI_API_KEY

def get_pricing_data():
    """
    Fetch pricing data from the published Google Sheets CSV.
    Only pull the necessary columns:
      - "Color Name"
      - "Cost/SqFt"
      - "Total/SqFt"
    """
    url = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vRWyYuTQxC8_fKNBg9_aJiB7NMFztw6mgdhN35lo8sRL45MvncRg4D217lopZxuw39j5aJTN6TP4Elh/pub?output=csv")
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise Exception("Could not fetch pricing data")
    csv_text = response.text
    csv_file = StringIO(csv_text)
    reader = csv.DictReader(csv_file)
    pricing = {}
    for row in reader:
        color = row["Color Name"].strip().lower()
        try:
            cost_sqft = float(row["Cost/SqFt"])
        except Exception:
            cost_sqft = 50.0
        try:
            color_total_sqft = float(row["Total/SqFt"])
        except Exception:
            color_total_sqft = 100.0
        pricing[color] = {"cost": cost_sqft, "total_sqft": color_total_sqft}
    return pricing

@app.route("/")
def home():
    return "<h1>Surprise Granite AI Chatbot</h1><p>Your AI assistant is ready.</p>"

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "Missing user input"}), 400

    lower_msg = user_input.lower()

    # --- Labor Data Lookup ---
    if "labor" in lower_msg or ("cost" in lower_msg and "labor" in lower_msg):
        labor_csv_url = os.getenv("LABOR_CSV_URL")
        try:
            response_csv = requests.get(labor_csv_url, timeout=10)
            response_csv.raise_for_status()
            csv_text = response_csv.text
            csv_file = StringIO(csv_text)
            # Assuming your labor CSV is tab-delimited. Adjust delimiter if needed.
            reader = csv.DictReader(csv_file, delimiter='\t')
            labor_data = list(reader)
            response_text = "Current Labor Rates:\n"
            for row in labor_data:
                # Adjust these header names if they differ in your CSV.
                code = row.get("Code", "N/A")
                service = row.get("Service Description", "N/A")
                unit = row.get("Unit", "N/A")
                rate = row.get("Rate", "N/A")
                description = row.get("Description", "")
                response_text += f"- {code}: {service} ({unit}) at {rate}"
                if description:
                    response_text += f" - {description}"
                response_text += "\n"
        except Exception as e:
            response_text = f"Error retrieving labor data: {str(e)}"
        return jsonify({"response": response_text})

    # --- Materials Data Lookup ---
    elif "material" in lower_msg or "stone" in lower_msg or ("price" in lower_msg and ("stone" in lower_msg or "material" in lower_msg)):
        materials_csv_url = os.getenv("MATERIALS_CSV_URL")
        try:
            response_csv = requests.get(materials_csv_url, timeout=10)
            response_csv.raise_for_status()
            csv_text = response_csv.text
            csv_file = StringIO(csv_text)
            # Assuming your materials CSV is tab-delimited. Adjust delimiter if needed.
            reader = csv.DictReader(csv_file, delimiter='\t')
            materials_data = list(reader)
            response_text = "Current Stone Prices:\n"
            for row in materials_data:
                color_name = row.get("Color Name", "Unknown")
                vendor_name = row.get("Vendor Name", "Unknown")
                thickness = row.get("Thickness", "N/A")
                material = row.get("Material", "N/A")
                size = row.get("size", "N/A")
                total_sqft = row.get("Total/SqFt", "N/A")
                cost_sqft = row.get("Cost/SqFt", "N/A")
                price_group = row.get("Price Group", "N/A")
                tier = row.get("Tier", "N/A")
                response_text += (f"- {color_name}: {material} from {vendor_name}, Thickness: {thickness}, "
                                  f"Size: {size}, Total SqFt: {total_sqft}, Cost/SqFt: {cost_sqft}, "
                                  f"Group: {price_group}, Tier: {tier}\n")
        except Exception as e:
            response_text = f"Error retrieving materials data: {str(e)}"
        return jsonify({"response": response_text})

    # --- Fallback: Standard GPT‑4 Chat ---
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful remodeling assistant for Surprise Granite."},
                {"role": "user", "content": user_input}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/estimate", methods=["POST", "OPTIONS"])
def estimate():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    if not data or not data.get("totalSqFt"):
        return jsonify({"error": "Missing project data"}), 400

    try:
        total_sq_ft = float(data.get("totalSqFt"))
        vendor = data.get("vendor", "default vendor").strip()
        color = data.get("color", "").strip().lower()
        demo = data.get("demo", "no").strip()
        sink_qty = float(data.get("sinkQty", 0))
        cooktop_qty = float(data.get("cooktopQty", 0))
        sink_type = data.get("sinkType", "standard").strip().lower()
        cooktop_type = data.get("cooktopType", "standard").strip().lower()
        backsplash = data.get("backsplash", "no").strip().lower()
        tile_option = float(data.get("tileOption", 0))
        edge_detail = data.get("edgeDetail", "standard").strip().lower()
        job_name = data.get("jobName", "N/A").strip()
        job_type = data.get("jobType", "fabricate and install").strip().lower()
        customer_name = data.get("customerName", "Valued Customer").strip()

        pricing_data = get_pricing_data()
        pricing_info = pricing_data.get(color, {"cost": 50, "total_sqft": 100})
        price_per_sqft = pricing_info["cost"]
        color_total_sqft = pricing_info["total_sqft"]

        material_cost = total_sq_ft * price_per_sqft
        if demo.lower() == "yes":
            material_cost *= 1.10
        sink_cost = sink_qty * (150 if sink_type == "premium" else 100)
        cooktop_cost = cooktop_qty * (160 if cooktop_type == "premium" else 120)
        backsplash_cost = total_sq_ft * (tile_option if tile_option > 0 else 20) if backsplash == "yes" else 0

        multiplier = 1.05 if edge_detail == "premium" else 1.10 if edge_detail == "custom" else 1.0
        material_cost *= multiplier

        preliminary_total = material_cost + sink_cost + cooktop_cost + backsplash_cost
        effective_sq_ft = total_sq_ft * 1.20
        slab_count = math.ceil(effective_sq_ft / color_total_sqft)
        markup = 1.35 if job_type == "slab only" else 1.30
        base_labor_rate = 45
        labor_cost = total_sq_ft * base_labor_rate * markup
        total_project_cost = preliminary_total + labor_cost
        final_cost_per_sqft = f"{(total_project_cost / total_sq_ft):.2f}" if total_sq_ft else "0.00"

        prompt = (
            f"Surprise Granite Detailed Estimate\n\n"
            f"Customer: Mr./Ms. {customer_name}\n"
            f"Job Name: {job_name}\n"
            f"Job Type: {job_type}\n"
            f"Project Area: {total_sq_ft} sq ft (with 20% waste: {effective_sq_ft:.2f} sq ft)\n"
            f"Vendor: {vendor}\n"
            f"Material (Color): {color.title()}\n"
            f"Price per Sq Ft for {color.title()}: ${price_per_sqft:.2f}\n"
            f"Material Cost: ${material_cost:.2f}\n"
            f"Sink Count: {sink_qty} ({sink_type}), Cost: ${sink_cost:.2f}\n"
            f"Cooktop Count: {cooktop_qty} ({cooktop_type}), Cost: ${cooktop_cost:.2f}\n"
            f"Backsplash Cost: ${backsplash_cost:.2f}\n"
            f"Number of Slabs Needed: {slab_count} (Each slab: {color_total_sqft} sq ft)\n"
            f"Preliminary Total (Materials): ${preliminary_total:.2f}\n"
            f"Labor Cost (at base rate ${base_labor_rate} per sq ft with markup {int((markup-1)*100)}%): ${labor_cost:.2f}\n"
            f"Total Project Cost: ${total_project_cost:.2f}\n"
            f"Final Cost Per Sq Ft: ${final_cost_per_sqft}\n\n"
            "Using the above pricing details from Surprise Granite, generate a comprehensive, professional, "
            "and detailed written estimate that includes a breakdown of material and labor costs, installation notes, "
            "and a personalized closing message addressing the customer by name. "
            "Ensure that the estimate is specific to Surprise Granite pricing and does not include generic information."
        )

        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert estimator at Surprise Granite. Provide a highly detailed and professional estimate strictly based on Surprise Granite pricing details."},
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
                "labor_cost": labor_cost,
                "preliminary_total": preliminary_total,
                "slab_count": slab_count
            },
            "estimate": narrative
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/millwork-estimate", methods=["POST", "OPTIONS"])
def millwork_estimate():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    required_fields = ["roomLength", "roomWidth", "cabinetStyle", "woodType"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Missing {field}"}), 400

    try:
        room_length = float(data.get("roomLength"))
        room_width = float(data.get("roomWidth"))
        cabinet_style = data.get("cabinetStyle").strip().lower()
        wood_type = data.get("woodType").strip().lower()

        area = room_length * room_width
        base_cost = 50.0

        style_multiplier = 1.0
        if cabinet_style == "modern":
            style_multiplier = 1.2
        elif cabinet_style == "traditional":
            style_multiplier = 1.1

        wood_multiplier = 1.0
        if wood_type == "oak":
            wood_multiplier = 1.3
        elif wood_type == "maple":
            wood_multiplier = 1.2

        estimated_cost = area * base_cost * style_multiplier * wood_multiplier

        prompt = (
            f"Millwork Estimate Details:\n"
            f"Room dimensions: {room_length} ft x {room_width} ft (Area: {area} sq ft)\n"
            f"Cabinet Style: {cabinet_style.title()}\n"
            f"Wood Type: {wood_type.title()}\n"
            f"Base cost per sq ft: ${base_cost:.2f}\n"
            f"Style Multiplier: {style_multiplier}\n"
            f"Wood Multiplier: {wood_multiplier}\n"
            f"Calculated Estimated Cost: ${estimated_cost:.2f}\n\n"
            "Please provide a comprehensive, professional, and friendly written estimate for millwork services based on the above details."
        )

        ai_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional millwork estimator."},
                {"role": "user", "content": prompt}
            ]
        )
        narrative = ai_response.choices[0].message.content

        return jsonify({
            "area": area,
            "estimatedCost": estimated_cost,
            "narrative": narrative
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
