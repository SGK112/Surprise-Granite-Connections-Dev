/**
 * server.js
 *
 * Node.js/Express server for Surprise Granite Chatbot Backend with OpenAI integration.
 */

require("dotenv").config();
const express = require("express");
const Papa = require("papaparse");
const axios = require("axios");
const multer = require("multer");
const cors = require("cors");
const helmet = require("helmet");
const { Configuration, OpenAIApi } = require("openai"); // <-- For OpenAI
const path = require("path");
const fs = require("fs");

// CSV URLs (from Google Sheets)
const LABOR_CSV_URL =
  "https://docs.google.com/spreadsheets/d/e/2PACX-1vSX3Bh_n3s_HKEjZW20hNxj0hmpeoIc27sVJ1TjIvRzenPy0Np11J-KFtHgeUsu5NuVOv9zaWMA1LCU/pub?output=csv";
const MATERIALS_CSV_URL =
  "https://docs.google.com/spreadsheets/d/e/2PACX-1vRWyYuTQxC8_fKNBg9_aJiB7NMFztw6mgdhN35lo8sRL45MvncRg4D217lopZxuw39j5aJTN6TP4Elh/pub?output=csv";

// TOS URL (Google Doc)
const TOS_URL =
  "https://docs.google.com/document/d/e/2PACX-1vQh9AFnt8idWXCl9kFBruaZYhZfPokPBjuFla8aebX5CzPhrEkVLV_iKqv49rQJbIcNypQRAvJLwLHB/pub";

// Google Business Page URL
const GOOGLE_BUSINESS_PAGE = "https://g.co/kgs/Y9XGbpd";

// Thryv Zapier Token
const THRYV_ZAPIER_TOKEN =
  "3525b8f45f2822007b06b67d39a8b48aae9e9b3b67c3071569048d6850ba341d";

// EmailJS configuration (set via .env or fallback values)
const EMAILJS_SERVICE_ID = "service_jmjjix9";
const EMAILJS_TEMPLATE_ID = process.env.EMAILJS_TEMPLATE_ID || "template_chatHistory";
const EMAILJS_USER_ID = process.env.EMAILJS_USER_ID || "user_placeholder";

// OpenAI Configuration
const OPENAI_API_KEY = process.env.OPENAI_API_KEY; // Ensure this is set in Render
if (!OPENAI_API_KEY) {
  console.warn("Warning: OPENAI_API_KEY is not set. The /api/chat endpoint will fail.");
}
const openaiConfig = new Configuration({
  apiKey: OPENAI_API_KEY,
});
const openai = new OpenAIApi(openaiConfig);

// In-memory storage for CSV data.
let laborData = [];
let materialsData = [];

const app = express();

// Use explicit CORS options (adjust origin if needed)
const corsOptions = {
  origin: "https://www.surprisegranite.com", // or "*", or your front-end domain
  optionsSuccessStatus: 200,
};
app.use(cors(corsOptions));
app.use(helmet());
app.use(express.json());

// Set up Multer for handling image uploads (files stored in ./uploads)
const upload = multer({ dest: "uploads/" });

// Business info & instructions.
const BUSINESS_INFO = {
  name: "Surprise Granite",
  address: "11560 N Dysart Rd. #112, Surprise, AZ 85379",
  phone: "(602) 833-3189",
  email: "info@surprisegranite.com",
  googleBusiness: GOOGLE_BUSINESS_PAGE,
};

const SYSTEM_INSTRUCTIONS = `
You are CARI, the Surprise Granite Design Assistant.
You must:
- Greet customers politely and remain in character as "CARI."
- Provide accurate countertop estimates (if asked) using a 35% markup and a 20% waste factor, plus labor from CSV data. 
- For images, analyze stone type or blueprint details if user asks, or disclaim if uncertain.
- For scheduling, reference Thryv Zap token: ${THRYV_ZAPIER_TOKEN}.
- Surprise Granite Info:
  Name: ${BUSINESS_INFO.name}
  Address: ${BUSINESS_INFO.address}
  Phone: ${BUSINESS_INFO.phone}
  Email: ${BUSINESS_INFO.email}
  Google: ${BUSINESS_INFO.googleBusiness}
- TOS available at /api/get-tos.
`;

/**
 * Utility function to fetch and parse a CSV file from a URL.
 */
async function fetchAndParseCSV(url) {
  try {
    const response = await axios.get(url);
    const csvString = response.data;
    return new Promise((resolve, reject) => {
      Papa.parse(csvString, {
        header: true,
        skipEmptyLines: true,
        complete: (results) => {
          if (results.errors.length) {
            return reject(results.errors);
          }
          resolve(results.data);
        },
      });
    });
  } catch (error) {
    console.error("Error fetching CSV:", error);
    throw error;
  }
}

/**
 * Load labor and materials CSV data at startup.
 */
async function loadCSVData() {
  try {
    console.log("Loading labor CSV...");
    laborData = await fetchAndParseCSV(LABOR_CSV_URL);
    console.log(`Labor data loaded: ${laborData.length} rows`);

    console.log("Loading materials CSV...");
    materialsData = await fetchAndParseCSV(MATERIALS_CSV_URL);
    console.log(`Materials data loaded: ${materialsData.length} rows`);
  } catch (err) {
    console.error("Error loading CSV data:", err);
  }
}

/**
 * GET /api/get-tos
 * Fetches TOS content from the Google Doc.
 */
app.get("/api/get-tos", async (req, res) => {
  try {
    const response = await axios.get(TOS_URL);
    res.json({ tosHtml: response.data });
  } catch (error) {
    console.error("Error fetching TOS:", error);
    res.status(500).json({ error: "Unable to fetch TOS." });
  }
});

/**
 * GET /api/get-business-info
 * Returns business contact information.
 */
app.get("/api/get-business-info", (req, res) => {
  res.json(BUSINESS_INFO);
});

/**
 * GET /api/get-instructions
 * Returns guidelines for the assistant.
 */
app.get("/api/get-instructions", (req, res) => {
  res.json({ instructions: SYSTEM_INSTRUCTIONS });
});

/**
 * POST /api/schedule
 * Placeholder endpoint for scheduling via Thryv Zapier.
 */
app.post("/api/schedule", (req, res) => {
  const { clientName, desiredDate } = req.body;
  if (!clientName || !desiredDate) {
    return res.status(400).json({ error: "Missing 'clientName' or 'desiredDate'." });
  }
  // TODO: Integrate with Zapier using THRYV_ZAPIER_TOKEN.
  res.json({
    message: "Scheduling request received! We'll follow up soon.",
    zapierTokenUsed: THRYV_ZAPIER_TOKEN,
    clientName,
    desiredDate,
  });
});

/**
 * POST /api/get-estimate
 * Computes countertop estimates:
 * 1. Base sq ft = (lengthInches * widthInches) / 144.
 * 2. Final sq ft = base sq ft * 1.2 (adds 20% waste).
 * 3. Optional: Slab count = ceil(final sq ft / (slab area)).
 * 4. Material cost (with 35% markup) and labor cost are added.
 */
app.post("/api/get-estimate", (req, res) => {
  try {
    const {
      material,
      lengthInches,
      widthInches,
      slabLengthInches,
      slabWidthInches,
      laborKey,
    } = req.body;

    if (!material || !lengthInches || !widthInches) {
      return res.status(400).json({
        error: "Missing 'material', 'lengthInches', or 'widthInches'.",
      });
    }

    const lengthNum = parseFloat(lengthInches);
    const widthNum = parseFloat(widthInches);
    if (isNaN(lengthNum) || isNaN(widthNum) || lengthNum <= 0 || widthNum <= 0) {
      return res.status(400).json({
        error: "Invalid 'lengthInches' or 'widthInches'. Must be positive numbers.",
      });
    }

    // Calculate square footage.
    const baseSqFt = (lengthNum * widthNum) / 144;
    const finalSqFt = baseSqFt * 1.2; // Add 20% waste.

    // Optional: Slab calculation.
    let slabCount = 0;
    if (slabLengthInches && slabWidthInches) {
      const sLen = parseFloat(slabLengthInches);
      const sWid = parseFloat(slabWidthInches);
      if (!isNaN(sLen) && !isNaN(sWid) && sLen > 0 && sWid > 0) {
        const slabArea = (sLen * sWid) / 144;
        slabCount = Math.ceil(finalSqFt / slabArea);
      }
    }

    // Material pricing: Find material row and apply 35% markup.
    const matRow = materialsData.find(
      (row) => row.Material?.toLowerCase() === material.toLowerCase()
    );
    if (!matRow) {
      return res.status(404).json({ error: `Material '${material}' not found.` });
    }
    const baseCostStr = matRow.BaseCostPerSqFt || matRow.Cost || "0";
    const baseCost = parseFloat(baseCostStr);
    if (isNaN(baseCost)) {
      return res.status(400).json({ error: `Invalid base cost for material: ${material}` });
    }
    const markedUpCost = baseCost * 1.35;

    // Labor cost from CSV data.
    let laborCost = 0;
    if (laborKey) {
      const laborRow = laborData.find(
        (row) => row.LaborKey?.toLowerCase() === laborKey.toLowerCase()
      );
      if (laborRow && laborRow.Cost) {
        laborCost = parseFloat(laborRow.Cost) || 0;
      }
    } else {
      const defaultLaborRow = laborData.find((row) => row.LaborKey === "Default");
      if (defaultLaborRow && defaultLaborRow.Cost) {
        laborCost = parseFloat(defaultLaborRow.Cost) || 0;
      }
    }

    // Calculate totals.
    const materialTotal = markedUpCost * finalSqFt;
    const totalEstimate = materialTotal + laborCost;

    return res.json({
      material,
      lengthInches,
      widthInches,
      slabLengthInches: slabLengthInches || null,
      slabWidthInches: slabWidthInches || null,
      slabCount,
      baseSqFt: parseFloat(baseSqFt.toFixed(2)),
      finalSqFt: parseFloat(finalSqFt.toFixed(2)),
      baseCost,
      markedUpCost: parseFloat(markedUpCost.toFixed(2)),
      laborKey: laborKey || "Default",
      laborCost,
      totalEstimate: parseFloat(totalEstimate.toFixed(2)),
    });
  } catch (error) {
    console.error("Error in /api/get-estimate:", error);
    return res.status(500).json({ error: "Internal server error" });
  }
});

/**
 * POST /api/upload-image
 * Accepts an image upload for stone or blueprint analysis.
 * Uses Multer to handle the file upload.
 */
app.post("/api/upload-image", upload.single("file"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded." });
    }
    // TODO: Integrate your AI image recognition or blueprint analysis logic here.
    return res.json({
      message: "Image received! AI analysis pending...",
      fileName: req.file.filename,
    });
  } catch (error) {
    console.error("Error in /api/upload-image:", error);
    return res.status(500).json({ error: "Internal server error" });
  }
});

/**
 * POST /api/chat
 * Uses OpenAI to generate an AI-based natural language response.
 * The assistant remains in character as CARI, the Surprise Granite Design Assistant.
 */
app.post("/api/chat", async (req, res) => {
  try {
    const { userMessage } = req.body;
    if (!userMessage) {
      return res.status(400).json({ error: "No userMessage provided." });
    }
    if (!OPENAI_API_KEY) {
      return res.status(500).json({
        error: "OpenAI API key not configured on server. Please set OPENAI_API_KEY.",
      });
    }

    // Build the conversation prompt
    const messages = [
      { role: "system", content: SYSTEM_INSTRUCTIONS },
      { role: "user", content: userMessage },
    ];

    // Call OpenAI's Chat Completion
    const response = await openai.createChatCompletion({
      model: "gpt-3.5-turbo",
      messages,
      max_tokens: 250,
      temperature: 0.7,
    });

    const aiReply = response.data.choices[0].message.content.trim();
    return res.json({ response: aiReply });
  } catch (error) {
    console.error("Error in /api/chat:", error?.response?.data || error);
    return res.status(500).json({ error: "Internal server error" });
  }
});

/**
 * POST /api/email-history
 * Emails a copy of the chat history using EmailJS.
 * Request body: { "email": "customer@example.com", "chatHistory": "Full chat text..." }
 */
app.post("/api/email-history", async (req, res) => {
  const { email, chatHistory } = req.body;
  if (!email || !chatHistory) {
    return res.status(400).json({ error: "Missing 'email' or 'chatHistory'." });
  }
  try {
    const payload = {
      service_id: EMAILJS_SERVICE_ID,
      template_id: EMAILJS_TEMPLATE_ID,
      user_id: EMAILJS_USER_ID,
      template_params: {
        email: email,
        chat_history: chatHistory,
      },
    };
    const response = await axios.post(
      "https://api.emailjs.com/api/v1.0/email/send",
      payload,
      { headers: { "Content-Type": "application/json" } }
    );
    return res.json({ message: "Chat history sent!", response: response.data });
  } catch (err) {
    console.error("Error sending email via EmailJS:", err);
    return res.status(500).json({ error: "Failed to send email." });
  }
});

/**
 * Basic test route listing available endpoints.
 */
app.get("/", (req, res) => {
  res.send(`
    <h1>Surprise Granite Chatbot Backend (OpenAI Integrated)</h1>
    <p>Available Endpoints:</p>
    <ul>
      <li><strong>POST</strong> /api/get-estimate</li>
      <li><strong>POST</strong> /api/upload-image</li>
      <li><strong>POST</strong> /api/chat (OpenAI)</li>
      <li><strong>POST</strong> /api/schedule</li>
      <li><strong>POST</strong> /api/email-history</li>
      <li><strong>GET</strong> /api/get-tos</li>
      <li><strong>GET</strong> /api/get-business-info</li>
      <li><strong>GET</strong> /api/get-instructions</li>
    </ul>
  `);
});

/**
 * Start the server after loading CSV data.
 */
const PORT = process.env.PORT || 5000;
loadCSVData().then(() => {
  app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
  });
});
