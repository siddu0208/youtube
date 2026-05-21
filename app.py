from flask import Flask, render_template, request, jsonify, send_file
from downloader import YouTubeDownloader
import os

app = Flask(__name__)

# ── Fixed absolute download path ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

downloader = YouTubeDownloader(DOWNLOAD_DIR)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    """Get video information"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'})

        info = downloader.get_video_info(url)
        return jsonify(info)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download', methods=['POST'])
def download_video():
    """Download video"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        download_type = data.get('type', 'hd')
        quality = data.get('quality', '1080p')
        itag = data.get('itag', None)

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'})

        result = None

        if download_type == 'hd':
            result = downloader.download_video_with_audio(url, quality)

        elif download_type == 'progressive':
            if not itag:
                return jsonify({'success': False, 'error': 'itag required'})
            result = downloader.download_progressive(url, int(itag))

        elif download_type == 'audio':
            result = downloader.download_audio_only(url)

        else:
            return jsonify({'success': False, 'error': 'Invalid download type'})

        return jsonify(result)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download-file/<path:filename>')
def download_file(filename):
    """Serve downloaded file to browser"""
    try:
        # ── Build safe absolute path ──
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(DOWNLOAD_DIR, safe_filename)

        print(f"Looking for file: {file_path}")
        print(f"File exists: {os.path.exists(file_path)}")

        # ── List all files in downloads ──
        print("Files in downloads folder:")
        for f in os.listdir(DOWNLOAD_DIR):
            print(f"  - {f}")

        if not os.path.exists(file_path):
            # Try to find similar file
            for f in os.listdir(DOWNLOAD_DIR):
                if safe_filename[:20] in f:
                    file_path = os.path.join(DOWNLOAD_DIR, f)
                    safe_filename = f
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
                'error': f'File not found: {safe_filename}',
                'download_dir': DOWNLOAD_DIR,
                'files': os.listdir(DOWNLOAD_DIR)
            }), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-ffmpeg')
def check_ffmpeg():
    """Check FFmpeg status"""
    status = downloader.check_ffmpeg()
    return jsonify({'ffmpeg': status})

@app.route('/api/list-downloads')
def list_downloads():
    """List all downloaded files"""
    try:
        files = []
        for f in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, f)
            size = os.path.getsize(file_path) / (1024*1024)
            files.append({
                'name': f,
                'size': f"{size:.1f} MB",
                'path': file_path
            })
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("=" * 50)
    print("🎬 YouTube Downloader Web App")
    print(f"📁 Download folder: {DOWNLOAD_DIR}")
    print("🌐 Open: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
    