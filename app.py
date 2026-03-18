import sys
import os
import io
import json
import uuid
import threading
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

from flask import (Flask, request, jsonify, 
                   render_template, session, redirect)
from flask_cors import CORS
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.secret_key = 'ecomagent-secret-key-2024-fixed'
app.config['JSON_AS_ASCII'] = False
app.config['SESSION_COOKIE_SECURE'] = False  # Allow non-HTTPS (for local dev)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cross-IP requests
app.config['PERMANENT_SESSION_LIFETIME'] = 86400 * 7  # 7 days

# In-memory job store for polling
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

def sanitize(text):
    if not text:
        return ''
    return ''.join(
        c for c in str(text) if ord(c) < 128
    ).strip()

@app.route('/')
def index():
    if session.get('shopify_store_url'):
        return redirect('/dashboard')
    return redirect('/setup')

@app.route('/setup')
def setup():
    return render_template('setup.html')

@app.route('/save-credentials', methods=['POST'])
def save_credentials():
    try:
        data = request.get_json()
        session['shopify_store_url'] = data.get(
            'shopify_store_url', ''
        )
        session['shopify_access_token'] = data.get(
            'shopify_access_token', ''
        )
        session.permanent = True
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({
            'success': False,
            'error': sanitize(str(e))
        })

@app.route('/dashboard')
def dashboard():
    if not session.get('shopify_store_url'):
        return redirect('/setup')
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/setup')

@app.route('/import-product', methods=['POST'])
def import_product():
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data received'
            })

        supplier_url = sanitize(
            data.get('supplier_url', '')
        )
        shopify_store_url = sanitize(
            session.get('shopify_store_url', '')
        )
        shopify_access_token = sanitize(
            session.get('shopify_access_token', '')
        )

        if not supplier_url:
            return jsonify({
                'success': False,
                'error': 'Supplier URL is required'
            })

        if not shopify_store_url or not shopify_access_token:
            return jsonify({
                'success': False,
                'error': 'Please setup your store first'
            })

        job_id = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[job_id] = {
                'status': 'pending',
                'result': None,
                'error': None
            }

        # Write a per-job config file for the pipeline with absolute path
        import tempfile
        temp_dir = tempfile.gettempdir()
        config_path = os.path.join(temp_dir, f'temp_config_{job_id}.json')
        config = {
            'supplier_url': supplier_url,
            'shopify_store_url': shopify_store_url,
            'shopify_access_token': shopify_access_token
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f)

        def run_job():
            try:
                with JOBS_LOCK:
                    JOBS[job_id]['status'] = 'running'

                # Get the absolute path to src directory
                script_dir = os.path.dirname(os.path.abspath(__file__))
                
                # Add src directory to sys.path if not already there
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)

                # Set environment variables for the job
                os.environ['SUPPLIER_URL'] = supplier_url
                os.environ['SHOPIFY_STORE_URL'] = shopify_store_url
                os.environ['SHOPIFY_ACCESS_TOKEN'] = shopify_access_token
                os.environ['PIPELINE_CONFIG_PATH'] = config_path

                # Import the extraction and publishing modules directly
                from extractor import extract_product
                from navigator import publish_to_shopify

                # Run the pipeline directly
                try:
                    # Create a new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Run async extraction
                    product_data = loop.run_until_complete(extract_product())
                    print(f"Extracted: {product_data.product_name}", flush=True)

                    # Run synchronous publishing
                    result = publish_to_shopify()
                    print("Published to Shopify successfully", flush=True)

                    # Load result files
                    with open(os.path.join(script_dir, '..', 'extracted_product.json'), 'r', encoding='utf-8') as f:
                        product = json.load(f)
                    with open(os.path.join(script_dir, '..', 'shopify_response.json'), 'r', encoding='utf-8') as f:
                        shopify = json.load(f)

                    product_id = str(
                        shopify.get('product', {}).get('id', '')
                    )
                    shopify_url = (
                        f"https://{shopify_store_url}"
                        f"/admin/products/{product_id}"
                    )

                    image_url = ''
                    for url in product.get('image_urls', []):
                        if url and url.startswith('http'):
                            image_url = url
                            break

                    with JOBS_LOCK:
                        JOBS[job_id]['status'] = 'done'
                        JOBS[job_id]['result'] = {
                            'product_name': sanitize(
                                product.get('product_name', '')
                            ),
                            'price': sanitize(product.get('price', '')),
                            'description': sanitize(
                                product.get('seo_description', '')
                            ),
                            'image_url': image_url,
                            'shopify_url': shopify_url,
                            'product_id': product_id
                        }
                except asyncio.TimeoutError:
                    with JOBS_LOCK:
                        JOBS[job_id]['status'] = 'error'
                        JOBS[job_id]['error'] = 'Pipeline timed out. Please try again.'
                except Exception as e:
                    error_msg = sanitize(str(e))
                    print(f"[PIPELINE_ERROR] {error_msg}", flush=True)
                    import traceback
                    traceback.print_exc()
                    with JOBS_LOCK:
                        JOBS[job_id]['status'] = 'error'
                        JOBS[job_id]['error'] = error_msg[-200:]
                    
            except Exception as e:
                error_msg = sanitize(str(e))
                print(f"[JOB_ERROR] {error_msg}", flush=True)
                import traceback
                traceback.print_exc()
                with JOBS_LOCK:
                    JOBS[job_id]['status'] = 'error'
                    JOBS[job_id]['error'] = error_msg
            finally:
                try:
                    os.remove(config_path)
                except Exception:
                    pass

        threading.Thread(target=run_job, daemon=True).start()

        return jsonify({'success': True, 'job_id': job_id})

    except Exception as e:
        return jsonify({
            'success': False,
            'error': sanitize(str(e))
        })

@app.route('/status')
def status():
    return jsonify({'status': 'ok'})

@app.route('/job-status/<job_id>')
def job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({'status': 'unknown', 'error': 'Job not found'}), 404
    return jsonify(job)

if __name__ == '__main__':
    app.run(
        debug=False,
        host='0.0.0.0',
        port=5000,
        threaded=True,
        use_reloader=False
    )
