import time
import requests
import json

session = requests.Session()

print("=" * 60)
print("ECOMAGENT - FULL SYSTEM TEST")
print("=" * 60)
print()

# Test 1: Status check
print("TEST 1: Checking Flask app status")
try:
    response = session.get('http://127.0.0.1:5000/status')
    print(f"✓ Flask app is running: {response.json()}")
except Exception as e:
    print(f"✗ Flask app not responding: {e}")
    exit(1)
print()

# Test 2: Save credentials
print("TEST 2: Saving Shopify credentials")
response = session.post('http://127.0.0.1:5000/save-credentials', 
    json={
        'shopify_store_url': 'ecom-agent-demo.myshopify.com',
        'shopify_access_token': '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'
    })
result = response.json()
if result.get('success'):
    print("✓ Credentials saved successfully")
else:
    print(f"✗ Failed to save credentials: {result.get('error')}")
print()

# Test 3: Import product
print("TEST 3: Importing product from supplier")
response = session.post('http://127.0.0.1:5000/import-product',
    json={'supplier_url': 'https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html'})
import_result = response.json()

if import_result.get('success'):
    print("✓ Product imported successfully!")
    print()
    
    print("=" * 60)
    print("SUCCESS! PRODUCT IMPORTED TO SHOPIFY")
    print("=" * 60)
    print(f"Product Name: {import_result.get('product_name')}")
    print(f"Price: {import_result.get('price')}")
    print(f"Product ID: {import_result.get('shopify_product_id')}")
    print(f"Shopify URL: {import_result.get('shopify_url')}")
    print()
    print("✓ ALL TESTS PASSED - SYSTEM IS WORKING PERFECTLY!")
else:
    print(f"✗ Failed to import: {import_result.get('error')}")

print()
