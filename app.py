import sys
import os
import io
import json
import uuid
import threading
import subprocess

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

from flask import (Flask, request, jsonify, 
                   render_template, session, redirect)
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = 'ecomagent-secret-key-2024-fixed'
app.config['JSON_AS_ASCII'] = False

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

        # Write a per-job config file for the pipeline
        config_path = f'temp_config_{job_id}.json'
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

                result = subprocess.run(
                    [sys.executable, 'src/run_pipeline.py'],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=300,
                    env={
                        **os.environ,
                        'PYTHONIOENCODING': 'utf-8',
                        'PYTHONUTF8': '1',
                        'PIPELINE_CONFIG_PATH': config_path
                    }
                )

                if result.returncode != 0:
                    error = sanitize(
                        result.stderr or result.stdout or 'Pipeline failed'
                    )
                    with JOBS_LOCK:
                        JOBS[job_id]['status'] = 'error'
                        JOBS[job_id]['error'] = error[-200:]
                    return

                # Load result files
                with open('extracted_product.json', 'r', encoding='utf-8') as f:
                    product = json.load(f)
                with open('shopify_response.json', 'r', encoding='utf-8') as f:
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
            except subprocess.TimeoutExpired:
                with JOBS_LOCK:
                    JOBS[job_id]['status'] = 'error'
                    JOBS[job_id]['error'] = 'Pipeline timed out. Please try again.'
            except Exception as e:
                with JOBS_LOCK:
                    JOBS[job_id]['status'] = 'error'
                    JOBS[job_id]['error'] = sanitize(str(e))
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
        threaded=True
    )
