from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import subprocess
import re
import traceback

class Downloader:
    def __init__(self, save_path):
        self.save_path = os.path.abspath(save_path)
        os.makedirs(self.save_path, exist_ok=True)

    def clean_filename(self, title):
        try:
            name = re.sub(r'[^\w\s\-]', '', str(title))
            name = re.sub(r'\s+', '_', name)
            name = re.sub(r'_+', '_', name)
            name = name.strip('_')[:60]
            return name if name else 'video'
        except Exception:
            return 'video'

    def ok(self, data=None):
        result = {'success': True}
        if data:
            result.update(data)
        return result

    def fail(self, msg):
        return {'success': False, 'error': str(msg)}

    def file_size_mb(self, path):
        try:
            return round(os.path.getsize(path) / (1024 * 1024), 1)
        except Exception:
            return 0

    def check_ffmpeg(self):
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except Exception:
            return False

    def merge(self, video_path, audio_path, output_path):
        try:
            if not os.path.exists(video_path) or not os.path.exists(audio_path):
                return False
            cmd = ['ffmpeg', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', output_path, '-y', '-loglevel', 'error']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return result.returncode == 0
        except Exception:
            return False

    def cleanup(self, *files):
        for f in files:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def get_info(self, url):
        try:
            yt = YouTube(str(url))
            title = str(yt.title or 'Unknown')
            author = str(yt.author or 'Unknown')
            length = int(yt.length or 0)
            duration = f"{length//60}:{length%60:02d}"
            views = f"{int(yt.views):,}" if yt.views else 'N/A'
            thumb = str(yt.thumbnail_url or '')

            progressive = []
            for s in yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution'):
                size = round(s.filesize / (1024 * 1024), 1) if s.filesize else 0
                progressive.append({'itag': int(s.itag), 'resolution': str(s.resolution or 'N/A'), 'fps': int(s.fps or 30), 'size': str(size)})

            hd_streams = []
            seen = set()
            for s in yt.streams.filter(only_video=True, file_extension='mp4').order_by('resolution'):
                res = str(s.resolution or '')
                if res and res not in seen:
                    seen.add(res)
                    size = round(s.filesize / (1024 * 1024), 1) if s.filesize else 0
                    hd_streams.append({'itag': int(s.itag), 'resolution': res, 'fps': int(s.fps or 30), 'size': str(size)})

            audio_streams = []
            for s in yt.streams.filter(only_audio=True):
                size = round(s.filesize / (1024 * 1024), 1) if s.filesize else 0
                audio_streams.append({'itag': int(s.itag), 'abr': str(s.abr or 'N/A'), 'size': str(size)})

            return self.ok({'title': title, 'author': author, 'duration': duration, 'views': views, 'thumbnail': thumb, 'progressive': progressive, 'hd': hd_streams, 'audio': audio_streams})
        except Exception as e:
            traceback.print_exc()
            return self.fail(f"Failed to get video info: {str(e)}")

    def download_hd(self, url, quality='1080p'):
        if not self.check_ffmpeg():
            return self.fail("FFmpeg is required for HD/4K downloads but not found on server")
        v_tmp = a_tmp = None
        try:
            yt = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_filename(yt.title)

            order = ['2160p', '1440p', '1080p', '720p', '480p', '360p']
            if quality in order:
                order = order[order.index(quality):]

            v_stream = None
            v_res = None
            for res in order:
                s = yt.streams.filter(only_video=True, res=res, file_extension='mp4').first()
                if s:
                    v_stream = s
                    v_res = res
                    break
            if not v_stream:
                v_stream = yt.streams.filter(only_video=True, file_extension='mp4').order_by('resolution').last()
                v_res = str(v_stream.resolution) if v_stream else 'unknown'

            if not v_stream:
                return self.fail("No video stream found")

            a_stream = yt.streams.filter(only_audio=True).order_by('abr').last()
            if not a_stream:
                return self.fail("No audio stream found")

            v_tmp = os.path.join(self.save_path, f"{name}_v.mp4")
            a_tmp = os.path.join(self.save_path, f"{name}_a.mp4")
            output = os.path.join(self.save_path, f"{name}_{v_res}.mp4")

            v_stream.download(output_path=self.save_path, filename=f"{name}_v.mp4")
            if not os.path.exists(v_tmp):
                return self.fail("Video download failed")

            a_stream.download(output_path=self.save_path, filename=f"{name}_a.mp4")
            if not os.path.exists(a_tmp):
                self.cleanup(v_tmp)
                return self.fail("Audio download failed")

            if not self.merge(v_tmp, a_tmp, output):
                self.cleanup(v_tmp, a_tmp)
                return self.fail("FFmpeg merge failed")

            self.cleanup(v_tmp, a_tmp)
            if not os.path.exists(output):
                return self.fail("Output file not created")

            size = self.file_size_mb(output)
            return self.ok({'filename': os.path.basename(output), 'resolution': str(v_res), 'size': f"{size} MB"})
        except Exception as e:
            self.cleanup(v_tmp, a_tmp)
            return self.fail(str(e))

    def download_progressive(self, url, itag):
        try:
            yt = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_filename(yt.title)
            stream = yt.streams.get_by_itag(int(itag))
            if not stream:
                return self.fail(f"Stream not found: itag={itag}")
            res = str(stream.resolution or 'unknown')
            fname = f"{name}_{res}.mp4"
            output = os.path.join(self.save_path, fname)
            stream.download(output_path=self.save_path, filename=fname)
            if not os.path.exists(output):
                return self.fail("File not created")
            size = self.file_size_mb(output)
            return self.ok({'filename': fname, 'resolution': res, 'size': f"{size} MB"})
        except Exception as e:
            return self.fail(str(e))

    def download_audio(self, url):
        try:
            yt = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_filename(yt.title)
            stream = yt.streams.filter(only_audio=True).order_by('abr').last()
            if not stream:
                return self.fail("No audio stream found")
            fname = f"{name}_audio.mp4"
            output = os.path.join(self.save_path, fname)
            stream.download(output_path=self.save_path, filename=fname)
            if not os.path.exists(output):
                return self.fail("Audio file not created")
            size = self.file_size_mb(output)
            return self.ok({'filename': fname, 'bitrate': str(stream.abr or 'N/A'), 'size': f"{size} MB"})
        except Exception as e:
            return self.fail(str(e))
