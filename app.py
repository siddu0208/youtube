from flask import (
    Flask, render_template,
    request, jsonify,
    send_file, Response
)
from downloader import YouTubeDownloader
import os
import traceback
import logging

# ── Setup logging ──
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ── Flask App ──
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['JSON_SORT_KEYS'] = False
app.config['PROPAGATE_EXCEPTIONS'] = False

# ── Paths ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logger.info(f"Base dir: {BASE_DIR}")
logger.info(f"Download dir: {DOWNLOAD_DIR}")

# ── Downloader ──
try:
    downloader = YouTubeDownloader(DOWNLOAD_DIR)
    logger.info("Downloader initialized successfully")
except Exception as e:
    logger.error(f"Downloader init failed: {e}")
    downloader = None

# ════════════════════════════════════════════
# Helper: Always return JSON
# ════════════════════════════════════════════
def json_error(message, status=500):
    """Always return proper JSON error response"""
    response = jsonify({
        'success': False,
        'error': str(message)
    })
    response.status_code = status
    response.headers['Content-Type'] = 'application/json'
    return response

def json_success(data):
    """Always return proper JSON success response"""
    response = jsonify(data)
    response.status_code = 200
    response.headers['Content-Type'] = 'application/json'
    return response

# ════════════════════════════════════════════
# Global Error Handlers
# ════════════════════════════════════════════
@app.errorhandler(400)
def bad_request(e):
    logger.error(f"400 Error: {e}")
    return json_error(f"Bad Request: {str(e)}", 400)

@app.errorhandler(404)
def not_found(e):
    logger.error(f"404 Error: {e}")
    return json_error("Page not found", 404)

@app.errorhandler(405)
def method_not_allowed(e):
    logger.error(f"405 Error: {e}")
    return json_error("Method not allowed", 405)

@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 Error: {e}")
    traceback.print_exc()
    return json_error(f"Server error: {str(e)}", 500)

@app.errorhandler(Exception)
def handle_all_exceptions(e):
    logger.error(f"Unhandled exception: {e}")
    traceback.print_exc()
    return json_error(str(e), 500)

# ════════════════════════════════════════════
# CORS Headers (Fix for deployment)
# ════════════════════════════════════════════
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    # Force JSON content type for API routes
    if request.path.startswith('/api/'):
        if response.content_type == 'text/html; charset=utf-8':
            response.content_type = 'application/json'
    return response

# ════════════════════════════════════════════
# Routes
# ════════════════════════════════════════════
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Template error: {e}")
        return json_error(f"Template error: {str(e)}", 500)

# ── Test Route ──
@app.route('/api/test', methods=['GET'])
def test():
    try:
        return json_success({
            'success': True,
            'message': 'API is working!',
            'download_dir': DOWNLOAD_DIR,
            'dir_exists': os.path.exists(DOWNLOAD_DIR),
            'downloader_ok': downloader is not None,
            'ffmpeg': downloader.check_ffmpeg() if downloader else False
        })
    except Exception as e:
        return json_error(str(e))

# ── FFmpeg Check ──
@app.route('/api/check-ffmpeg', methods=['GET', 'OPTIONS'])
def check_ffmpeg():
    if request.method == 'OPTIONS':
        return json_success({})
    try:
        if not downloader:
            return json_success({'ffmpeg': False, 'error': 'Downloader not initialized'})
        status = downloader.check_ffmpeg()
        return json_success({'ffmpeg': status})
    except Exception as e:
        logger.error(f"FFmpeg check error: {e}")
        return json_success({'ffmpeg': False, 'error': str(e)})

# ── Video Info ──
@app.route('/api/video-info', methods=['POST', 'OPTIONS'])
def get_video_info():
    if request.method == 'OPTIONS':
        return json_success({})

    try:
        # ── Check downloader ──
        if not downloader:
            return json_error("Downloader not initialized", 500)

        # ── Validate Content-Type ──
        if not request.is_json:
            logger.warning(f"Non-JSON request: {request.content_type}")
            return json_error(
                "Content-Type must be application/json", 400
            )

        # ── Parse JSON safely ──
        try:
            data = request.get_json(force=True, silent=True)
        except Exception as e:
            return json_error(f"Invalid JSON: {str(e)}", 400)

        if not data:
            return json_error("Request body is empty or invalid JSON", 400)

        url = str(data.get('url', '')).strip()

        if not url:
            return json_error("URL is required", 400)

        # ── Validate URL ──
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return json_error("Please enter a valid YouTube URL", 400)

        logger.info(f"Fetching info: {url}")

        # ── Get info ──
        result = downloader.get_video_info(url)

        if result is None:
            return json_error("get_video_info returned None", 500)

        logger.info(f"Info result: success={result.get('success')}")
        return json_success(result)

    except Exception as e:
        logger.error(f"video-info error: {e}")
        traceback.print_exc()
        return json_error(str(e), 500)

# ── Download ──
@app.route('/api/download', methods=['POST', 'OPTIONS'])
def download_video():
    if request.method == 'OPTIONS':
        return json_success({})

    try:
        # ── Check downloader ──
        if not downloader:
            return json_error("Downloader not initialized", 500)

        # ── Validate Content-Type ──
        if not request.is_json:
            return json_error(
                "Content-Type must be application/json", 400
            )

        # ── Parse JSON ──
        try:
            data = request.get_json(force=True, silent=True)
        except Exception as e:
            return json_error(f"Invalid JSON: {str(e)}", 400)

        if not data:
            return json_error("Empty request body", 400)

        url = str(data.get('url', '')).strip()
        download_type = str(data.get('type', 'hd')).strip()
        quality = str(data.get('quality', '1080p')).strip()
        itag = data.get('itag', None)

        logger.info(f"Download request: type={download_type}, quality={quality}, url={url}")

        # ── Validate ──
        if not url:
            return json_error("URL is required", 400)

        if 'youtube.com' not in url and 'youtu.be' not in url:
            return json_error("Invalid YouTube URL", 400)

        valid_types = ['hd', 'progressive', 'audio']
        if download_type not in valid_types:
            return json_error(
                f"Invalid type. Use: {', '.join(valid_types)}", 400
            )

        # ── Execute download ──
        result = None

        if download_type == 'hd':
            logger.info(f"Starting HD download: {quality}")
            result = downloader.download_video_with_audio(url, quality)

        elif download_type == 'progressive':
            if not itag:
                return json_error("itag required for progressive", 400)
            try:
                itag_int = int(itag)
            except (ValueError, TypeError):
                return json_error("itag must be a number", 400)
            logger.info(f"Starting progressive: itag={itag_int}")
            result = downloader.download_progressive(url, itag_int)

        elif download_type == 'audio':
            logger.info("Starting audio download")
            result = downloader.download_audio_only(url)

        # ── Validate result ──
        if result is None:
            return json_error("Download function returned None", 500)

        if not isinstance(result, dict):
            return json_error(
                f"Invalid result type: {type(result)}", 500
            )

        logger.info(f"Download result: {result}")
        return json_success(result)

    except Exception as e:
        logger.error(f"Download error: {e}")
        traceback.print_exc()
        return json_error(str(e), 500)

# ── Serve File ──
@app.route('/api/download-file/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        safe_name = os.path.basename(filename)
        file_path = os.path.join(DOWNLOAD_DIR, safe_name)

        logger.info(f"File request: {safe_name}")

        # ── Check file exists ──
        if not os.path.exists(file_path):
            # Try fuzzy match
            try:
                all_files = os.listdir(DOWNLOAD_DIR)
                for f in all_files:
                    if (f.endswith('.mp4') and
                        safe_name[:10].lower() in f.lower()):
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        safe_name = f
                        logger.info(f"Fuzzy match: {f}")
                        break
            except Exception as e:
                logger.warning(f"Fuzzy match error: {e}")

        if not os.path.exists(file_path):
            return json_error(
                f"File not found: {safe_name}", 404
            )

        logger.info(f"Serving file: {file_path}")
        return send_file(
            file_path,
            as_attachment=True,
            download_name=safe_name,
            mimetype='video/mp4'
        )

    except Exception as e:
        logger.error(f"File serve error: {e}")
        traceback.print_exc()
        return json_error(str(e), 500)

# ── List Downloads ──
@app.route('/api/list-downloads', methods=['GET'])
def list_downloads():
    try:
        files = []
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(('.mp4', '.mp3', '.webm', '.m4a')):
                fp = os.path.join(DOWNLOAD_DIR, f)
                try:
                    size = os.path.getsize(fp) / (1024*1024)
                    files.append({
                        'name': f,
                        'size': f"{size:.1f} MB"
                    })
                except Exception:
                    continue

        return json_success({
            'success': True,
            'files': files,
            'count': len(files),
            'download_dir': DOWNLOAD_DIR
        })
    except Exception as e:
        return json_error(str(e))

# ════════════════════════════════════════════
# Run
# ════════════════════════════════════════════
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'

    print("\n" + "="*55)
    print("  🎬 YouTube Downloader")
    print("="*55)
    print(f"  📁 Downloads : {DOWNLOAD_DIR}")
    print(f"  🌐 Port      : {port}")
    print(f"  🔧 Debug     : {debug}")
    print(f"  🔧 FFmpeg    : {'✅' if downloader and downloader.check_ffmpeg() else '❌'}")
    print("="*55 + "\n")

    app.run(
        debug=debug,
        host='0.0.0.0',
        port=port,
        use_reloader=False
    )
