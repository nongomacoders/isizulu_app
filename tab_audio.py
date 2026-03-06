import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pygame
import subprocess
import tempfile

class AudioTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Initialize pygame mixer
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"Failed to initialize pygame mixer: {e}")
        
        self.current_folder = ""
        self.audio_files = []
        self.is_paused = False
        self.poll_id = None
        self.stop_time_ms = None
        
        # Loop functionality states
        self.loop_poll_id = None
        self.is_looping = False
        self.current_speed = 1.0
        self.temp_audio_file = os.path.join(tempfile.gettempdir(), "isizulu_temp_loop.wav")
        
        self._build_ui()
        
    def _build_ui(self):
        # Top Frame for controls
        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", pady=5)
        
        btn_folder = ttk.Button(top_frame, text="Select Folder", command=self._select_folder)
        btn_folder.pack(side="left", padx=5)
        
        self.lbl_folder = ttk.Label(top_frame, text="No folder selected", foreground="gray")
        self.lbl_folder.pack(side="left", padx=5, fill="x", expand=True)
        
        # Middle Frame for Listbox
        mid_frame = ttk.Frame(self)
        mid_frame.pack(fill="both", expand=True, pady=5)
        
        scrollbar = ttk.Scrollbar(mid_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.listbox = tk.Listbox(mid_frame, yscrollcommand=scrollbar.set, font=("Segoe UI", 12))
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        
        # Time Frame for Start/Stop controls
        time_frame = ttk.Frame(self)
        time_frame.pack(fill="x", pady=5)
        
        ttk.Label(time_frame, text="Start (s):").pack(side="left")
        self.entry_start = ttk.Entry(time_frame, width=8)
        self.entry_start.pack(side="left", padx=5)
        self.entry_start.insert(0, "0")
        
        ttk.Label(time_frame, text="Stop (s):").pack(side="left", padx=(10, 0))
        self.entry_stop = ttk.Entry(time_frame, width=8)
        self.entry_stop.pack(side="left", padx=5)
        ttk.Label(time_frame, text="(Leave empty to play to end)").pack(side="left", padx=5)
        
        # Bottom Frame for Playback controls
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", pady=5)
        
        self.btn_play = ttk.Button(bottom_frame, text="Play", command=self._play_audio)
        self.btn_play.pack(side="left", padx=5)
        
        self.btn_pause = ttk.Button(bottom_frame, text="Pause/Resume", command=self._pause_resume_audio)
        self.btn_pause.pack(side="left", padx=5)
        
        self.btn_stop = ttk.Button(bottom_frame, text="Stop", command=self._stop_audio)
        self.btn_stop.pack(side="left", padx=5)
        
        self.btn_loop = ttk.Button(bottom_frame, text="Loop", command=self._start_loop)
        self.btn_loop.pack(side="left", padx=5)
        
        ttk.Label(bottom_frame, text="Volume:").pack(side="left", padx=(20, 5))
        self.volume_scale = ttk.Scale(bottom_frame, from_=0.0, to=1.0, orient="horizontal", command=self._set_volume)
        self.volume_scale.set(1.0)
        self.volume_scale.pack(side="left", padx=5)
        
        self.lbl_status = ttk.Label(bottom_frame, text="Stopped")
        self.lbl_status.pack(side="left", padx=20)
        
    def _set_volume(self, val):
        try:
            pygame.mixer.music.set_volume(float(val))
        except Exception:
            pass

    def _select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder with Audio Files")
        if folder:
            self.current_folder = folder
            self.lbl_folder.config(text=folder)
            self._load_files()
            
    def _load_files(self):
        self.listbox.delete(0, tk.END)
        self.audio_files = []
        if not self.current_folder:
            return
            
        supported_exts = {".mp3", ".wav", ".ogg"}
        try:
            for f in os.listdir(self.current_folder):
                ext = os.path.splitext(f)[1].lower()
                if ext in supported_exts:
                    self.audio_files.append(f)
            self.audio_files.sort()
            for f in self.audio_files:
                self.listbox.insert(tk.END, f)
        except Exception as e:
            messagebox.showerror("Error", f"Could not read folder:\n{e}")

    def _on_select(self, event):
        pass

    def _play_audio(self):
        self._stop_audio()

        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an audio file to play.")
            return
            
        index = selection[0]
        filename = self.audio_files[index]
        filepath = os.path.join(self.current_folder, filename)
        
        try:
            start_time = float(self.entry_start.get() or 0)
        except ValueError:
            start_time = 0.0

        try:
            stop_time_str = self.entry_stop.get().strip()
            stop_time = float(stop_time_str) if stop_time_str else None
        except ValueError:
            stop_time = None

        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play(start=start_time)
            self.lbl_status.config(text=f"Playing: {filename}")
            self.is_paused = False
            
            if stop_time is not None and stop_time > start_time:
                self.stop_time_ms = (stop_time - start_time) * 1000
                self._poll_playback()
            else:
                self.stop_time_ms = None
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to play {filename}:\n{e}")

    def _poll_playback(self):
        if self.stop_time_ms is not None:
            if pygame.mixer.music.get_busy() and not self.is_paused:
                if pygame.mixer.music.get_pos() >= self.stop_time_ms:
                    self._stop_audio()
                    return
            self.poll_id = self.after(100, self._poll_playback)

    def _start_loop(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an audio file to loop.")
            return
            
        self._stop_audio()
        self.is_looping = True
        self.current_speed = 0.65
        self._play_loop_step()

    def _play_loop_step(self):
        if not self.is_looping:
            return
            
        selection = self.listbox.curselection()
        if not selection:
            self.is_looping = False
            return
            
        index = selection[0]
        filename = self.audio_files[index]
        filepath = os.path.join(self.current_folder, filename)
        
        try:
            start_time = float(self.entry_start.get() or 0)
        except ValueError:
            start_time = 0.0

        try:
            stop_time_str = self.entry_stop.get().strip()
            stop_time = float(stop_time_str) if stop_time_str else None
        except ValueError:
            stop_time = None

        # Stop and unload to ensure the temp file is not locked
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass

        # We extract the segment at normal speed first, then slow it down.
        # This keeps the Start/Stop times relative to the original audio.
        cmd = ["ffmpeg", "-y"]
        if start_time > 0:
            cmd.extend(["-ss", f"{start_time:.3f}"])
        cmd.extend(["-i", filepath])
        
        if stop_time is not None and stop_time > start_time:
            duration = stop_time - start_time
            cmd.extend(["-t", f"{duration:.3f}"])
            
        cmd.extend(["-filter:a", f"atempo={self.current_speed:.2f}", self.temp_audio_file])
        
        try:
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, **kwargs)
            
            pygame.mixer.music.load(self.temp_audio_file)
            pygame.mixer.music.play() # Plays the extracted segment from the beginning
            self.lbl_status.config(text=f"Looping {filename} at {self.current_speed:.2f}x")
            self.is_paused = False
            
            self._poll_loop()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to loop {filename}:\n{e}")
            self.is_looping = False

    def _poll_loop(self):
        if not self.is_looping:
            return
            
        if not pygame.mixer.music.get_busy() and not self.is_paused:
            # Increment speed by 0.05 for a smooth transition to normal speed
            self.current_speed += 0.05
            if self.current_speed > 1.01:
                self.is_looping = False
                self.lbl_status.config(text="Loop finished")
            else:
                self._play_loop_step()
        else:
            self.loop_poll_id = self.after(100, self._poll_loop)

    def _pause_resume_audio(self):
        if not pygame.mixer.music.get_busy() and not self.is_paused:
            return
            
        if self.is_paused:
            pygame.mixer.music.unpause()
            if self.is_looping:
                self.lbl_status.config(text=f"Looping at {self.current_speed:.2f}x")
            else:
                self.lbl_status.config(text="Playing")
            self.is_paused = False
        else:
            pygame.mixer.music.pause()
            self.lbl_status.config(text="Paused")
            self.is_paused = True

    def _stop_audio(self):
        self.is_looping = False
        if self.loop_poll_id:
            self.after_cancel(self.loop_poll_id)
            self.loop_poll_id = None
        if self.poll_id:
            self.after_cancel(self.poll_id)
            self.poll_id = None
            
        try:
            pygame.mixer.music.stop()
            self.lbl_status.config(text="Stopped")
            self.is_paused = False
        except Exception:
            pass