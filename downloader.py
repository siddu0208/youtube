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
    def clean_name(self, title):
        """Create safe filename"""
        try:
            name = re.sub(r'[^\w\s\-]', '', str(title))
            name = re.sub(r'[\s]+', '_', name)
            name = re.sub(r'_+', '_', name)
            name = name.strip('_')[:60]
            return name if name else 'video'
        except Exception:
            return 'video'

    def ok(self, data=None):
        """Success response dict"""
        out = {'success': True}
        if isinstance(data, dict):
            out.update(data)
        return out

    def fail(self, msg):
        """Error response dict"""
        return {'success': False, 'error': str(msg)}

    def size_mb(self, path):
        """File size in MB"""
        try:
            return round(os.path.getsize(path) / (1024 * 1024), 1)
        except Exception:
            return 0

    def remove(self, *paths):
        """Delete files safely"""
        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    print(f"[RM] {p}")
                except Exception as e:
                    print(f"[RM] Failed: {e}")

    # ════════════════════════════════════════
    # FFmpeg
    # ════════════════════════════════════════
    def check_ffmpeg(self):
        """Return True if FFmpeg is installed"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True
            )
            return True
        except Exception:
            return False

    def ffmpeg_merge(self, video, audio, output):
        """Merge video + audio using FFmpeg"""
        try:
            if not os.path.exists(video):
                print(f"[MERGE] Missing video: {video}")
                return False
            if not os.path.exists(audio):
                print(f"[MERGE] Missing audio: {audio}")
                return False

            cmd = [
                'ffmpeg',
                '-i', video,
                '-i', audio,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                output,
                '-y',
                '-loglevel', 'error'
            ]

            print(f"[MERGE] Running FFmpeg...")
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )

            if r.returncode == 0:
                print("[MERGE] ✓ Done")
                return True
            else:
                print(f"[MERGE] ✗ Error: {r.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("[MERGE] ✗ Timeout")
            return False
        except FileNotFoundError:
            print("[MERGE] ✗ FFmpeg not found")
            return False
        except Exception as e:
            print(f"[MERGE] ✗ {e}")
            return False

    # ════════════════════════════════════════
    # Get Video Info
    # ════════════════════════════════════════
    def get_info(self, url):
        """Fetch video metadata and available streams"""
        try:
            print(f"\n[INFO] Fetching: {url}")
            yt = YouTube(str(url))

            # ── Metadata ──
            def safe(fn):
                try: return fn()
                except Exception: return None

            title    = safe(lambda: str(yt.title))    or 'Unknown'
            author   = safe(lambda: str(yt.author))   or 'Unknown'
            thumb    = safe(lambda: str(yt.thumbnail_url)) or ''
            views    = safe(lambda: f"{int(yt.views):,}") or 'N/A'
            length   = safe(lambda: int(yt.length))   or 0
            duration = f"{length // 60}:{length % 60:02d}"

            # ── Progressive (video+audio) ──
            progressive = []
            try:
                for s in yt.streams.filter(
                    progressive=True,
                    file_extension='mp4'
                ).order_by('resolution'):
                    try:
                        sz = round(s.filesize / (1024*1024), 1) \
                             if s.filesize else 0
                        progressive.append({
                            'itag':       int(s.itag),
                            'resolution': str(s.resolution or 'N/A'),
                            'fps':        int(s.fps or 30),
                            'size':       str(sz),
                            'audio':      True
                        })
                    except Exception as e:
                        print(f"[INFO] Prog skip: {e}")
            except Exception as e:
                print(f"[INFO] Prog error: {e}")

            # ── HD (video only) ──
            hd = []
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
                            sz = round(s.filesize / (1024*1024), 1) \
                                 if s.filesize else 0
                            hd.append({
                                'itag':       int(s.itag),
                                'resolution': res,
                                'fps':        int(s.fps or 30),
                                'size':       str(sz),
                                'audio':      False
                            })
                    except Exception as e:
                        print(f"[INFO] HD skip: {e}")
            except Exception as e:
                print(f"[INFO] HD error: {e}")

            # ── Audio only ──
            audio = []
            try:
                for s in yt.streams.filter(only_audio=True):
                    try:
                        sz = round(s.filesize / (1024*1024), 1) \
                             if s.filesize else 0
                        audio.append({
                            'itag': int(s.itag),
                            'abr':  str(s.abr or 'N/A'),
                            'size': str(sz)
                        })
                    except Exception as e:
                        print(f"[INFO] Audio skip: {e}")
            except Exception as e:
                print(f"[INFO] Audio error: {e}")

            print(f"[INFO] ✓ Title: {title}")
            print(f"[INFO]   Progressive: {len(progressive)}")
            print(f"[INFO]   HD: {len(hd)}")
            print(f"[INFO]   Audio: {len(audio)}")

            return self.ok({
                'title':       title,
                'author':      author,
                'duration':    duration,
                'views':       views,
                'thumbnail':   thumb,
                'progressive': progressive,
                'hd':          hd,
                'audio':       audio
            })

        except Exception as e:
            traceback.print_exc()
            return self.fail(f"get_info failed: {str(e)}")

    # ════════════════════════════════════════
    # Download HD (FFmpeg merge)
    # ════════════════════════════════════════
    def download_hd(self, url, quality='1080p'):
        """Download HD video + audio and merge with FFmpeg"""
        v_tmp = None
        a_tmp = None

        try:
            print(f"\n[HD] quality={quality}")
            yt   = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_name(yt.title)

            # ── Find video stream ──
            order = ['2160p','1440p','1080p','720p','480p','360p','240p','144p']
            if quality in order:
                order = order[order.index(quality):]

            v_stream = None
            v_res    = None

            for res in order:
                try:
                    s = yt.streams.filter(
                        only_video=True,
                        res=res,
                        file_extension='mp4'
                    ).first()
                    if s:
                        v_stream = s
                        v_res    = res
                        print(f"[HD] ✓ Video stream: {res}")
                        break
                except Exception as e:
                    print(f"[HD] {res} error: {e}")

            if not v_stream:
                try:
                    v_stream = yt.streams.filter(
                        only_video=True,
                        file_extension='mp4'
                    ).order_by('resolution').last()
                    v_res = str(v_stream.resolution) if v_stream else 'unknown'
                    print(f"[HD] Fallback video: {v_res}")
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

            # ── Paths ──
            v_tmp  = os.path.join(self.save_path, f"{name}_v.mp4")
            a_tmp  = os.path.join(self.save_path, f"{name}_a.mp4")
            output = os.path.join(self.save_path, f"{name}_{v_res}.mp4")

            print(f"[HD] Output: {output}")

            # ── Download video ──
            print(f"[HD] Downloading video ({v_res})...")
            try:
                v_stream.download(
                    output_path=self.save_path,
                    filename=f"{name}_v.mp4"
                )
            except Exception as e:
                return self.fail(f"Video download error: {e}")

            if not os.path.exists(v_tmp):
                return self.fail("Video file not created")

            print(f"[HD] ✓ Video: {self.size_mb(v_tmp)} MB")

            # ── Download audio ──
            print("[HD] Downloading audio...")
            try:
                a_stream.download(
                    output_path=self.save_path,
                    filename=f"{name}_a.mp4"
                )
            except Exception as e:
                self.remove(v_tmp)
                return self.fail(f"Audio download error: {e}")

            if not os.path.exists(a_tmp):
                self.remove(v_tmp)
                return self.fail("Audio file not created")

            print(f"[HD] ✓ Audio: {self.size_mb(a_tmp)} MB")

            # ── Merge ──
            print("[HD] Merging...")
            ok = self.ffmpeg_merge(v_tmp, a_tmp, output)
            self.remove(v_tmp, a_tmp)

            if not ok:
                return self.fail("FFmpeg merge failed")

            if not os.path.exists(output):
                return self.fail("Output file not found after merge")

            size  = self.size_mb(output)
            fname = os.path.basename(output)
            print(f"[HD] ✓ Complete: {fname} ({size} MB)")

            return self.ok({
                'filename':   fname,
                'resolution': str(v_res),
                'size':       f"{size} MB"
            })

        except Exception as e:
            traceback.print_exc()
            self.remove(v_tmp, a_tmp)
            return self.fail(str(e))

    # ════════════════════════════════════════
    # Download Progressive
    # ════════════════════════════════════════
    def download_progressive(self, url, itag):
        """Download combined video+audio stream directly"""
        try:
            print(f"\n[PROG] itag={itag}")
            yt   = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_name(yt.title)

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
                return self.fail("Progressive file not created")

            size = self.size_mb(output)
            print(f"[PROG] ✓ {fname} ({size} MB)")

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
        """Download best audio stream"""
        try:
            print(f"\n[AUDIO] Starting...")
            yt   = YouTube(str(url), on_progress_callback=on_progress)
            name = self.clean_name(yt.title)

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

            size = self.size_mb(output)
            print(f"[AUDIO] ✓ {fname} ({size} MB)")

            return self.ok({
                'filename': fname,
                'bitrate':  str(stream.abr or 'N/A'),
                'size':     f"{size} MB"
            })

        except Exception as e:
            traceback.print_exc()
            return self.fail(str(e))
