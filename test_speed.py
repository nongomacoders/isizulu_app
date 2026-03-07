import pygame
import time
import os
import subprocess
import tempfile

speed = 0.5
start_time_original = 2.0  # seconds in the original file
stop_time_original = 4.0   # seconds in the original file

print(f"--- Configuration ---")
print(f"Speed: {speed}x")
print(f"Original Start Time: {start_time_original}s")
print(f"Original Stop Time: {stop_time_original}s")

# Ensure the mixer is at standard frequency
pygame.mixer.init(frequency=44100)
print(f"Mixer Initialized: {pygame.mixer.get_init()}")

# Generate test file if needed
if not os.path.exists('tone5s.wav'):
    print("Generating 5s test file...")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=5", "tone5s.wav"], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Process the audio segment with ffmpeg (crop and change speed)
print("Processing audio with ffmpeg...")
temp_audio = os.path.join(tempfile.gettempdir(), "test_speed_temp.wav")
cmd = [
    "ffmpeg", "-y",
    "-ss", str(start_time_original),
    "-t", str(stop_time_original - start_time_original),
    "-i", "tone5s.wav",
    "-filter:a", f"atempo={speed}",
    temp_audio
]

subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
print(f"Audio processed and saved to {temp_audio}")

# Timing expectations
expected_real_duration = (stop_time_original - start_time_original) / speed
print(f"Expected Real Playback Time: {expected_real_duration}s")

# Load and play the processed file (from the beginning, as it's already cropped)
pygame.mixer.music.load(temp_audio)
pygame.mixer.music.play()

# Calculate target stop position
# Since the file is already processed, get_pos() will naturally reach expected_real_duration * 1000
target_stop_ms = expected_real_duration * 1000
print(f"Target Stop Position (get_pos() ms): {target_stop_ms}")

print("--- Starting Playback Loop ---")
t0 = time.time()
stopped_by_us = False

while True:
    real_time_passed = time.time() - t0
    pos_ms = pygame.mixer.music.get_pos()
    
    print(f"[Log] Real time passed: {real_time_passed:.3f}s | pygame get_pos(): {pos_ms}ms")
    
    if pos_ms >= target_stop_ms:
        print(f"*** Reached target stop position: {pos_ms} >= {target_stop_ms} ***")
        pygame.mixer.music.stop()
        stopped_by_us = True
        break
        
    if not pygame.mixer.music.get_busy():
        print("!!! Pygame stopped playing prematurely !!!")
        break
        
    if real_time_passed > expected_real_duration + 2.0:
        print("!!! Timeout reached !!!")
        break
        
    time.sleep(0.5)

print(f"--- Results ---")
print(f"Total Real Time Elapsed: {time.time() - t0:.3f}s")
print(f"Did we successfully reach the expected stop time?: {stopped_by_us}")
