from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import subprocess
import re

class YouTubeDownloader:
    def __init__(self, download_path):
        # ── Use absolute path always ──
        self.download_path = os.path.abspath(download_path)
        os.makedirs(self.download_path, exist_ok=True)
        print(f"✓ Download folder: {self.download_path}")

    def check_ffmpeg(self):
        """Check if FFmpeg is installed"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True
            )
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def get_safe_filename(self, title):
        """
        Create safe filename from title
        Remove all special characters
        """
        # Remove special characters
        safe = re.sub(r'[^\w\s\-]', '', title)
        # Replace multiple spaces with single space
        safe = re.sub(r'\s+', ' ', safe)
        # Strip leading/trailing spaces
        safe = safe.strip()
        # Limit length
        safe = safe[:80]
        # Replace spaces with underscores
        safe = safe.replace(' ', '_')
        return safe

    def get_video_info(self, url):
        """Get video information"""
        try:
            yt = YouTube(url)

            # Get progressive streams
            progressive_streams = []
            for s in yt.streams.filter(
                progressive=True,
                file_extension='mp4'
            ).order_by('resolution'):
                size = s.filesize / (1024*1024) if s.filesize else 0
                progressive_streams.append({
                    'itag': s.itag,
                    'resolution': s.resolution,
                    'fps': s.fps,
                    'size': f"{size:.1f}",
                    'type': 'progressive',
                    'audio': True
                })

            # Get video only streams
            video_only_streams = []
            seen_res = set()
            for s in yt.streams.filter(
                only_video=True,
                file_extension='mp4'
            ).order_by('resolution'):
                if s.resolution not in seen_res:
                    seen_res.add(s.resolution)
                    size = s.filesize / (1024*1024) if s.filesize else 0
                    video_only_streams.append({
                        'itag': s.itag,
                        'resolution': s.resolution,
                        'fps': s.fps,
                        'size': f"{size:.1f}",
                        'type': 'video_only',
                        'audio': False
                    })

            # Get audio streams
            audio_streams = []
            for s in yt.streams.filter(only_audio=True):
                size = s.filesize / (1024*1024) if s.filesize else 0
                audio_streams.append({
                    'itag': s.itag,
                    'abr': s.abr,
                    'size': f"{size:.1f}",
                    'type': 'audio_only'
                })

            return {
                'success': True,
                'title': yt.title,
                'author': yt.author,
                'duration': f"{yt.length // 60}:{yt.length % 60:02d}",
                'views': f"{yt.views:,}",
                'thumbnail': yt.thumbnail_url,
                'progressive_streams': progressive_streams,
                'video_only_streams': video_only_streams,
                'audio_streams': audio_streams
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def download_video_with_audio(self, url, quality='1080p'):
        """
        Download Video WITH Audio
        Downloads video + audio separately then merges
        """
        video_temp = None
        audio_temp = None

        try:
            print(f"\n Starting download: {url}")
            print(f" Quality: {quality}")
            print(f" Download path: {self.download_path}")

            yt = YouTube(url, on_progress_callback=on_progress)
            safe_title = self.get_safe_filename(yt.title)

            print(f" Safe title: {safe_title}")

            # ── Find best video stream ──
            resolutions = ['2160p', '1440p', '1080p', '720p', '480p', '360p']

            # Start from requested quality
            if quality in resolutions:
                start_idx = resolutions.index(quality)
                search_order = resolutions[start_idx:]
            else:
                search_order = resolutions

            video_stream = None
            selected_res = None

            for res in search_order:
                video_stream = yt.streams.filter(
                    only_video=True,
                    res=res,
                    file_extension='mp4'
                ).first()
                if video_stream:
                    selected_res = res
                    print(f" Found video stream: {res}")
                    break

            if not video_stream:
                video_stream = yt.streams.filter(
                    only_video=True,
                    file_extension='mp4'
                ).order_by('resolution').last()
                selected_res = video_stream.resolution
                print(f" Using best available: {selected_res}")

            # ── Find best audio stream ──
            audio_stream = yt.streams.filter(
                only_audio=True
            ).order_by('abr').last()

            print(f" Audio stream: {audio_stream.abr}")

            # ── Define ABSOLUTE file paths ──
            video_temp = os.path.join(
                self.download_path,
                f"{safe_title}_video_temp.mp4"
            )
            audio_temp = os.path.join(
                self.download_path,
                f"{safe_title}_audio_temp.mp4"
            )
            output_file = os.path.join(
                self.download_path,
                f"{safe_title}_{selected_res}.mp4"
            )

            print(f"\n Video temp: {video_temp}")
            print(f" Audio temp: {audio_temp}")
            print(f" Output: {output_file}")

            # ── Download Video ──
            print(f"\n[1/3] Downloading video ({selected_res})...")
            video_stream.download(
                output_path=self.download_path,
                filename=f"{safe_title}_video_temp.mp4"
            )
            print(f" ✓ Video saved: {video_temp}")
            print(f" ✓ File exists: {os.path.exists(video_temp)}")

            # ── Download Audio ──
            print(f"\n[2/3] Downloading audio...")
            audio_stream.download(
                output_path=self.download_path,
                filename=f"{safe_title}_audio_temp.mp4"
            )
            print(f" ✓ Audio saved: {audio_temp}")
            print(f" ✓ File exists: {os.path.exists(audio_temp)}")

            # ── Merge ──
            print(f"\n[3/3] Merging video + audio...")
            success = self.merge_video_audio(
                video_temp,
                audio_temp,
                output_file
            )

            # ── Cleanup temp files ──
            for temp_file in [video_temp, audio_temp]:
                if temp_file and os.path.exists(temp_file):
                    os.remove(temp_file)
                    print(f" ✓ Removed: {temp_file}")

            if success and os.path.exists(output_file):
                final_size = os.path.getsize(output_file) / (1024*1024)
                filename = os.path.basename(output_file)

                print(f"\n✓ Download complete!")
                print(f"  File: {filename}")
                print(f"  Size: {final_size:.1f} MB")
                print(f"  Path: {output_file}")

                return {
                    'success': True,
                    'filename': filename,
                    'resolution': selected_res,
                    'size': f"{final_size:.1f} MB",
                    'path': output_file
                }
            else:
                return {
                    'success': False,
                    'error': 'Merge failed or output file not created'
                }

        except Exception as e:
            print(f"\n✗ Error: {e}")
            # Cleanup on error
            for temp_file in [video_temp, audio_temp]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            return {'success': False, 'error': str(e)}

    def download_progressive(self, url, itag):
        """Download progressive stream (video+audio combined)"""
        try:
            yt = YouTube(url, on_progress_callback=on_progress)
            safe_title = self.get_safe_filename(yt.title)

            stream = yt.streams.get_by_itag(itag)
            if not stream:
                return {'success': False, 'error': 'Stream not found'}

            filename = f"{safe_title}_{stream.resolution}.mp4"
            output_path = os.path.join(self.download_path, filename)

            print(f"\n Downloading: {filename}")
            print(f" Path: {output_path}")

            stream.download(
                output_path=self.download_path,
                filename=filename
            )

            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path) / (1024*1024)
                print(f"✓ Downloaded: {filename} ({final_size:.1f} MB)")

                return {
                    'success': True,
                    'filename': filename,
                    'resolution': stream.resolution,
                    'size': f"{final_size:.1f} MB",
                    'path': output_path
                }
            else:
                return {'success': False, 'error': 'File not created'}

        except Exception as e:
            print(f"✗ Error: {e}")
            return {'success': False, 'error': str(e)}

    def download_audio_only(self, url):
        """Download Audio Only"""
        try:
            yt = YouTube(url, on_progress_callback=on_progress)
            safe_title = self.get_safe_filename(yt.title)

            audio_stream = yt.streams.filter(
                only_audio=True
            ).order_by('abr').last()

            filename = f"{safe_title}_audio.mp4"
            output_path = os.path.join(self.download_path, filename)

            print(f"\n Downloading audio: {filename}")
            print(f" Path: {output_path}")

            audio_stream.download(
                output_path=self.download_path,
                filename=filename
            )

            if os.path.exists(output_path):
                final_size = os.path.getsize(output_path) / (1024*1024)
                print(f"✓ Audio downloaded: {filename} ({final_size:.1f} MB)")

                return {
                    'success': True,
                    'filename': filename,
                    'bitrate': audio_stream.abr,
                    'size': f"{final_size:.1f} MB",
                    'path': output_path
                }
            else:
                return {'success': False, 'error': 'Audio file not created'}

        except Exception as e:
            print(f"✗ Error: {e}")
            return {'success': False, 'error': str(e)}

    def merge_video_audio(self, video_path, audio_path, output_path):
        """Merge video and audio using FFmpeg"""
        try:
            print(f"\n FFmpeg merge:")
            print(f"   Video: {video_path}")
            print(f"   Audio: {audio_path}")
            print(f"   Output: {output_path}")

            if not os.path.exists(video_path):
                print(f" ✗ Video not found: {video_path}")
                return False

            if not os.path.exists(audio_path):
                print(f" ✗ Audio not found: {audio_path}")
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

            print(f" Running FFmpeg...")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                print(f" ✓ FFmpeg merge successful!")
                print(f" ✓ Output exists: {os.path.exists(output_path)}")
                return True
            else:
                print(f" ✗ FFmpeg failed: {result.stderr}")
                return False

        except FileNotFoundError:
            print(" ✗ FFmpeg not found! Install: conda install -c conda-forge ffmpeg")
            return False
        except Exception as e:
            print(f" ✗ Merge error: {e}")
            return False