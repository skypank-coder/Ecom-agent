import sys
import io
import os
import json
import asyncio

# Add current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

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
    config_path = os.getenv('PIPELINE_CONFIG_PATH')
    if not config_path:
        raise ValueError("PIPELINE_CONFIG_PATH environment variable not set")
    
    # Convert to absolute path if needed
    config_path = os.path.abspath(config_path)
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
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
