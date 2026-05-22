from flask import Flask, render_template, request, jsonify, send_file
from downloader import Downloader
import os
import traceback
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['JSON_SORT_KEYS'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

try:
    dl = Downloader(DOWNLOAD_DIR)
    log.info("✓ Downloader ready")
except Exception as e:
    log.error(f"✗ Downloader failed: {e}")
    dl = None

def send_ok(data=None):
    body = {'success': True}
    if data and isinstance(data, dict):
        body.update(data)
    return jsonify(body), 200

def send_err(msg, code=500):
    if isinstance(msg, Exception):
        msg = str(msg)
    elif isinstance(msg, dict):
        msg = msg.get('error', str(msg))
    return jsonify({'success': False, 'error': str(msg)}), code

def parse_body():
    try:
        return request.get_json(force=True, silent=True) or {}
    except Exception:
        return {}

@app.errorhandler(404)
def err_404(e):
    return send_err("Not found", 404)

@app.errorhandler(Exception)
def err_any(e):
    traceback.print_exc()
    return send_err(str(e), 500)

@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        return send_err(f"Failed to load page: {e}", 500)

@app.route('/api/ffmpeg')
def api_ffmpeg():
    try:
        ok = dl.check_ffmpeg() if dl else False
        return send_ok({'ffmpeg': ok})
    except Exception:
        return send_ok({'ffmpeg': False})

@app.route('/api/info', methods=['POST', 'OPTIONS'])
def api_info():
    if request.method == 'OPTIONS':
        return send_ok({})
    if not dl:
        return send_err("Downloader not ready", 500)
    body = parse_body()
    url = str(body.get('url', '')).strip()
    if not url or ('youtube.com' not in url and 'youtu.be' not in url):
        return send_err("Valid YouTube URL required", 400)
    log.info(f"Info: {url}")
    result = dl.get_info(url)
    if not result or not result.get('success'):
        return send_err(result.get('error', 'Unknown error'), 500)
    return send_ok(result)

@app.route('/api/download', methods=['POST', 'OPTIONS'])
def api_download():
    if request.method == 'OPTIONS':
        return send_ok({})
    if not dl:
        return send_err("Downloader not ready", 500)
    body = parse_body()
    url = str(body.get('url', '')).strip()
    dtype = str(body.get('type', 'hd')).strip()
    quality = str(body.get('quality', '1080p')).strip()
    itag = body.get('itag')

    if not url or ('youtube.com' not in url and 'youtu.be' not in url):
        return send_err("Valid YouTube URL required", 400)
    if dtype not in ['hd', 'progressive', 'audio']:
        return send_err(f"Invalid type: {dtype}", 400)

    log.info(f"Download: type={dtype} quality={quality}")
    try:
        if dtype == 'hd':
            result = dl.download_hd(url, quality)
        elif dtype == 'progressive':
            if itag is None:
                return send_err("itag required for progressive download", 400)
            result = dl.download_progressive(url, int(itag))
        else:  # audio
            result = dl.download_audio(url)

        if not result or not result.get('success'):
            return send_err(result.get('error', 'Download failed'), 500)
        return send_ok(result)
    except Exception as e:
        traceback.print_exc()
        return send_err(str(e), 500)

@app.route('/api/file/<path:filename>')
def api_file(filename):
    try:
        safe_name = os.path.basename(filename)
        filepath = os.path.join(DOWNLOAD_DIR, safe_name)
        if not os.path.exists(filepath):
            # Try fuzzy match only if exact not found
            for f in os.listdir(DOWNLOAD_DIR):
                if f.endswith('.mp4') and safe_name.replace('.mp4', '') in f:
                    filepath = os.path.join(DOWNLOAD_DIR, f)
                    break
        if not os.path.exists(filepath):
            return send_err(f"File not found: {safe_name}", 404)
        return send_file(filepath, as_attachment=True, download_name=os.path.basename(filepath), mimetype='video/mp4')
    except Exception as e:
        return send_err(str(e), 500)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    print("\n" + "="*50)
    print("  🎬 YouTube Downloader Ready")
    print("="*50)
    print(f"  📁 Save path : {DOWNLOAD_DIR}")
    print(f"  🌐 URL       : http://localhost:{port}")
    print(f"  🔧 FFmpeg    : {'✅' if dl and dl.check_ffmpeg() else '❌'}")
    print("="*50 + "\n")
    app.run(debug=debug, host='0.0.0.0', port=port, use_reloader=False)
