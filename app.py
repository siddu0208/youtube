from flask import Flask, render_template, request, jsonify, send_file
from downloader import YouTubeDownloader
import os
import traceback

app = Flask(__name__)

# ── Absolute paths ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

downloader = YouTubeDownloader(DOWNLOAD_DIR)

# ════════════════════════════════════════
# Global Error Handlers (Return JSON always)
# ════════════════════════════════════════
@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Route not found: 404'}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'success': False, 'error': 'Method not allowed: 405'}), 405

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    traceback.print_exc()
    return jsonify({'success': False, 'error': str(e)}), 500

# ════════════════════════════════════════
# Routes
# ════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check-ffmpeg', methods=['GET'])
def check_ffmpeg():
    try:
        status = downloader.check_ffmpeg()
        return jsonify({'success': True, 'ffmpeg': status})
    except Exception as e:
        return jsonify({'success': False, 'ffmpeg': False, 'error': str(e)})

@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    try:
        # ── Validate request ──
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Request must be JSON'}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON body'}), 400

        url = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400

        if 'youtube.com' not in url and 'youtu.be' not in url:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400

        print(f"\n[INFO] Fetching video info: {url}")
        result = downloader.get_video_info(url)
        print(f"[INFO] Result: {result.get('success')}")
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        # ── Validate request ──
        if not request.is_json:
            return jsonify({'success': False, 'error': 'Request must be JSON'}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'error': 'Invalid JSON body'}), 400

        url = data.get('url', '').strip()
        download_type = data.get('type', 'hd').strip()
        quality = data.get('quality', '1080p').strip()
        itag = data.get('itag', None)

        print(f"\n[INFO] Download request:")
        print(f"  URL: {url}")
        print(f"  Type: {download_type}")
        print(f"  Quality: {quality}")
        print(f"  Itag: {itag}")

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400

        if 'youtube.com' not in url and 'youtu.be' not in url:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400

        result = None

        if download_type == 'hd':
            print(f"[INFO] Starting HD download: {quality}")
            result = downloader.download_video_with_audio(url, quality)

        elif download_type == 'progressive':
            if not itag:
                return jsonify({'success': False, 'error': 'itag is required for progressive download'}), 400
            print(f"[INFO] Starting progressive download: itag={itag}")
            result = downloader.download_progressive(url, int(itag))

        elif download_type == 'audio':
            print(f"[INFO] Starting audio download")
            result = downloader.download_audio_only(url)

        else:
            return jsonify({'success': False, 'error': f'Invalid download type: {download_type}'}), 400

        if result is None:
            return jsonify({'success': False, 'error': 'Download returned no result'}), 500

        print(f"[INFO] Download result: {result}")
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download-file/<path:filename>', methods=['GET'])
def download_file(filename):
    try:
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(DOWNLOAD_DIR, safe_filename)

        print(f"\n[INFO] File request: {safe_filename}")
        print(f"[INFO] Full path: {file_path}")
        print(f"[INFO] Exists: {os.path.exists(file_path)}")

        # ── List downloads folder ──
        all_files = os.listdir(DOWNLOAD_DIR)
        print(f"[INFO] Files in downloads: {all_files}")

        if not os.path.exists(file_path):
            # Try fuzzy match
            for f in all_files:
                if f.endswith('.mp4') and safe_filename[:15].lower() in f.lower():
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    safe_filename = f
                    print(f"[INFO] Found match: {f}")
                    break

        if os.path.exists(file_path):
            return send_file(
                file_path,
                as_attachment=True,
                download_name=safe_filename,
                mimetype='video/mp4'
            )
        else:
            return jsonify({
                'success': False,
                'error': f'File not found: {safe_filename}',
                'available_files': all_files
            }), 404

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/list-downloads', methods=['GET'])
def list_downloads():
    try:
        files = []
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(('.mp4', '.mp3', '.webm')):
                fp = os.path.join(DOWNLOAD_DIR, f)
                size = os.path.getsize(fp) / (1024 * 1024)
                files.append({
                    'name': f,
                    'size': f"{size:.1f} MB"
                })
        return jsonify({'success': True, 'files': files, 'count': len(files)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── Test route ──
@app.route('/api/test', methods=['GET'])
def test():
    return jsonify({
        'success': True,
        'message': 'Flask API is working!',
        'download_dir': DOWNLOAD_DIR,
        'ffmpeg': downloader.check_ffmpeg()
    })

if __name__ == '__main__':
    print("\n" + "="*55)
    print("  🎬 YouTube Downloader - Flask Server")
    print("="*55)
    print(f"  📁 Downloads: {DOWNLOAD_DIR}")
    print(f"  🌐 URL: http://localhost:5000")
    print(f"  🔧 FFmpeg: {'✅ Found' if downloader.check_ffmpeg() else '❌ Missing'}")
    print("="*55 + "\n")
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        use_reloader=False  # Prevent double init
    )
    
