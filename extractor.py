import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding='utf-8',
        errors='replace'
    )

import asyncio
import json
import os
from typing import List, Optional

from dotenv import load_dotenv
from groq import Groq
from playwright.async_api import async_playwright
from pydantic import BaseModel, ValidationError


# NOTE: we intentionally avoid configuring a global logger here.
# For this hackathon-style script, clear stdout prints with explicit
# progress messages give the best "step-by-step" UX when run in a terminal
# or in Cloud Run logs. If a larger app wants structured logging, it can
# wrap this module and add logging there.


def _safe_ascii(obj: object) -> str:
    """Return an ASCII-only string representation of the input."""

    return "".join(c for c in str(obj) if ord(c) < 128)


def _print_step(message: str) -> None:
    """Print a progress message and immediately flush stdout."""

    print(_safe_ascii(message))
    sys.stdout.flush()


def _load_env() -> None:
    """
    Load environment variables from `.env`.

    WHY:
    - Keeps secrets (like GROQ_API_KEY) out of source control.
    - Allows local/dev/prod to use different credentials without
      changing code.
    """

    load_dotenv()


def _get_required_env(name: str) -> str:
    """
    Fetch a required environment variable or fail fast with a clear error.

    WHY:
    - It's better to crash immediately with a helpful message than to
      hit confusing errors further down (e.g. 401s from Groq).
    """

    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


class ProductData(BaseModel):
    product_name: str
    price: str
    image_urls: List[str]
    seo_description: str
    key_features: List[str]


async def _capture_page_state(supplier_url: str) -> tuple[str, str, list[str], str]:
    """
    Use Playwright to navigate to the supplier page and capture:
    - a full-page screenshot
    - the complete HTML (untruncated)
    - a list of image URLs extracted directly from the DOM

    WHY this exact sequence:
    - Headless Chromium simulates a real browser, which is more reliable
      than plain HTTP for modern, JS-heavy e‑commerce sites.
    - `domcontentloaded` ensures the initial HTML is ready.
    - A best-effort `networkidle` wait (with short timeout) reduces
      the chance of half-rendered content but doesn't block forever
      on sites with long-polling.
    - An extra 3s wait gives slow images or price widgets a final chance to
      render.  The full HTML is preserved so we can fall back to scraping
      <img> tags later if the model misses them.
    - Extracting image URLs via Playwright is more dependable than
      asking Groq for them, so we gather them here and return them for
      later use.
    """

    screenshot_path = "supplier_screenshot.png"

    browser = None
    context = None
    page = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        await page.goto(
            supplier_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        try:
            # Some sites never truly go "idle" due to analytics or live chat.
            # We still attempt this for the many sites where it *does* stabilize the DOM.
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # Silently ignore as requested — best-effort only.
            pass

        # Give late-loading images or price widgets a final chance to render.
        await page.wait_for_timeout(3000)

        # --- new section: directly extract price from page ---
        raw_price = await page.evaluate(r"""
            () => {
                // Try multiple common price selectors
                const selectors = [
                    '[class*="price"]',
                    '[class*="Price"]', 
                    '[id*="price"]',
                    '[class*="amount"]',
                    '[class*="cost"]',
                    'span[class*="rupee"]',
                    '[class*="mrp"]',
                    '[class*="selling"]',
                    '.a-price-whole',
                    '#priceblock_ourprice',
                    '.price-item',
                    '[data-price]',
                    '[class*="product-price"]',
                    '.price_color',  // books.toscrape.com specific
                    'p.price_color', // more specific
                    '[class*="color"]' // broader
                ];
                
                for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    if (el && el.innerText && el.innerText.trim().length > 0) {
                        return el.innerText.trim();
                    }
                }
                
                // Fallback: search all text for price pattern
                const body = document.body.innerText;
                const priceMatch = body.match(
                    /(?:₹|Rs\.?|INR|USD|\$|£|€|£)\s*[\d,]+(?:\.\d{1,2})?/
                );
                return priceMatch ? priceMatch[0] : 'Price not available';
            }
        """)

        if raw_price:
            raw_price = ''.join(
                c for c in raw_price
                if ord(c) < 128
            )
        direct_price = raw_price or 'Price not available'
        print(_safe_ascii(f"Direct price extracted: {direct_price}"))
        # --------------------------------------------------------------------

        await page.screenshot(path=screenshot_path, full_page=True)

        # --- new section: directly grab image URLs from the rendered page ---
        raw_images = await page.evaluate("""
            () => {
                const imgs = Array.from(document.querySelectorAll('img'));
                return imgs
                    .map(img => img.src || img.getAttribute('data-src') || '')
                    .filter(src => src && src.length > 10);
            }
        """)

        # fix relative URLs using base domain info
        from urllib.parse import urljoin, urlparse
        parsed = urlparse(supplier_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        direct_page_images: list[str] = []
        for url in raw_images:
            url = ''.join(c for c in url if ord(c) < 128).strip()
            if not url:
                continue
            if url.startswith('http://') or url.startswith('https://'):
                direct_page_images.append(url)
            elif url.startswith('//'):
                direct_page_images.append('https:' + url)
            elif url.startswith('/'):
                direct_page_images.append(base_url + url)
            else:
                direct_page_images.append(urljoin(supplier_url, url))

        # filter out tiny icons, tracking pixels, base64 blobs etc.
        direct_page_images = [
            url for url in direct_page_images
            if url.startswith('http')
            and not url.endswith('.gif')
            and not url.endswith('.svg')
            and 'tracking' not in url.lower()
            and 'pixel' not in url.lower()
            and 'logo' not in url.lower()
            and len(url) > 20
        ]

        safe_count = len(direct_page_images)
        print(_safe_ascii(f"Playwright found {safe_count} images directly from page"))
        # ---------------------------------------------------------------------

        html_content = await page.content()
        html_content = ''.join(
            char for char in html_content 
            if ord(char) < 128
        )
        html_content = html_content[:8000]
        html_content_full = html_content

        await context.close()
        await browser.close()

    return screenshot_path, html_content_full, direct_page_images, direct_price


def _build_groq_prompt(html_content: str) -> str:
    """
    Build the exact prompt required for Groq, injecting HTML content.

    WHY:
    - Centralizing the prompt string makes it easy to tweak later
      without hunting through business logic.
    - Using a template ensures we keep the required instructions
      (JSON only, no markdown, fallbacks for missing price/images).
    """

    return f"""
You are an expert e-commerce product data extractor.
Analyze this HTML from an e-commerce product page and extract info.

HTML Content:
{html_content}

Return ONLY a valid JSON object with exactly these fields:
{{
  "product_name": "full product name as string",
  "price": "price with currency symbol as string",
  "image_urls": ["list", "of", "image", "urls"],
  "seo_description": "3 sentences of exciting SEO optimized marketing copy",
  "key_features": ["feature 1", "feature 2", "feature 3", "feature 4"]
}}

Rules:
- Return ONLY the JSON object
- No markdown, no code blocks, no explanation
- No text before or after the JSON
- If price not found write "Price not available"
- If images not found return empty list
""".strip()


def _call_groq_and_get_text(client: Groq, prompt: str) -> str:
    """
    Call Groq's chat completion API and return the raw text.

    WHY sync here:
    - The Groq Python SDK is synchronous; wrapping it in `asyncio.to_thread`
      isn't necessary for this small script and would add complexity without
      clear benefit at this stage.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
    )
    # After every Groq API call we pause to be gentle on rate limits,
    # as requested in the spec.
    # This sleep is awaited in the caller to keep the main flow async-friendly.
    return response.choices[0].message.content or ""


def _clean_and_parse_model_output(text: str) -> ProductData:
    """
    Strip accidental markdown/code fences, parse JSON, and validate with Pydantic.

    WHY:
    - Even when instructed otherwise, models sometimes wrap JSON in ``` fences.
    - Using a strict JSON parser + schema validation guarantees downstream
      code only sees well-structured data.
    """

    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:]

    raw_data = json.loads(text)
    return ProductData.model_validate(raw_data)


async def extract_product_data() -> ProductData:
    """
    High-level orchestration for the extraction flow.

    Steps:
    1. Load env vars and construct a Groq client.
    2. Use Playwright to capture screenshot + truncated HTML.
    3. Send HTML to Groq with a tightly-scoped prompt.
    4. Clean and validate the model output as ProductData.
    5. Persist the result to `extracted_product.json`.

    WHY a single orchestrator:
    - Keeps the CLI entrypoint simple (`asyncio.run(extract_product_data())`).
    - Makes it easy for other modules to reuse this function directly.
    """

    _load_env()
    groq_api_key = _get_required_env("GROQ_API_KEY")
    supplier_url = _get_required_env("SUPPLIER_URL")

    client = Groq(api_key=groq_api_key)

    max_attempts = 3
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            _print_step("Launching browser...")
            _print_step("Navigating to supplier page...")
            _print_step("Taking screenshot...")

            screenshot_path, html_content_full, direct_page_images, direct_price = await _capture_page_state(supplier_url)

            _print_step("Extracting page content...")

            # Groq prompt uses truncated HTML to keep token count reasonable
            html_content = html_content_full[:8000]
            html_content = html_content.encode('ascii', errors='ignore').decode('ascii')
            prompt = _build_groq_prompt(html_content)

            _print_step("Sending to Groq AI...")
            # Groq SDK is sync; call it directly, then backoff using asyncio.
            text = _call_groq_and_get_text(client, prompt)
            await asyncio.sleep(2)

            _print_step("Validating response...")
            product = _clean_and_parse_model_output(text)

            # ⚠️ Fix for relative image URLs from books.toscrape.com
            # The supplier site often returns paths like "/media/..." instead
            # of full URLs. If we leave them unchanged Shopify will try to
            # fetch them from the wrong host, resulting in missing images.
            base_url = "https://books.toscrape.com"
            fixed_urls: list[str] = []
            for url in product.image_urls:
                if url.startswith("http"):
                    fixed_urls.append(url)
                elif url.startswith("/"):
                    fixed_urls.append(base_url + url)
            product.image_urls = fixed_urls

            # override with Playwright images when available
            if direct_page_images:
                # take up to ten images to avoid huge payloads
                product.image_urls = direct_page_images[:10]
                print(_safe_ascii(f"Using {len(product.image_urls)} directly extracted images"))
            else:
                print(_safe_ascii("No images found directly, keeping Groq extracted URLs"))

            # Override Groq price with directly extracted price
            # Direct extraction is more reliable than Groq parsing HTML
            if direct_price and direct_price != 'Price not available':
                product.price = direct_price
                print(_safe_ascii(f"Using directly extracted price: {direct_price}"))

            # Fallback: if the model failed to return any images, scrape
            # them directly from the full HTML we captured earlier.
            if not product.image_urls:
                import re

                found = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_content_full)
                scraped: list[str] = []
                for url in found:
                    if url.startswith("http"):
                        scraped.append(url)
                    elif url.startswith("/"):
                        scraped.append(base_url + url)
                # dedupe while preserving order
                seen = set()
                product.image_urls = [u for u in scraped if not (u in seen or seen.add(u))]

            # Additional fallback: if still no images, use Playwright to query DOM
            if not product.image_urls:
                # Re-launch browser to query the DOM directly
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    context = await browser.new_context(viewport={"width": 1920, "height": 1080})
                    page = await context.new_page()
                    await page.goto(supplier_url, wait_until="domcontentloaded", timeout=60000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3000)

                    # Query for all img elements and their src attributes
                    img_elements = await page.query_selector_all('img')
                    dom_urls = []
                    for img in img_elements:
                        src = await img.get_attribute('src')
                        if src:
                            dom_urls.append(src)

                    # Also check for data-src (lazy loading)
                    lazy_imgs = await page.query_selector_all('img[data-src]')
                    for img in lazy_imgs:
                        data_src = await img.get_attribute('data-src')
                        if data_src:
                            dom_urls.append(data_src)

                    await browser.close()

                # Process the DOM-found URLs
                scraped: list[str] = []
                for url in dom_urls:
                    url = url.strip()
                    if url.startswith("http"):
                        scraped.append(url)
                    elif url.startswith("/"):
                        scraped.append(base_url + url)
                # dedupe while preserving order
                seen = set()
                product.image_urls = [u for u in scraped if not (u in seen or seen.add(u))]

            _print_step("Saving results...")
            # Print to console as formatted JSON for quick inspection.
            print(_safe_ascii(json.dumps(product.model_dump(), indent=2, ensure_ascii=True)))
            sys.stdout.flush()

            with open('extracted_product.json', 'w', 
                      encoding='utf-8') as f:
                json.dump(
                    product.dict(),
                    f,
                    indent=2,
                    ensure_ascii=True
                )

            _print_step(
                "Done! Product data saved to extracted_product.json"
            )

            return product

        except (json.JSONDecodeError, ValidationError) as e:
            # These failures usually mean the model's JSON wasn't quite
            # compliant with the schema. Retrying lets the model "self-correct"
            # based on a fresh sample of the page HTML (which may have changed)
            # or simply due to sampling variance.
            last_error = e
            error_msg = str(e).encode(
                'ascii', errors='ignore'
            ).decode('ascii')
            print(_safe_ascii(f"Attempt {attempt} failed: {error_msg}"))
            sys.stdout.flush()
        except Exception as e:
            # Catch-all for network issues, Playwright failures, or Groq errors.
            last_error = e
            error_msg = str(e).encode(
                'ascii', errors='ignore'
            ).decode('ascii')
            print(_safe_ascii(f"Attempt {attempt} failed: {error_msg}"))
            sys.stdout.flush()

        if attempt < max_attempts:
            # Short fixed delay between attempts gives external systems
            # (supplier site, Groq) a chance to recover.
            await asyncio.sleep(2)

    raise SystemExit(
        f"Extraction failed after {max_attempts} attempts. Last error: {last_error}"
    )


async def extract_product() -> ProductData:
    """
    Thin alias kept for orchestration code.

    WHY:
    - The high-level agent controller can depend on a concise name
      (`extract_product`) without needing to know about the more
      descriptive internal name (`extract_product_data`).
    """

    return await extract_product_data()


if __name__ == "__main__":
    # Running this module directly provides a simple manual test:
    # - verifies `.env` is configured (GROQ_API_KEY, SUPPLIER_URL)
    # - checks Playwright can render and screenshot the page
    # - ensures Groq returns valid, schema-compliant JSON
    asyncio.run(extract_product_data())
