import sys
import io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding='utf-8',
        errors='replace'
    )

import json
import os
import re
from typing import Any, Dict

import requests
from dotenv import load_dotenv


def _load_env() -> None:
    """
    Load environment variables from `.env`.

    WHY:
    - Keeps Shopify credentials out of source control.
    - Lets you point the agent at different stores (dev, staging, prod)
      without changing code.
    """

    load_dotenv()


def _get_required_env(name: str) -> str:
    """
    Fetch a required environment variable or exit with a clear message if missing.

    WHY:
    - It's better to fail fast with a helpful hint than to send half-baked
      requests that will only 401/404 later.
    """

    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _load_extracted_product(path: str = "extracted_product.json") -> Dict[str, Any]:
    """
    Load the previously extracted product data from disk.

    WHY:
    - Decouples the "observe + extract" step (Playwright + Groq) from
      the "act" step (Shopify API call), which makes it easier to debug
      each part independently.
    """

    try:
        with open('extracted_product.json', 'r',
                  encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        raise SystemExit(
            f"Could not find {path}. Run the extractor first so this file exists."
        )
    except json.JSONDecodeError as e:
        raise SystemExit(f"Failed to parse {path} as JSON: {e}")


def _clean_price(raw_price: str) -> str:
    """
    Clean a human-friendly price string into a numeric-only string.

    HOW:
    - Strip all characters *except* digits and decimal point.
    - If we can't find any digits, fall back to '0.00'.

    WHY:
    - Shopify expects numeric price strings without currency symbols.
    - Being forgiving here makes the pipeline resilient to slightly
      messy model outputs like 'Approx. £51.77!!!'.
    """

    if not isinstance(raw_price, str):
        return "0.00"

    # Keep only digits and decimal point.
    cleaned = re.sub(r"[^0-9.]", "", raw_price)

    # Remove leading/trailing dots and collapse multiple dots if they appear.
    if cleaned.count(".") > 1:
        # Take only the first dot and drop the rest.
        first_dot = cleaned.find(".")
        cleaned = cleaned[: first_dot + 1] + cleaned[first_dot + 1 :].replace(".", "")

    cleaned = cleaned.strip(".")

    if not cleaned:
        return "0.00"

    try:
        # Format to two decimal places to satisfy Shopify's expectations.
        return f"{float(cleaned):.2f}"
    except ValueError:
        # If parsing still fails, fall back defensively.
        return "0.00"


def _build_shopify_payload(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform extracted product data into the Shopify product create payload.

    WHY:
    - Keeping this mapping in one place makes it easy to evolve the
      Shopify representation without touching the HTTP code.
    """

    product_name = product_data.get("product_name", "Untitled Product")
    price_raw = product_data.get("price", "0.00")
    key_features = product_data.get("key_features") or []
    image_urls = product_data.get("image_urls") or []
    seo_description = product_data.get("seo_description", "")

    product_name = product_name.encode(
        'ascii', errors='ignore'
    ).decode('ascii')
    seo_description = seo_description.encode(
        'ascii', errors='ignore'
    ).decode('ascii')
    key_features = [
        f.encode('ascii', errors='ignore').decode('ascii')
        for f in key_features
    ]

    price_cleaned = _clean_price(price_raw)

    # Build the bullet list HTML that Shopify will render on the product page.
    features_html = "".join(f"<li>{f}</li>" for f in key_features)
    body_html = f"<p>{seo_description}</p><ul>{features_html}</ul>"

    # Build image objects for Shopify only from fully-qualified URLs.
    images = [
        {"src": url} for url in image_urls if url and isinstance(url, str) and url.startswith("http")
    ]

    # Progress message to make it obvious that we are attaching images.
    print(f"Attaching {len(image_urls)} images to listing...")

    return {
        "product": {
            "title": product_name,
            "body_html": body_html,
            "vendor": "EcomAgent",
            "product_type": "Imported Product",
            "status": "active",
            "tags": "ai-generated, ecom-agent",
            "images": images,
            "variants": [
                {
                    "price": price_cleaned,
                    "inventory_management": None,
                }
            ],
        }
    }


def publish_product_to_shopify() -> None:
    """
    Orchestrate loading extracted data and publishing it to Shopify.

    WHY:
    - Provides a single entry point both for the CLI (`python src/navigator.py`)
      and for other modules that may want to trigger publishing programmatically.
    """

    _load_env()

    # These two values identify and authorize against the Shopify Admin API.
    shopify_store_url = _get_required_env("SHOPIFY_STORE_URL")
    shopify_access_token = _get_required_env("SHOPIFY_ACCESS_TOKEN")

    print("Loading extracted product data...")
    product_data = _load_extracted_product()

    payload = _build_shopify_payload(product_data)

    endpoint = (
        f"https://{shopify_store_url}/admin/api/2024-01/products.json"
    )
    headers = {
        "X-Shopify-Access-Token": shopify_access_token,
        "Content-Type": "application/json",
    }

    print("Connecting to Shopify...")

    try:
        print("Creating product listing...")
        response = requests.post(
            endpoint,
            headers=headers,
            data=json.dumps(payload),
            timeout=30,
        )
    except requests.RequestException as e:
        # Network-layer or HTTP client errors (timeouts, DNS, etc.)
        print(f"Failed to reach Shopify API: {e}")
        return

    try:
        response_data = response.json()
    except json.JSONDecodeError:
        response_data = None

    if response.status_code == 201 and isinstance(response_data, dict):
        # Shopify returns the created product object on success.
        try:
            product = response_data["product"]
            product_id = product["id"]
        except (KeyError, TypeError):
            # Even on 201, be defensive if the body isn't what we expect.
            print("Product created (201), but response format was unexpected.")
            print(f"Raw response: {response.text}")
            return

        print("Product created successfully!")
        print(f"Product ID: {product_id}")
        print(
            f"View at: https://{shopify_store_url}/admin/products/{product_id}"
        )

        # Persist the full Shopify response for debugging or later use.
        try:
            with open('shopify_response.json', 'w',
                      encoding='utf-8') as f:
                json.dump(
                    response.json(),
                    f,
                    indent=2,
                    ensure_ascii=True
                )
        except OSError as e:
            # Failure to write the debug file shouldn't block the workflow.
            print(f"Warning: could not write shopify_response.json: {e}")

        print("Product published successfully!")
    else:
        # On any non-201 status, surface both the status code and body
        # so the user can see Shopify's error message (e.g. auth or validation).
        print(f"Failed: {response.status_code}")
        print(f"Error: {response.text}")


def publish_to_shopify() -> None:
    """
    Alias retained for the master agent controller.

    WHY:
    - Keeps the controller code aligned with the high-level
      design docs (`publish_to_shopify`) while allowing this
      module to expose a more descriptive primary function name.
    """

    publish_product_to_shopify()


if __name__ == "__main__":
    # Standalone entry point so you can:
    # - run this after the extractor to publish a product
    # - test Shopify connectivity independently from Playwright / Groq
    try:
        publish_product_to_shopify()
    except Exception as e:
        # Top-level catch to ensure any unexpected exception is surfaced
        # with a clear message, instead of a long noisy traceback.
        print(f"Navigator crashed with an unexpected error: {e}")
