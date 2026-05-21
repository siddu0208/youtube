from flask import (
    Flask, render_template,
    request, jsonify, send_file
)
from downloader import Downloader
import os
import traceback
import logging

# ── Logging ──
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

# ── Flask App ──
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
app.config['JSON_SORT_KEYS']     = False

# ── Paths ──
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

log.info(f"Base dir     : {BASE_DIR}")
log.info(f"Download dir : {DOWNLOAD_DIR}")

# ── Downloader instance ──
try:
    dl = Downloader(DOWNLOAD_DIR)
    log.info("✓ Downloader ready")
except Exception as e:
    log.error(f"✗ Downloader failed: {e}")
    dl = None

# ════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════
def json_ok(data=None):
    """Return JSON success response"""
    body = {'success': True}
    if isinstance(data, dict):
        body.update(data)
    resp = jsonify(body)
    resp.headers['Content-Type'] = 'application/json'
    return resp

def json_err(msg, code=500):
    """Return JSON error response — NEVER returns HTML"""
    # Convert anything to string safely
    if isinstance(msg, Exception):
        msg = str(msg)
    elif isinstance(msg, dict):
        msg = msg.get('error', str(msg))
    elif not isinstance(msg, str):
        msg = str(msg)

    log.error(f"[ERR {code}] {msg}")
    resp = jsonify({'success': False, 'error': msg})
    resp.headers['Content-Type'] = 'application/json'
    return resp, code

def get_json():
    """Safely parse request JSON body"""
    try:
        data = request.get_json(force=True, silent=True)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def validate_url(url):
    """Validate YouTube URL"""
    url = str(url).strip()
    if not url:
        return None, "URL is required"
    if 'youtube.com' not in url and 'youtu.be' not in url:
        return None, "Invalid YouTube URL"
    return url, None

# ════════════════════════════════════════════
# Global Error Handlers — Always JSON
# ════════════════════════════════════════════
@app.errorhandler(400)
def err400(e):
    return json_err(f"Bad request: {str(e)}", 400)

@app.errorhandler(404)
def err404(e):
    return json_err("Route not found — check API path", 404)

@app.errorhandler(405)
def err405(e):
    return json_err("Method not allowed", 405)

@app.errorhandler(413)
def err413(e):
    return json_err("File too large", 413)

@app.errorhandler(500)
def err500(e):
    traceback.print_exc()
    return json_err(f"Server error: {str(e)}", 500)

@app.errorhandler(Exception)
def err_any(e):
    traceback.print_exc()
    return json_err(str(e), 500)

# ════════════════════════════════════════════
# CORS Headers
# ════════════════════════════════════════════
@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return resp

# ════════════════════════════════════════════
# Page Routes
# ════════════════════════════════════════════
@app.route('/', methods=['GET'])
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        traceback.print_exc()
        return f"Template error: {str(e)}", 500

# ════════════════════════════════════════════
# API Routes
# ════════════════════════════════════════════

# ── Test ──
@app.route('/api/test', methods=['GET'])
def api_test():
    try:
        return json_ok({
            'message'  : 'API is working!',
            'base_dir' : BASE_DIR,
            'dl_dir'   : DOWNLOAD_DIR,
            'dl_ready' : dl is not None,
            'ffmpeg'   : dl.check_ffmpeg() if dl else False,
            'routes'   : [
                'GET  /api/test',
                'GET  /api/ffmpeg',
                'POST /api/info',
                'POST /api/download',
                'GET  /api/file/<filename>',
                'GET  /api/files',
            ]
        })
    except Exception as e:
        traceback.print_exc()
        return json_err(str(e))

# ── FFmpeg check ──
@app.route('/api/ffmpeg', methods=['GET', 'OPTIONS'])
def api_ffmpeg():
    if request.method == 'OPTIONS':
        return json_ok({})
    try:
        status = dl.check_ffmpeg() if dl else False
        return json_ok({'ffmpeg': status})
    except Exception as e:
        traceback.print_exc()
        return json_ok({'ffmpeg': False, 'error': str(e)})

# ── Video info ──
@app.route('/api/info', methods=['GET', 'POST', 'OPTIONS'])
def api_info():
    if request.method == 'OPTIONS':
        return json_ok({})

    try:
        if not dl:
            return json_err("Downloader not initialized", 500)

        body = get_json()
        url, err = validate_url(body.get('url', ''))
        if err:
            return json_err(err, 400)

        log.info(f"[INFO] {url}")
        result = dl.get_info(url)

        if not result or not isinstance(result, dict):
            return json_err("Downloader returned invalid data", 500)

        if not result.get('success'):
            return json_err(
                result.get('error', 'Failed to get video info'), 500
            )

        return json_ok(result)

    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), 500)

# ── Download ──
@app.route('/api/download', methods=['GET', 'POST', 'OPTIONS'])
def api_download():
    if request.method == 'OPTIONS':
        return json_ok({})

    try:
        if not dl:
            return json_err("Downloader not initialized", 500)

        body    = get_json()
        url, err = validate_url(body.get('url', ''))
        if err:
            return json_err(err, 400)

        dtype   = str(body.get('type',    'hd')).strip().lower()
        quality = str(body.get('quality', '1080p')).strip()
        itag    = body.get('itag', None)

        log.info(f"[DL] type={dtype} quality={quality} url={url}")

        VALID_TYPES = ['hd', 'progressive', 'audio']
        if dtype not in VALID_TYPES:
            return json_err(
                f"Invalid type '{dtype}'. Use: {', '.join(VALID_TYPES)}", 400
            )

        # ── Execute ──
        result = None

        if dtype == 'hd':
            result = dl.download_hd(url, quality)

        elif dtype == 'progressive':
            if itag is None:
                return json_err("itag is required for progressive", 400)
            try:
                itag = int(itag)
            except (ValueError, TypeError):
                return json_err("itag must be a number", 400)
            result = dl.download_progressive(url, itag)

        elif dtype == 'audio':
            result = dl.download_audio(url)

        # ── Validate result ──
        if result is None:
            return json_err("Download function returned None", 500)

        if not isinstance(result, dict):
            return json_err(f"Invalid result type: {type(result)}", 500)

        if not result.get('success'):
            return json_err(
                result.get('error', 'Download failed'), 500
            )

        log.info(f"[DL] Done: {result.get('filename')}")
        return json_ok(result)

    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), 500)

# ── Serve file ──
@app.route('/api/file/<path:filename>', methods=['GET'])
def api_file(filename):
    try:
        safe = os.path.basename(filename)
        path = os.path.join(DOWNLOAD_DIR, safe)

        log.info(f"[FILE] Request: {safe}")
        log.info(f"[FILE] Path: {path}")
        log.info(f"[FILE] Exists: {os.path.exists(path)}")

        if not os.path.exists(path):
            # Try fuzzy match
            try:
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.endswith('.mp4'):
                        if safe[:15].lower() in f.lower():
                            path = os.path.join(DOWNLOAD_DIR, f)
                            safe = f
                            log.info(f"[FILE] Fuzzy match: {f}")
                            break
            except Exception as fe:
                log.warning(f"[FILE] Fuzzy error: {fe}")

        if not os.path.exists(path):
            # List all files for debugging
            try:
                files = os.listdir(DOWNLOAD_DIR)
                log.error(f"[FILE] Not found. Available: {files}")
            except Exception:
                pass
            return json_err(f"File not found: {safe}", 404)

        log.info(f"[FILE] Serving: {path}")
        return send_file(
            path,
            as_attachment=True,
            download_name=safe,
            mimetype='video/mp4'
        )

    except Exception as e:
        traceback.print_exc()
        return json_err(str(e), 500)

# ── List files ──
@app.route('/api/files', methods=['GET'])
def api_files():
    try:
        files = []
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(('.mp4', '.mp3', '.webm', '.m4a')):
                fp   = os.path.join(DOWNLOAD_DIR, f)
                size = round(os.path.getsize(fp) / (1024 * 1024), 1)
                files.append({'name': f, 'size': f"{size} MB"})
        return json_ok({'files': files, 'count': len(files)})
    except Exception as e:
        traceback.print_exc()
        return json_err(str(e))

# ════════════════════════════════════════════
# Print all routes on startup
# ════════════════════════════════════════════
def print_routes():
    print("\n" + "=" * 55)
    print("  Registered Routes:")
    print("=" * 55)
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        methods = ', '.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        print(f"  {methods:8}  {rule.rule}")
    print("=" * 55 + "\n")

# ════════════════════════════════════════════
# Main
# ════════════════════════════════════════════
if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'

    print("\n" + "=" * 55)
    print("  🎬 YouTube Downloader")
    print("=" * 55)
    print(f"  📁 Downloads : {DOWNLOAD_DIR}")
    print(f"  🌐 URL       : http://localhost:{port}")
    print(f"  🔧 Debug     : {debug}")
    print(f"  🔧 FFmpeg    : {'✅ Found' if dl and dl.check_ffmpeg() else '❌ Missing'}")
    print("=" * 55)

    print_routes()

    app.run(
        debug=debug,
        host='0.0.0.0',
        port=port,
        use_reloader=False
    )
