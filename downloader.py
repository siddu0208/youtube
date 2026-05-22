
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
        print(f"[INIT] Save path: {self.save_path}")

    # ════════════════════════════════════════
    # Utilities
    # ════════════════════════════════════════
    def clean_filename(self, title):
        """Remove special characters from filename"""
        try:
            name = re.sub(r'[^\w\s\-]', '', str(title))
            name = re.sub(r'\s+', '_', name)
            name = re.sub(r'_+', '_', name)
            name = name.strip('_')[:60]
            return name if name else 'video'
        except Exception:
            return 'video'

    def ok(self, data=None):
        """Return success response"""
        result = {'success': True}
        if data:
            result.update(data)
        return result

    def fail(self, msg):
        """Return error response"""
        return {
            'success': False,
            'error': str(msg)
        }

    def file_size_mb(self, path):
        """Get file size in MB"""
        try:
            return round(os.path.getsize(path) / (1024 * 1024), 1)
        except Exception:
            return 0

    # ════════════════════════════════════════
    # FFmpeg
    # ════════════════════════════════════════
    def check_ffmpeg(self):
        """Check if FFmpeg is available"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True,
                timeout=5
            )
            return True
        except Exception as e:
            print(f"[FFMPEG] Check failed: {e}")
            return False

    def merge(self, video_path, audio_path, output_path):
        """Merge video and audio with FFmpeg"""
        try:
            if not os.path.exists(video_path):
                print(f"[ERROR] Video missing: {video_path}")
                return False

            if not os.path.exists(audio_path):
                print(f"[ERROR] Audio missing: {audio_path}")
                return False

            # Fixed FFmpeg command with -y flag in correct position
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file without asking
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                '-loglevel', 'error',
                output_path
            ]

            print("[MERGE] Running FFmpeg...")
            print(f"[MERGE] Command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                print("[MERGE] ✓ Success")
                return True
            else:
                error_msg = result.stderr if result.stderr else "Unknown error"
                print(f"[MERGE] ✗ Failed: {error_msg}")
                return False

        except subprocess.TimeoutExpired:
            print("[MERGE] ✗ Timeout (>10 minutes)")
            return False
        except FileNotFoundError:
            print("[MERGE] ✗ FFmpeg not found - install FFmpeg first")
            return False
        except Exception as e:
            print(f"[MERGE] ✗ Error: {e}")
            return False

    def cleanup(self, *files):
        """Delete temp files"""
        for f in files:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                    print(f"[CLEAN] Removed: {f}")
                except Exception as e:
                    print(f"[CLEAN] Failed: {e}")

    # ════════════════════════════════════════
    # Get Video Info
    # ════════════════════════════════════════
    def get_info(self, url):
        """Fetch video metadata and stream list"""
        try:
            print(f"\n[INFO] URL: {url}")
            yt = YouTube(str(url))

            # ── Title / Author ──
            try:
                title = str(yt.title or 'Unknown')
            except Exception:
                title = 'Unknown'

            try:
                author = str(yt.author or 'Unknown')
            except Exception:
                author = 'Unknown'

            try:
                length = int(yt.length or 0)
                mins = length // 60
                secs = length % 60
                duration = f"{mins}:{secs:02d}"
            except Exception:
                duration = '0:00'

            try:
                views = f"{int(yt.views):,}" if yt.views else 'N/A'
            except Exception:
                views = 'N/A'

            try:
                thumb = str(yt.thumbnail_url or '')
            except Exception:
                thumb = ''

            # ── Progressive Streams (Video + Audio) ──
            progressive = []
            try:
                for s in yt.streams.filter(
                    progressive=True,
                    file_extension='mp4'
                ).order_by('resolution'):
                    try:
                        size = round(
                            s.filesize / (1024 * 1024), 1
                        ) if s.filesize else 0
                        progressive.append({
                            'itag':       int(s.itag),
                            'resolution': str(s.resolution or 'N/A'),
                            'fps':        int(s.fps or 30),
                            'size':       str(size),
                            'audio':      True
                        })
                    except Exception as e:
                        print(f"[WARN] Stream skip: {e}")
            except Exception as e:
                print(f"[WARN] Progressive error: {e}")

            # ── HD Streams (Video Only) ──
            hd_streams = []
            try:
                seen = set()
                for s in yt.streams.filter(
                    only_video=True,
                    file_extension='mp4'
                ).order_by('resolution'):
                    try:
                        res = str(s.resolution or '')
                        if res and res not in seen:
                            seen.add(res)
                            size = round(
                                s.filesize / (1024 * 1024), 1
                            ) if s.filesize else 0
                            hd_streams.append({
                                'itag':       int(s.itag),
                                'resolution': res,
                                'fps':        int(s.fps or 30),
                                'size':       str(size),
                                'audio':      False
                            })
                    except Exception as e:
                        print(f"[WARN] HD stream skip: {e}")
            except Exception as e:
                print(f"[WARN] HD error: {e}")

            # ── Audio Streams ──
            audio_streams = []
            try:
                for s in yt.streams.filter(only_audio=True):
                    try:
                        size = round(
                            s.filesize / (1024 * 1024), 1
                        ) if s.filesize else 0
                        audio_streams.append({
                            'itag': int(s.itag),
                            'abr':  str(s.abr or 'N/A'),
                            'size': str(size)
                        })
                    except Exception as e:
                        print(f"[WARN] Audio skip: {e}")
            except Exception as e:
                print(f"[WARN] Audio error: {e}")

            print(f"[INFO] ✓ Got info: {title}")
            print(f"[INFO] Progressive: {len(progressive)}")
            print(f"[INFO] HD: {len(hd_streams)}")
            print(f"[INFO] Audio: {len(audio_streams)}")

            return self.ok({
                'title':       title,
                'author':      author,
                'duration':    duration,
                'views':       views,
                'thumbnail':   thumb,
                'progressive': progressive,
                'hd':          hd_streams,
                'audio':       audio_streams
            })

        except Exception as e:
            traceback.print_exc()
            return self.fail(f"Failed to get video info: {str(e)}")

    # ════════════════════════════════════════
    # Download HD (FFmpeg merge)
    # ════════════════════════════════════════
    def download_hd(self, url, quality='1080p'):
        """Download high quality video with FFmpeg merge"""
        v_tmp = None
        a_tmp = None

        try:
            print(f"\n[HD] Starting: {quality}")
            yt = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_filename(yt.title)

            # ── Find video stream ──
            order = ['2160p', '1440p', '1080p', '720p', '480p', '360p']
            if quality in order:
                order = order[order.index(quality):]

            v_stream = None
            v_res = None

            for res in order:
                try:
                    s = yt.streams.filter(
                        only_video=True,
                        res=res,
                        file_extension='mp4'
                    ).first()
                    if s:
                        v_stream = s
                        v_res = res
                        print(f"[HD] Video: {res}")
                        break
                except Exception:
                    continue

            if not v_stream:
                try:
                    v_stream = yt.streams.filter(
                        only_video=True,
                        file_extension='mp4'
                    ).order_by('resolution').last()
                    v_res = str(
                        v_stream.resolution
                    ) if v_stream else 'unknown'
                except Exception as e:
                    return self.fail(f"No video stream: {e}")

            if not v_stream:
                return self.fail("No video stream found")

            # ── Find audio stream ──
            try:
                a_stream = yt.streams.filter(
                    only_audio=True
                ).order_by('abr').last()
            except Exception as e:
                return self.fail(f"No audio stream: {e}")

            if not a_stream:
                return self.fail("No audio stream found")

            # ── Setup paths ──
            v_tmp  = os.path.join(self.save_path, f"{name}_v.mp4")
            a_tmp  = os.path.join(self.save_path, f"{name}_a.mp4")
            output = os.path.join(self.save_path, f"{name}_{v_res}.mp4")

            # ── Download video ──
            print(f"[HD] Downloading video ({v_res})...")
            try:
                v_stream.download(
                    output_path=self.save_path,
                    filename=f"{name}_v.mp4"
                )
            except Exception as e:
                return self.fail(f"Video download failed: {e}")

            if not os.path.exists(v_tmp):
                return self.fail("Video file not created")

            # ── Download audio ──
            print("[HD] Downloading audio...")
            try:
                a_stream.download(
                    output_path=self.save_path,
                    filename=f"{name}_a.mp4"
                )
            except Exception as e:
                self.cleanup(v_tmp)
                return self.fail(f"Audio download failed: {e}")

            if not os.path.exists(a_tmp):
                self.cleanup(v_tmp)
                return self.fail("Audio file not created")

            # ── Merge ──
            print("[HD] Merging...")
            merged = self.merge(v_tmp, a_tmp, output)
            self.cleanup(v_tmp, a_tmp)

            if not merged:
                return self.fail("FFmpeg merge failed - make sure FFmpeg is installed")

            if not os.path.exists(output):
                return self.fail("Output file not created after merge")

            size  = self.file_size_mb(output)
            fname = os.path.basename(output)
            print(f"[HD] ✓ Done: {fname} ({size} MB)")

            return self.ok({
                'filename':   fname,
                'resolution': str(v_res),
                'size':       f"{size} MB"
            })

        except Exception as e:
            traceback.print_exc()
            self.cleanup(v_tmp, a_tmp)
            return self.fail(str(e))

    # ════════════════════════════════════════
    # Download Progressive
    # ════════════════════════════════════════
    def download_progressive(self, url, itag):
        """Download video+audio combined stream"""
        try:
            print(f"\n[PROG] itag={itag}")
            yt = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_filename(yt.title)

            stream = yt.streams.get_by_itag(int(itag))
            if not stream:
                return self.fail(f"Stream not found: itag={itag}")

            res    = str(stream.resolution or 'unknown')
            fname  = f"{name}_{res}.mp4"
            output = os.path.join(self.save_path, fname)

            print(f"[PROG] Downloading: {fname}")
            stream.download(
                output_path=self.save_path,
                filename=fname
            )

            if not os.path.exists(output):
                return self.fail("File not created")

            size = self.file_size_mb(output)
            print(f"[PROG] ✓ Done: {fname} ({size} MB)")

            return self.ok({
                'filename':   fname,
                'resolution': res,
                'size':       f"{size} MB"
            })

        except Exception as e:
            traceback.print_exc()
            return self.fail(str(e))

    # ════════════════════════════════════════
    # Download Audio
    # ════════════════════════════════════════
    def download_audio(self, url):
        """Download audio only"""
        try:
            print(f"\n[AUDIO] Starting...")
            yt = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_filename(yt.title)

            stream = yt.streams.filter(
                only_audio=True
            ).order_by('abr').last()

            if not stream:
                return self.fail("No audio stream found")

            fname  = f"{name}_audio.mp4"
            output = os.path.join(self.save_path, fname)

            print(f"[AUDIO] Downloading: {fname}")
            stream.download(
                output_path=self.save_path,
                filename=fname
            )

            if not os.path.exists(output):
                return self.fail("Audio file not created")

            size = self.file_size_mb(output)
            print(f"[AUDIO] ✓ Done: {fname} ({size} MB)")

            return self.ok({
                'filename': fname,
                'bitrate':  str(stream.abr or 'N/A'),
                'size':     f"{size} MB"
            })

        except Exception as e:
            traceback.print_exc()
            return self.fail(str(e))
