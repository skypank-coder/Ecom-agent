import sys
import io
import os
import json
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding='utf-8',
    errors='replace'
)
sys.stderr = io.TextIOWrapper(
    sys.stderr.buffer,
    encoding='utf-8',
    errors='replace'
)

from dotenv import load_dotenv
load_dotenv()

async def main():
    # Load temp config written by Flask
    config_path = os.getenv('PIPELINE_CONFIG_PATH', 'temp_config.json')
    with open(config_path, 'r',
              encoding='utf-8') as f:
        config = json.load(f)

    # Override env vars with request-specific values
    os.environ['SUPPLIER_URL'] = config['supplier_url']
    os.environ['SHOPIFY_STORE_URL'] = config['shopify_store_url']
    os.environ['SHOPIFY_ACCESS_TOKEN'] = config['shopify_access_token']

    # Import and run extractor
    from extractor import extract_product
    product_data = await extract_product()
    print(f"Extracted: {product_data.product_name}")

    # Import and run navigator
    from navigator import publish_to_shopify
    result = publish_to_shopify()
    print("Published to Shopify successfully")

    return product_data, result


if __name__ == '__main__':
    asyncio.run(main())
