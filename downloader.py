from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import subprocess
import re
import traceback

class YouTubeDownloader:
    def __init__(self, download_path):
        self.download_path = os.path.abspath(download_path)
        os.makedirs(self.download_path, exist_ok=True)
        print(f"[INFO] Download folder: {self.download_path}")

    def check_ffmpeg(self):
        """Check if FFmpeg is installed"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True
            )
            return True
        except FileNotFoundError:
            print("[ERROR] FFmpeg not found!")
            return False
        except Exception as e:
            print(f"[ERROR] FFmpeg check failed: {e}")
            return False

    def get_safe_filename(self, title):
        """Create safe filename - remove ALL special characters"""
        try:
            # Remove special characters
            safe = re.sub(r'[^\w\s\-]', '', title)
            # Replace multiple spaces/underscores
            safe = re.sub(r'[\s_]+', '_', safe)
            # Strip leading/trailing
            safe = safe.strip('_').strip()
            # Limit length
            safe = safe[:60]
            # Final cleanup
            safe = re.sub(r'[^\w\-]', '_', safe)
            safe = re.sub(r'_+', '_', safe)
            safe = safe.strip('_')

            if not safe:
                safe = "youtube_video"

            print(f"[INFO] Safe filename: {safe}")
            return safe

        except Exception as e:
            print(f"[ERROR] Filename error: {e}")
            return "youtube_video"

    def get_video_info(self, url):
        """Get video information - returns dict always"""
        try:
            print(f"\n[INFO] Getting video info: {url}")
            yt = YouTube(url)
            print(f"[INFO] Title: {yt.title}")

            # Progressive streams
            progressive_streams = []
            try:
                for s in yt.streams.filter(
                    progressive=True,
                    file_extension='mp4'
                ).order_by('resolution'):
                    try:
                        size = s.filesize / (1024*1024) if s.filesize else 0
                        progressive_streams.append({
                            'itag': s.itag,
                            'resolution': s.resolution or 'Unknown',
                            'fps': s.fps or 30,
                            'size': f"{size:.1f}",
                            'type': 'progressive',
                            'audio': True
                        })
                    except Exception as e:
                        print(f"[WARN] Stream error: {e}")
                        continue
            except Exception as e:
                print(f"[WARN] Progressive streams error: {e}")

            # Video only streams
            video_only_streams = []
            try:
                seen_res = set()
                for s in yt.streams.filter(
                    only_video=True,
                    file_extension='mp4'
                ).order_by('resolution'):
                    try:
                        if s.resolution and s.resolution not in seen_res:
                            seen_res.add(s.resolution)
                            size = s.filesize / (1024*1024) if s.filesize else 0
                            video_only_streams.append({
                                'itag': s.itag,
                                'resolution': s.resolution,
                                'fps': s.fps or 30,
                                'size': f"{size:.1f}",
                                'type': 'video_only',
                                'audio': False
                            })
                    except Exception as e:
                        print(f"[WARN] HD stream error: {e}")
                        continue
            except Exception as e:
                print(f"[WARN] Video only streams error: {e}")

            # Audio streams
            audio_streams = []
            try:
                for s in yt.streams.filter(only_audio=True):
                    try:
                        size = s.filesize / (1024*1024) if s.filesize else 0
                        audio_streams.append({
                            'itag': s.itag,
                            'abr': s.abr or 'Unknown',
                            'size': f"{size:.1f}",
                            'type': 'audio_only'
                        })
                    except Exception as e:
                        print(f"[WARN] Audio stream error: {e}")
                        continue
            except Exception as e:
                print(f"[WARN] Audio streams error: {e}")

            # Safe values
            try:
                views = f"{yt.views:,}" if yt.views else "N/A"
            except:
                views = "N/A"

            try:
                length = yt.length or 0
                duration = f"{length // 60}:{length % 60:02d}"
            except:
                duration = "0:00"

            result = {
                'success': True,
                'title': str(yt.title or 'Unknown'),
                'author': str(yt.author or 'Unknown'),
                'duration': duration,
                'views': views,
                'thumbnail': str(yt.thumbnail_url or ''),
                'progressive_streams': progressive_streams,
                'video_only_streams': video_only_streams,
                'audio_streams': audio_streams
            }

            print(f"[INFO] Streams found:")
            print(f"  Progressive: {len(progressive_streams)}")
            print(f"  HD: {len(video_only_streams)}")
            print(f"  Audio: {len(audio_streams)}")

            return result

        except Exception as e:
            traceback.print_exc()
            return {
                'success': False,
                'error': f"Failed to get video info: {str(e)}"
            }

    def download_video_with_audio(self, url, quality='1080p'):
        """Download HD video with audio using FFmpeg merge"""
        video_temp = None
        audio_temp = None

        try:
            print(f"\n[INFO] HD Download started")
            print(f"[INFO] URL: {url}")
            print(f"[INFO] Quality: {quality}")

            yt = YouTube(url, on_progress_callback=on_progress)
            safe_title = self.get_safe_filename(yt.title)

            # ── Find video stream ──
            resolutions = ['2160p', '1440p', '1080p', '720p', '480p', '360p']
            if quality in resolutions:
                idx = resolutions.index(quality)
                search_order = resolutions[idx:]
            else:
                search_order = resolutions

            video_stream = None
            selected_res = None

            for res in search_order:
                try:
                    video_stream = yt.streams.filter(
                        only_video=True,
                        res=res,
                        file_extension='mp4'
                    ).first()
                    if video_stream:
                        selected_res = res
                        print(f"[INFO] Found video: {res}")
                        break
                except Exception as e:
                    print(f"[WARN] Error checking {res}: {e}")
                    continue

            if not video_stream:
                try:
                    video_stream = yt.streams.filter(
                        only_video=True,
                        file_extension='mp4'
                    ).order_by('resolution').last()
                    selected_res = video_stream.resolution if video_stream else '720p'
                    print(f"[INFO] Fallback video: {selected_res}")
                except Exception as e:
                    return {'success': False, 'error': f'No video stream found: {str(e)}'}

            if not video_stream:
                return {'success': False, 'error': 'No video stream available'}

            # ── Find audio stream ──
            try:
                audio_stream = yt.streams.filter(
                    only_audio=True
                ).order_by('abr').last()
            except Exception as e:
                return {'success': False, 'error': f'No audio stream found: {str(e)}'}

            if not audio_stream:
                return {'success': False, 'error': 'No audio stream available'}

            # ── Define file paths ──
            video_temp = os.path.join(self.download_path, f"{safe_title}_v_temp.mp4")
            audio_temp = os.path.join(self.download_path, f"{safe_title}_a_temp.mp4")
            output_file = os.path.join(self.download_path, f"{safe_title}_{selected_res}.mp4")

            print(f"[INFO] Video temp: {video_temp}")
            print(f"[INFO] Audio temp: {audio_temp}")
            print(f"[INFO] Output: {output_file}")

            # ── Download video ──
            print(f"[INFO] Downloading video ({selected_res})...")
            try:
                video_stream.download(
                    output_path=self.download_path,
                    filename=f"{safe_title}_v_temp.mp4"
                )
            except Exception as e:
                return {'success': False, 'error': f'Video download failed: {str(e)}'}

            if not os.path.exists(video_temp):
                return {'success': False, 'error': f'Video temp file not created: {video_temp}'}

            print(f"[INFO] ✓ Video downloaded: {os.path.getsize(video_temp) / (1024*1024):.1f} MB")

            # ── Download audio ──
            print(f"[INFO] Downloading audio...")
            try:
                audio_stream.download(
                    output_path=self.download_path,
                    filename=f"{safe_title}_a_temp.mp4"
                )
            except Exception as e:
                return {'success': False, 'error': f'Audio download failed: {str(e)}'}

            if not os.path.exists(audio_temp):
                return {'success': False, 'error': f'Audio temp file not created: {audio_temp}'}

            print(f"[INFO] ✓ Audio downloaded: {os.path.getsize(audio_temp) / (1024*1024):.1f} MB")

            # ── Merge ──
            print(f"[INFO] Merging with FFmpeg...")
            merge_ok = self.merge_video_audio(video_temp, audio_temp, output_file)

            # ── Cleanup ──
            for tmp in [video_temp, audio_temp]:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                        print(f"[INFO] Removed temp: {tmp}")
                    except Exception as e:
                        print(f"[WARN] Could not remove temp: {e}")

            if merge_ok and os.path.exists(output_file):
                final_size = os.path.getsize(output_file) / (1024*1024)
                filename = os.path.basename(output_file)
                print(f"[INFO] ✓ Done! {filename} ({final_size:.1f} MB)")

                return {
                    'success': True,
                    'filename': filename,
                    'resolution': selected_res,
                    'size': f"{final_size:.1f} MB",
                    'path': output_file
                }
            else:
                return {'success': False, 'error': 'FFmpeg merge failed or output not created'}

        except Exception as e:
            traceback.print_exc()
            # Cleanup on error
            for tmp in [video_temp, audio_temp]:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except:
                        pass
            return {'success': False, 'error': str(e)}

    def download_progressive(self, url, itag):
        """Download progressive stream (video+audio combined)"""
        try:
            print(f"\n[INFO] Progressive download: itag={itag}")
            yt = YouTube(url, on_progress_callback=on_progress)
            safe_title = self.get_safe_filename(yt.title)

            stream = yt.streams.get_by_itag(int(itag))
            if not stream:
                return {'success': False, 'error': f'Stream not found: itag={itag}'}

            filename = f"{safe_title}_{stream.resolution}.mp4"
            output_path = os.path.join(self.download_path, filename)

            print(f"[INFO] Downloading: {filename}")
            stream.download(
                output_path=self.download_path,
                filename=filename
            )

            if not os.path.exists(output_path):
                return {'success': False, 'error': 'File not created after download'}

            final_size = os.path.getsize(output_path) / (1024*1024)
            print(f"[INFO] ✓ Done! {filename} ({final_size:.1f} MB)")

            return {
                'success': True,
                'filename': filename,
                'resolution': stream.resolution or 'Unknown',
                'size': f"{final_size:.1f} MB",
                'path': output_path
            }

        except Exception as e:
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def download_audio_only(self, url):
        """Download audio only"""
        try:
            print(f"\n[INFO] Audio download started")
            yt = YouTube(url, on_progress_callback=on_progress)
            safe_title = self.get_safe_filename(yt.title)

            audio_stream = yt.streams.filter(
                only_audio=True
            ).order_by('abr').last()

            if not audio_stream:
                return {'success': False, 'error': 'No audio stream found'}

            filename = f"{safe_title}_audio.mp4"
            output_path = os.path.join(self.download_path, filename)

            print(f"[INFO] Downloading audio: {filename}")
            audio_stream.download(
                output_path=self.download_path,
                filename=filename
            )

            if not os.path.exists(output_path):
                return {'success': False, 'error': 'Audio file not created'}

            final_size = os.path.getsize(output_path) / (1024*1024)
            print(f"[INFO] ✓ Done! {filename} ({final_size:.1f} MB)")

            return {
                'success': True,
                'filename': filename,
                'bitrate': audio_stream.abr or 'Unknown',
                'size': f"{final_size:.1f} MB",
                'path': output_path
            }

        except Exception as e:
            traceback.print_exc()
            return {'success': False, 'error': str(e)}

    def merge_video_audio(self, video_path, audio_path, output_path):
        """Merge video and audio using FFmpeg"""
        try:
            if not os.path.exists(video_path):
                print(f"[ERROR] Video not found: {video_path}")
                return False
            if not os.path.exists(audio_path):
                print(f"[ERROR] Audio not found: {audio_path}")
                return False

            command = [
                'ffmpeg',
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
                output_path,
                '-y',
                '-loglevel', 'error'
            ]

            print(f"[INFO] Running FFmpeg...")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300  # 5 min timeout
            )

            if result.returncode == 0:
                print(f"[INFO] ✓ FFmpeg merge successful")
                return True
            else:
                print(f"[ERROR] FFmpeg failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("[ERROR] FFmpeg timeout!")
            return False
        except FileNotFoundError:
            print("[ERROR] FFmpeg not found!")
            return False
        except Exception as e:
            print(f"[ERROR] Merge error: {e}")
            return False
     
