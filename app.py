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

# ── App ──
app = Flask(__name__, template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['JSON_SORT_KEYS'] = False

# ── Paths ──
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

# Create necessary directories
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# ── Init ──
try:
    dl = Downloader(DOWNLOAD_DIR)
    log.info("✓ Downloader ready")
except Exception as e:
    log.error(f"✗ Downloader failed: {e}")
    dl = None

# ════════════════════════════════════════
# Response Helpers
# ════════════════════════════════════════
def send_ok(data=None):
    """Send JSON success"""
    body = {'success': True}
    if data and isinstance(data, dict):
        body.update(data)
    r = jsonify(body)
    r.headers['Content-Type'] = 'application/json'
    return r, 200


def send_err(msg, code=500):
    """Send JSON error - always JSON never HTML"""
    if isinstance(msg, Exception):
        msg = str(msg)
    elif isinstance(msg, dict):
        msg = msg.get('error', str(msg))
    elif not isinstance(msg, str):
        msg = str(msg)

    r = jsonify({'success': False, 'error': msg})
    r.headers['Content-Type'] = 'application/json'
    return r, code


def parse_body():
    """Safely parse JSON request body"""
    try:
        data = request.get_json(force=True, silent=True)
        return data or {}
    except Exception:
        return {}


# ════════════════════════════════════════
# Error Handlers (Always JSON)
# ════════════════════════════════════════
@app.errorhandler(400)
def err_400(e):
    return send_err(f"Bad request: {e}", 400)

@app.errorhandler(404)
def err_404(e):
    return send_err("Not found", 404)

@app.errorhandler(405)
def err_405(e):
    return send_err("Method not allowed", 405)

@app.errorhandler(500)
def err_500(e):
    return send_err(f"Server error: {e}", 500)

@app.errorhandler(Exception)
def err_any(e):
    traceback.print_exc()
    return send_err(str(e), 500)


# ════════════════════════════════════════
# CORS
# ════════════════════════════════════════
@app.after_request
def add_cors(resp):
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp


# ════════════════════════════════════════
# Routes
# ════════════════════════════════════════
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        log.error(f"Template error: {e}")
        return send_err(f"Template not found: {e}", 500)


@app.route('/api/test')
def api_test():
    return send_ok({
        'message':  'API working!',
        'ffmpeg':   dl.check_ffmpeg() if dl else False,
        'dir':      DOWNLOAD_DIR
    })


@app.route('/api/ffmpeg')
def api_ffmpeg():
    try:
        ok = dl.check_ffmpeg() if dl else False
        return send_ok({'ffmpeg': ok})
    except Exception as e:
        return send_ok({'ffmpeg': False})


@app.route('/api/info', methods=['POST', 'OPTIONS'])
def api_info():
    if request.method == 'OPTIONS':
        return send_ok({})
    try:
        if not dl:
            return send_err("Downloader not ready", 500)

        body = parse_body()
        url  = str(body.get('url', '')).strip()

        if not url:
            return send_err("URL required", 400)

        if 'youtube.com' not in url and 'youtu.be' not in url:
            return send_err("Invalid YouTube URL", 400)

        log.info(f"Info: {url}")
        result = dl.get_info(url)

        if not result or not isinstance(result, dict):
            return send_err("No result from downloader", 500)

        if not result.get('success'):
            return send_err(
                result.get('error', 'Unknown error'), 500
            )

        return send_ok(result)

    except Exception as e:
        traceback.print_exc()
        return send_err(str(e), 500)


@app.route('/api/download', methods=['POST', 'OPTIONS'])
def api_download():
    if request.method == 'OPTIONS':
        return send_ok({})
    try:
        if not dl:
            return send_err("Downloader not ready", 500)

        body    = parse_body()
        url     = str(body.get('url',     '')).strip()
        dtype   = str(body.get('type',    'hd')).strip()
        quality = str(body.get('quality', '1080p')).strip()
        itag    = body.get('itag', None)

        log.info(f"Download: type={dtype} quality={quality}")

        if not url:
            return send_err("URL required", 400)

        if 'youtube.com' not in url and 'youtu.be' not in url:
            return send_err("Invalid YouTube URL", 400)

        if dtype not in ['hd', 'progressive', 'audio']:
            return send_err(f"Invalid type: {dtype}", 400)

        # ── Execute ──
        result = None

        if dtype == 'hd':
            result = dl.download_hd(url, quality)

        elif dtype == 'progressive':
            if itag is None:
                return send_err("itag required", 400)
            try:
                itag = int(itag)
            except (ValueError, TypeError):
                return send_err("itag must be integer", 400)
            result = dl.download_progressive(url, itag)

        elif dtype == 'audio':
            result = dl.download_audio(url)

        # ── Validate result ──
        if result is None:
            return send_err("Download returned None", 500)

        if not isinstance(result, dict):
            return send_err(f"Bad result: {type(result)}", 500)

        if not result.get('success'):
            return send_err(
                result.get('error', 'Download failed'), 500
            )

        log.info(f"Done: {result.get('filename')}")
        return send_ok(result)

    except Exception as e:
        traceback.print_exc()
        return send_err(str(e), 500)


@app.route('/api/file/<path:filename>')
def api_file(filename):
    try:
        # Sanitize filename
        name = os.path.basename(filename)
        path = os.path.join(DOWNLOAD_DIR, name)

        log.info(f"File request: {name}")

        # Check if file exists
        if not os.path.exists(path):
            log.warning(f"File not found: {path}")
            
            # Try to find similar file
            if os.path.exists(DOWNLOAD_DIR):
                files = os.listdir(DOWNLOAD_DIR)
                for f in files:
                    if f.endswith(('.mp4', '.m4a', '.webm')):
                        # Match by name prefix (first 20 chars)
                        if name[:20].lower() in f.lower() or f.lower().startswith(name[:15].lower()):
                            path = os.path.join(DOWNLOAD_DIR, f)
                            name = f
                            log.info(f"Found similar file: {f}")
                            break

        if not os.path.exists(path):
            log.error(f"File still not found: {name}")
            # List available files for debugging
            if os.path.exists(DOWNLOAD_DIR):
                available = os.listdir(DOWNLOAD_DIR)
                log.error(f"Available files: {available}")
            return send_err(f"File not found: {name}", 404)

        log.info(f"Sending file: {path}")

        return send_file(
            path,
            as_attachment=True,
            download_name=name,
            mimetype='video/mp4'
        )

    except Exception as e:
        traceback.print_exc()
        log.error(f"File serving error: {str(e)}")
        return send_err(f"Error serving file: {str(e)}", 500)


# ════════════════════════════════════════
# Main
# ════════════════════════════════════════
if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'

    print("\n" + "=" * 50)
    print("  🎬 YouTube Downloader")
    print("=" * 50)
    print(f"  📁 Save path   : {DOWNLOAD_DIR}")
    print(f"  📂 Templates   : {TEMPLATE_DIR}")
    print(f"  🌐 URL         : http://localhost:{port}")
    print(f"  🔧 FFmpeg      : {'✅' if dl and dl.check_ffmpeg() else '❌'}")
    print(f"  🔍 Debug       : {'ON' if debug else 'OFF'}")
    print("=" * 50 + "\n")

    app.run(
        debug=debug,
        host='0.0.0.0',
        port=port,
        use_reloader=False
    )
