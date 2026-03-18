# 🤖 EcomAgent

> An AI-powered agent that automatically extracts product data
> from any supplier webpage and publishes it directly to your
> Shopify store — in under 20 seconds.

---

## ✨ Features

- 🌐 Works with ANY public product page URL
- 🧠 AI powered product data extraction (LLaMA 3.3 70B)
- 📸 Direct image extraction via Playwright
- 💰 Automatic price detection from any currency
- 📝 Auto generated SEO optimized descriptions
- 🛍️ One click Shopify publishing via REST API
- 🎨 Beautiful dark theme SaaS web UI
- 🔐 One time store setup, import forever
- 🔄 Self correcting retry loop (3 attempts)
- 🐳 Docker ready + Google Cloud Run deployable

---

## 🏗️ Architecture
```
User pastes Supplier URL
         ↓
[Flask Web App - app.py]
         ↓
[subprocess: run_pipeline.py]
         ↓
    ┌────────────┐
    │ extractor  │
    │   .py      │
    │            │
    │ Playwright │
    │  Browser   │
    │     ↓      │
    │ Screenshot │
    │   + HTML   │
    │     ↓      │
    │ Groq AI    │
    │ LLaMA 3.3  │
    │     ↓      │
    │ Pydantic   │
    │ Validation │
    └────────────┘
         ↓
    ┌────────────┐
    │ navigator  │
    │   .py      │
    │            │
    │  Shopify   │
    │ Admin API  │
    └────────────┘
         ↓
  Live Product Listing ✅
```

---

## 🛠️ Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.11 | Core language |
| Flask | Web application framework |
| Playwright | Browser automation + screenshots |
| Groq (LLaMA 3.3 70B) | AI product data extraction |
| Pydantic | Data validation + self correction |
| Shopify Admin REST API | Product publishing |
| subprocess | Safe async pipeline execution |
| Docker | Containerization |
| Google Cloud Run | Cloud deployment |

---

## ⚡ Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/skypank-coder/Ecom-agent.git
cd ecom-agent
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Set up environment variables
```bash
cp .env.example .env
```

Fill in your credentials in `.env`:
```
GROQ_API_KEY=your_groq_api_key
SHOPIFY_STORE_URL=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxx
SUPPLIER_URL=https://any-product-page-url.com
```

### 4. Run the web app
```bash
python src/app.py
```

### 5. Open browser
```
http://localhost:5000
```

1. Enter your Shopify store URL + access token once
2. Paste any supplier product URL
3. Click Import — done in 20 seconds! 🎉

---

## 🔐 Getting Your Shopify Access Token

1. Go to **https://partners.shopify.com** → create free account
2. Create a Development Store
3. Inside store: **Settings → Apps → Develop Apps**
4. Click **Allow custom app development**
5. Create app → **Configure Admin API scopes**
6. Enable: `write_products`, `read_products`,
           `write_files`, `read_files`
7. Click **Install App** → **Reveal token once**
8. Copy token starting with `shpat_...`

---

## 📁 Project Structure
```
ecom-agent/
├── src/
│   ├── extractor.py      # Playwright + Groq AI extraction
│   ├── navigator.py      # Shopify API publisher
│   ├── app.py            # Flask web application
│   └── run_pipeline.py   # Subprocess pipeline runner
├── templates/
│   ├── setup.html        # One time store connection UI
│   └── dashboard.html    # Product import dashboard
├── .env                  # Your credentials (never commit!)
├── .env.example          # Template for credentials
├── .gitignore
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## 🔄 How It Works In Detail

### Step 1: OBSERVE
Playwright launches a headless Chromium browser, navigates
to the supplier URL, waits for full page load, and:
- Takes a full page screenshot
- Extracts complete page HTML
- Directly scrapes all image URLs from img tags
- Directly extracts price using smart CSS selectors

### Step 2: THINK
Groq's LLaMA 3.3 70B model analyzes the HTML and extracts:
- Product name
- Price (with currency)
- Image URLs
- SEO optimized description (3 sentences)
- Key features (3-5 bullet points)

### Step 3: VALIDATE
Pydantic validates the AI response against a strict schema.
If validation fails, the agent automatically retries up to
3 times with a fresh extraction. All non-ASCII characters
are sanitized to prevent encoding errors.

### Step 4: PUBLISH
Shopify Admin REST API creates a complete product listing:
- Title + SEO description
- Price + variants
- Product images (directly uploaded to Shopify CDN)
- Tags: ai-generated, ecom-agent
- Status: active (immediately live)

### Step 5: RESULT
Web UI displays:
- Product image preview
- Product name + price
- Direct link to Shopify listing
- Import history (last 5 products)

---

## 🖥️ Web UI

### Setup Page
One time store connection — enter your Shopify
credentials once and never again.

### Dashboard
Clean import interface — just paste a URL and
watch the agent work in real time with live
progress updates.

---

## 🐳 Docker Deployment
```bash
docker build -t ecom-agent .
docker run -p 5000:5000 --env-file .env ecom-agent
```

---

## ☁️ Google Cloud Run Deployment
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy ecom-agent \
  --source . \
  --region us-central1 \
  --memory 2Gi \
  --timeout 120
```

---

## 🚀 Future Improvements

- [ ] Bulk import (multiple URLs at once)
- [ ] WooCommerce + other platform support
- [ ] Price comparison across suppliers
- [ ] Scheduled auto import
- [ ] Inventory tracking
- [ ] Competitor price monitoring
- [ ] Gemini vision for screenshot based extraction
- [ ] Product variant detection (sizes, colors)

---

## 🆓 Free Tier Usage

This project runs completely free:
- **Groq API** — 14,400 requests/day free
- **Shopify Partner** — Development stores free
- **Google Cloud Run** — 2M requests/month free
- **Playwright** — completely open source

---

## 👨‍💻 Built By

**Saatwik Kumar Yadav** — CSE Student & Full Stack Developer

[![GitHub](https://img.shields.io/badge/GitHub-skypank--coder-black?logo=github)](https://github.com/skypank-coder)

---

## 📄 License

MIT License — feel free to use and modify!