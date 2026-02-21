import threading
import time
import datetime
import os
import customtkinter as ctk
from plyer import notification
import speech_recognition as sr
import pyttsx3
import sys
import pythoncom
import subprocess
import webbrowser
import re
import queue
from tkinter import ttk, messagebox
from collections import defaultdict
import math
import json

# Try to import scheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.base import JobLookupError
    SCHEDULER_AVAILABLE = True
except:
    SCHEDULER_AVAILABLE = False
    print("⚠️ APScheduler not installed. Installing...")
    os.system(f"{sys.executable} -m pip install apscheduler")
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.base import JobLookupError
    SCHEDULER_AVAILABLE = True

# Try to import winsound
try:
    import winsound
    SOUND_AVAILABLE = True
except:
    SOUND_AVAILABLE = False

# For camera access
try:
    import cv2
    CAMERA_AVAILABLE = True
except:
    CAMERA_AVAILABLE = False
    print("⚠️ OpenCV not installed. Camera features disabled.")
    print("   Install with: pip install opencv-python")

# For volume control
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    VOLUME_AVAILABLE = True
except Exception as e:
    VOLUME_AVAILABLE = False
    print(f"⚠️ Pycaw not installed. Volume control disabled. Error: {e}")
    print("   Install with: pip install pycaw comtypes")

# ==========================================
# 1. CORE CONFIGURATION
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()
print("✅ Scheduler started")

# In-memory task storage
tasks_memory = []
tasks_counter = 0

# Command repetition tracking
command_history = []
COMMAND_THRESHOLD = 6  # 6 times repeat
last_command_time = {}

# Flag to ensure loading window shows only once
loading_shown = False

# ==========================================
# 2. LOADING WINDOW - FIXED (shows only once)
# ==========================================
class LoadingWindow(ctk.CTkToplevel):
    def __init__(self):
        super().__init__()
        self.title("")
        self.geometry("500x300")
        self.configure(fg_color="#1a1a2e")
        
        # Center the window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.winfo_screenheight() // 2) - (300 // 2)
        self.geometry(f'+{x}+{y}')
        
        # Remove window decorations
        self.overrideredirect(True)
        
        # Make sure it stays on top
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        
        # Main frame
        self.main_frame = ctk.CTkFrame(self, fg_color="#16213e", corner_radius=20)
        self.main_frame.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Logo/Title
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="NEXUS",
            font=("Orbitron", 48, "bold"),
            text_color="#22d3ee"
        )
        self.title_label.pack(pady=(30, 10))
        
        # Subtitle
        self.subtitle = ctk.CTkLabel(
            self.main_frame,
            text="Personal Assistant",
            font=("Arial", 16),
            text_color="#a5f3fc"
        )
        self.subtitle.pack(pady=(0, 20))
        
        # Loading bar
        self.progress = ctk.CTkProgressBar(self.main_frame, width=300, height=15, corner_radius=10)
        self.progress.pack(pady=20)
        self.progress.set(0)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self.main_frame,
            text="Initializing NEXUS...",
            font=("Arial", 12),
            text_color="#88aaee"
        )
        self.status_label.pack(pady=10)
        
        # Loading dots
        self.dots = ""
        self.running = True
        self.update_loading()
    
    def update_loading(self):
        """Animate loading"""
        if self.running and self.progress.get() < 1:
            # Update progress
            new_value = self.progress.get() + 0.05
            self.progress.set(new_value)
            
            # Update status text
            if new_value < 0.3:
                self.status_label.configure(text="Loading modules...")
            elif new_value < 0.5:
                self.status_label.configure(text="Initializing voice engine...")
            elif new_value < 0.7:
                self.status_label.configure(text="Setting up scheduler...")
            elif new_value < 0.9:
                self.status_label.configure(text="Preparing camera...")
            else:
                self.status_label.configure(text="Almost ready...")
            
            # Animate dots
            self.dots = self.dots + "." if len(self.dots) < 3 else ""
            self.title_label.configure(text=f"NEXUS{self.dots}")
            
            # Schedule next update
            self.after(100, self.update_loading)
        elif self.running:
            self.status_label.configure(text="Ready!")
            self.after(800, self.destroy_window)
    
    def destroy_window(self):
        """Destroy loading window"""
        self.running = False
        self.destroy()

# ==========================================
# 3. REPEAT COMMAND DETECTION
# ==========================================
def check_command_repetition(command):
    """Check if command is repeated too many times"""
    global command_history, last_command_time
    
    current_time = time.time()
    command_lower = command.lower()
    
    # Add to history
    command_history.append({
        'command': command_lower,
        'time': current_time
    })
    
    # Keep only last 20 commands
    if len(command_history) > 20:
        command_history.pop(0)
    
    # Count occurrences in last 2 minutes
    recent_commands = [c for c in command_history 
                      if c['command'] == command_lower 
                      and current_time - c['time'] < 120]  # Last 2 minutes
    
    count = len(recent_commands)
    
    # Check if this is a repeat command
    if command_lower in last_command_time:
        time_diff = current_time - last_command_time[command_lower]
        if time_diff < 10:  # Same command within 10 seconds
            count += 1
    
    last_command_time[command_lower] = current_time
    
    # If repeated more than threshold, ask user
    if count >= COMMAND_THRESHOLD:
        return True, count
    
    return False, count

def ask_for_task_schedule(command):
    """Ask user if they want to schedule the repeated command as a task"""
    response = messagebox.askyesno(
        "Repeat Command Detected",
        f"आपने यह कमांड {COMMAND_THRESHOLD} बार दोहराया है:\n\n'{command}'\n\n"
        "क्या आप इसे एक टास्क के रूप में शेड्यूल करना चाहते हैं?\n"
        "उदाहरण: 'remind me to " + command + " at 5pm'"
    )
    
    if response:
        # Open reminder suggestion
        speak("कृपया समय बताएं। उदाहरण: at 5pm या tomorrow morning")
        return True
    return False

# ==========================================
# 3b. COMMAND LOGGER
# ==========================================
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_command_logs.json")

class CommandLogger:
    """Persists every user command to a JSON log file with timestamp."""

    def __init__(self, log_path=LOG_FILE):
        self.log_path = log_path
        self._ensure_file()

    def _ensure_file(self):
        """Create log file if it doesn't exist."""
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def log(self, command: str, source: str = "text"):
        """Append one command entry with a full ISO-8601 timestamp."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "command": command.strip(),
            "source": source   # "text" or "voice"
        }
        records = self._load()
        records.append(entry)
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ CommandLogger write error: {e}")

    def _load(self):
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def get_all(self):
        return self._load()


# ==========================================
# 3c. COMMAND RECOMMENDER
# ==========================================
class CommandRecommender:
    """Reads command log and recommends the user's most frequent commands."""

    TOP_N = 5

    def __init__(self, logger: CommandLogger):
        self.logger = logger

    @staticmethod
    def _hour_band(hour: int) -> str:
        if 5 <= hour < 12:  return "morning"
        if 12 <= hour < 17: return "afternoon"
        if 17 <= hour < 21: return "evening"
        return "night"

    def get_recommendations(self, time_aware=True):
        """Return top-N (command, count) tuples, optionally filtered by time-of-day."""
        records = self.logger.get_all()
        if not records:
            return []

        current_hour = datetime.datetime.now().hour
        band = self._hour_band(current_hour)

        if time_aware:
            filtered = []
            for r in records:
                try:
                    rec_hour = datetime.datetime.fromisoformat(r["timestamp"]).hour
                    if self._hour_band(rec_hour) == band:
                        filtered.append(r)
                except Exception:
                    pass
            # Fall back to all records when filtered set is too small
            if len(filtered) < 5:
                filtered = records
        else:
            filtered = records

        # Frequency count (case-insensitive)
        freq = {}
        for r in filtered:
            cmd = r.get("command", "").lower().strip()
            if cmd:
                freq[cmd] = freq.get(cmd, 0) + 1

        sorted_cmds = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return sorted_cmds[:self.TOP_N]

    def format_recommendations(self):
        recs = self.get_recommendations()
        if not recs:
            return "No command history yet. Start using NEXUS to get recommendations!"
        lines = [f"  {i+1}. '{cmd}'  (used {cnt} time{'s' if cnt > 1 else ''})"
                 for i, (cmd, cnt) in enumerate(recs)]
        band = self._hour_band(datetime.datetime.now().hour)
        header = f"💡 Top commands for you this {band}:"
        return header + "\n" + "\n".join(lines)


# Global logger & recommender instances (created once at startup)
command_logger = CommandLogger()
command_recommender = CommandRecommender(command_logger)
print("✅ Command Logger initialized →", LOG_FILE)

# ==========================================
# 4. SPEECH FUNCTION - FEMALE VOICE
# ==========================================
def speak(text):
    """Convert text to speech - Female voice"""
    def _speak():
        try:
            pythoncom.CoInitialize()
            engine = pyttsx3.init()
            
            # Get available voices
            voices = engine.getProperty('voices')
            
            # Try to find a female voice
            female_voice_found = False
            for voice in voices:
                # Check for female voice indicators
                if 'female' in voice.name.lower() or 'zira' in voice.name.lower() or 'heera' in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    female_voice_found = True
                    print(f"✅ Using female voice: {voice.name}")
                    break
            
            # If no female voice found, use default
            if not female_voice_found and len(voices) > 1:
                engine.setProperty('voice', voices[1].id)
                print(f"✅ Using voice: {voices[1].name}")
            
            # Set properties
            engine.setProperty('rate', 175)
            engine.setProperty('volume', 0.95)
            
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"Speech Error: {e}")
        finally:
            pythoncom.CoUninitialize()
    threading.Thread(target=_speak, daemon=True).start()

# ==========================================
# 5. VOLUME CONTROL
# ==========================================
def set_volume(level):
    """Set system volume (0-100)"""
    if not VOLUME_AVAILABLE:
        return False, "Volume control not available"
    
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        # Convert percentage to scalar
        scalar = level / 100.0
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return True, f"Volume set to {level}%"
    except Exception as e:
        return False, f"Volume error: {e}"

def get_volume():
    """Get current volume level"""
    if not VOLUME_AVAILABLE:
        return None
    
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        scalar = volume.GetMasterVolumeLevelScalar()
        return int(scalar * 100)
    except Exception as e:
        print(f"Volume get error: {e}")
        return None

def volume_up(amount=10):
    """Increase volume"""
    current = get_volume()
    if current is not None:
        new_volume = min(100, current + amount)
        return set_volume(new_volume)
    return False, "Could not get current volume"

def volume_down(amount=10):
    """Decrease volume"""
    current = get_volume()
    if current is not None:
        new_volume = max(0, current - amount)
        return set_volume(new_volume)
    return False, "Could not get current volume"

def mute_volume():
    """Mute volume"""
    return set_volume(0)

def unmute_volume():
    """Unmute volume (set to 50%)"""
    return set_volume(50)

# ==========================================
# 6. CAMERA FUNCTIONS
# ==========================================
def open_camera():
    """Open laptop camera"""
    if not CAMERA_AVAILABLE:
        return False, "OpenCV not installed. Please install: pip install opencv-python"
    
    try:
        def _open_camera():
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                speak("Could not open camera")
                return
            
            cv2.namedWindow('NEXUS Camera', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('NEXUS Camera', 640, 480)
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Add text to frame
                cv2.putText(frame, 'Press ESC to close | SPACE to take photo', (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                cv2.imshow('NEXUS Camera', frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == 27:  # ESC
                    break
                elif key == 32:  # SPACE
                    # Take photo
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"nexus_photo_{timestamp}.jpg"
                    cv2.imwrite(filename, frame)
                    speak(f"Photo saved as {filename}")
            
            cap.release()
            cv2.destroyAllWindows()
        
        threading.Thread(target=_open_camera, daemon=True).start()
        return True, "Camera opened"
    except Exception as e:
        return False, f"Camera error: {e}"

def take_photo():
    """Take a photo from camera"""
    if not CAMERA_AVAILABLE:
        return False, "OpenCV not installed"
    
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return False, "Could not open camera"
        
        ret, frame = cap.read()
        if ret:
            # Save photo
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nexus_photo_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            cap.release()
            return True, f"Photo saved as {filename}"
        
        cap.release()
        return False, "Could not capture photo"
    except Exception as e:
        return False, f"Photo error: {e}"

# ==========================================
# 7. BROWSER FUNCTIONS
# ==========================================
def get_available_browser():
    """Check for available browsers"""
    chrome_paths = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"
    ]
    
    edge_paths = [
        "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "C:/Program Files/Microsoft/Edge/Application/msedge.exe"
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            return path, "chrome"
    
    for path in edge_paths:
        if os.path.exists(path):
            return path, "edge"
    
    return None, None

def search_browser(query):
    """Search Google"""
    browser_path, browser_type = get_available_browser()
    if browser_path:
        webbrowser.open(f"https://www.google.com/search?q={query}")
        return True
    return False

def play_youtube_direct(query):
    """Play YouTube video directly"""
    search_query = query.replace(' ', '+')
    
    # Try different YouTube URL formats for better playback
    urls = [
        f"https://www.youtube.com/results?search_query={search_query}",
        f"https://www.youtube.com/embed?listType=search&list={search_query}",
        f"https://m.youtube.com/results?search_query={search_query}"
    ]
    
    for url in urls:
        try:
            webbrowser.open(url)
            time.sleep(1)
            break
        except:
            continue
    
    speak(f"Playing {query} on YouTube")

# ==========================================
# 8. TASK HANDLER - FIXED DELETE
# ==========================================
def extract_time_from_text(text):
    """Extract time from text"""
    now = datetime.datetime.now()
    text_lower = text.lower()
    
    print(f"🔍 Extracting time from: {text_lower}")
    
    # Pattern: 5pm, 5:30pm, 5:00 p.m., 5 baje
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(pm|am|p\.?m\.?|a\.?m\.?|baje)?', text_lower)
    if match:
        hr = int(match.group(1))
        mn = int(match.group(2)) if match.group(2) else 0
        meridian = match.group(3).lower() if match.group(3) else ''
        
        # Clean meridian
        meridian = meridian.replace('.', '')
        
        if 'pm' in meridian and hr < 12:
            hr += 12
        elif 'am' in meridian and hr == 12:
            hr = 0
        elif 'baje' in meridian:
            if 'raat' in text_lower or 'shaam' in text_lower:
                if hr < 12:
                    hr += 12
        
        target_time = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
        if target_time <= now:
            target_time += datetime.timedelta(days=1)
        
        return target_time
    
    # Pattern: in 5 minutes
    match = re.search(r'in (\d+) minutes?', text_lower)
    if match:
        mins = int(match.group(1))
        return now + datetime.timedelta(minutes=mins)
    
    # Pattern: tomorrow
    if 'tomorrow' in text_lower:
        target = now + datetime.timedelta(days=1)
        if 'morning' in text_lower:
            target = target.replace(hour=8, minute=0)
        else:
            target = target.replace(hour=9, minute=0)
        return target
    
    # Pattern: tonight
    if 'tonight' in text_lower:
        target = now.replace(hour=20, minute=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return target
    
    # Default: 1 minute from now
    return now + datetime.timedelta(minutes=1)

def generate_alert_message(task_name, is_early=False):
    """Generate task-specific alert message"""
    task_lower = task_name.lower()
    
    # Food-related tasks
    if any(word in task_lower for word in ["eat", "food", "khana", "dinner", "lunch", "breakfast", "snack", "bhojan"]):
        if is_early:
            return f"Jnab! 5 minutes mein khane ka time hai: {task_name}"
        else:
            return f"Jnab! Khane ka time ho gaya: {task_name}"
    
    # Gym/Exercise tasks
    elif any(word in task_lower for word in ["gym", "workout", "exercise", "kasarat", "yoga", "running"]):
        if is_early:
            return f"Jnab! 5 minutes mein gym jaane ka time hai: {task_name}"
        else:
            return f"Jnab! Gym jaane ka time ho gaya: {task_name}"
    
    # Study/Work tasks
    elif any(word in task_lower for word in ["padh", "study", "homework", "assignment", "work", "office", "project"]):
        if is_early:
            return f"Jnab! 5 minutes mein padhne ka time hai: {task_name}"
        else:
            return f"Jnab! Padhne ka time ho gaya: {task_name}"
    
    # Medicine tasks
    elif any(word in task_lower for word in ["medicine", "dawai", "tablet", "pill", "dawa"]):
        if is_early:
            return f"Jnab! 5 minutes mein dawai lene ka time hai: {task_name}"
        else:
            return f"Jnab! Dawai lene ka time ho gaya: {task_name}"
    
    # Meeting/Call tasks
    elif any(word in task_lower for word in ["meeting", "call", "phone", "skype", "zoom", "teams"]):
        if is_early:
            return f"Jnab! 5 minutes mein meeting/call ka time hai: {task_name}"
        else:
            return f"Jnab! Meeting/call ka time ho gaya: {task_name}"
    
    # Sleep/Rest tasks
    elif any(word in task_lower for word in ["sleep", "so", "rest", "nap", "aaram"]):
        if is_early:
            return f"Jnab! 5 minutes mein sone ka time hai: {task_name}"
        else:
            return f"Jnab! Sone ka time ho gaya: {task_name}"
    
    # Default message for other tasks
    else:
        if is_early:
            return f"Jnab! 5 minutes bache hain: {task_name}"
        else:
            return f"Jnab! Time ho gaya: {task_name}"

def save_task(command_text, run_time):
    """Save task and schedule alert"""
    global tasks_counter
    try:
        # Extract task name
        task_name = command_text
        prefixes = ['remind me to', 'remind me', 'reminder', 'task', 'yaad dilana', 'set reminder', 'please remind me to']
        for prefix in prefixes:
            task_name = re.sub(r'^' + prefix + r'\s+', '', task_name, flags=re.IGNORECASE)
        
        # Remove time info
        task_name = re.sub(r'at\s+\d{1,2}(?::\d{2})?\s*(?:pm|am|p\.?m\.?|a\.?m\.?|baje)?', '', task_name, flags=re.IGNORECASE)
        task_name = re.sub(r'\b\d{1,2}(?::\d{2})?\s*(?:pm|am|p\.?m\.?|a\.?m\.?|baje)\b', '', task_name, flags=re.IGNORECASE)
        task_name = re.sub(r'\b(tomorrow|tonight|morning|evening|today)\b', '', task_name, flags=re.IGNORECASE)
        task_name = ' '.join(task_name.split())
        
        if not task_name or len(task_name) < 2:
            task_name = "Task"
        
        # Calculate alert time (5 minutes before)
        alert_time = run_time - datetime.timedelta(minutes=5)
        
        # Generate simple ID for easy deletion
        tasks_counter += 1
        task_id = f"task_{tasks_counter}"
        display_id = f"{tasks_counter}"
        
        # Store task
        task_record = {
            'id': task_id,
            'display_id': display_id,
            'name': task_name,
            'command': command_text,
            'run_time': run_time,
            'alert_time': alert_time,
            'status': 'active',
            'created_at': datetime.datetime.now()
        }
        tasks_memory.append(task_record)
        
        # Remove old jobs if exist
        try:
            scheduler.remove_job(f"early_{task_id}")
        except:
            pass
        try:
            scheduler.remove_job(f"main_{task_id}")
        except:
            pass
        
        # Schedule early alert (5 minutes before)
        scheduler.add_job(
            trigger_alert,
            'date',
            run_date=alert_time,
            args=[task_name, task_id, True],
            id=f"early_{task_id}"
        )
        
        # Schedule main alert
        scheduler.add_job(
            trigger_alert,
            'date',
            run_date=run_time,
            args=[task_name, task_id, False],
            id=f"main_{task_id}"
        )
        
        print(f"\n✅ Task {display_id} scheduled: {task_name} at {run_time}")
        return True, task_name, run_time, display_id
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None, None

def trigger_alert(task_name, task_id, is_early=False):
    """Trigger alert with task-specific message"""
    # Generate task-specific message
    message = generate_alert_message(task_name, is_early)
    
    if is_early:
        title = "⏰ NEXUS EARLY ALERT"
    else:
        title = "🔔 NEXUS TASK ALERT"
    
    print(f"\n🔔 ALERT: {message}")
    
    # Notification
    try:
        notification.notify(
            title=f"NEXUS - {title}",
            message=message,
            timeout=10
        )
    except:
        pass
    
    # Beep
    if SOUND_AVAILABLE:
        for _ in range(3):
            try:
                winsound.Beep(1000, 500)
                time.sleep(0.2)
            except:
                print("\a")
    else:
        print("\a\a\a")
    
    # Speak
    speak(message)
    
    # Update status
    for task in tasks_memory:
        if task['id'] == task_id:
            task['status'] = 'completed'
            break

def delete_task(task_identifier):
    """Delete a scheduled task by ID, number, or name - FIXED"""
    try:
        # Try to find by display ID (number)
        if task_identifier.isdigit():
            display_id = task_identifier
            tasks_to_delete = []
            
            for task in tasks_memory:
                if task.get('display_id') == display_id and task['status'] == 'active':
                    tasks_to_delete.append(task)
            
            if tasks_to_delete:
                task = tasks_to_delete[0]
                task_id = task['id']
                task_name = task['name']
                tasks_memory.remove(task)
                
                # Remove scheduled jobs
                try:
                    scheduler.remove_job(f"early_{task_id}")
                except:
                    pass
                try:
                    scheduler.remove_job(f"main_{task_id}")
                except:
                    pass
                
                return True, f"Task {display_id}: {task_name}"
        
        # Try to find by name (partial match)
        else:
            task_identifier_lower = task_identifier.lower()
            found_tasks = []
            
            for task in tasks_memory:
                if task_identifier_lower in task['name'].lower() and task['status'] == 'active':
                    found_tasks.append(task)
            
            if len(found_tasks) == 1:
                # Exactly one match
                task = found_tasks[0]
                task_id = task['id']
                task_name = task['name']
                display_id = task.get('display_id', '?')
                tasks_memory.remove(task)
                
                # Remove scheduled jobs
                try:
                    scheduler.remove_job(f"early_{task_id}")
                except:
                    pass
                try:
                    scheduler.remove_job(f"main_{task_id}")
                except:
                    pass
                
                return True, f"Task {display_id}: {task_name}"
            
            elif len(found_tasks) > 1:
                # Multiple matches
                task_list = "\n".join([f"   {t.get('display_id', '?')}. {t['name']}" for t in found_tasks])
                return False, f"Multiple tasks found:\n{task_list}\nPlease specify by number"
        
        return False, "No matching task found"
        
    except Exception as e:
        print(f"Error deleting task: {e}")
        return False, f"Error: {e}"

def get_pending_tasks():
    return [t for t in tasks_memory if t['status'] == 'active']

def get_all_tasks():
    return tasks_memory

# ==========================================
# 9. COMMAND PROCESSOR
# ==========================================
def process_command(text, from_voice=False):
    if not text:
        return "[Error] Empty command"
    
    text_lower = text.lower()
    print(f"\n🎯 Processing: {text}")

    # ---- Log every command with timestamp ----
    command_logger.log(text, source="voice" if from_voice else "text")
    # ------------------------------------------

    # Check for command repetition
    is_repeat, count = check_command_repetition(text)
    if is_repeat and from_voice:
        if ask_for_task_schedule(text):
            return "[System] Please specify time for this task"

    # Recommendations
    if any(w in text_lower for w in ["recommend", "suggestion", "what should i do",
                                      "show recommendations", "frequent commands",
                                      "my top commands", "what i usually do"]):
        recs = command_recommender.format_recommendations()
        speak("Here are your top commands based on past usage.")
        return f"[Recommendations]\n{recs}"

    # Hello
    if any(word in text_lower for word in ["hello", "hi", "hey", "nexus"]):
        response = "Hello! How can I help you?"
        speak(response)
        return f"[Chat] {response}"
    
    # How are you
    if "how are you" in text_lower or "kaise ho" in text_lower:
        response = "I'm doing great! Thanks for asking."
        speak(response)
        return f"[Chat] {response}"
    
    # Your name
    if "your name" in text_lower or "kaun ho" in text_lower:
        response = "I am NEXUS, your personal assistant."
        speak(response)
        return f"[Chat] {response}"
    
    # Thanks
    if "thank" in text_lower:
        response = "You're welcome!"
        speak(response)
        return f"[Chat] {response}"
    
    # CAMERA COMMANDS
    if "camera" in text_lower or "photo" in text_lower or "picture" in text_lower:
        if "open camera" in text_lower or "start camera" in text_lower:
            success, msg = open_camera()
            if success:
                speak("Opening camera")
                return f"[Camera] {msg}"
            else:
                speak(msg)
                return f"[Error] {msg}"
        
        elif "take photo" in text_lower or "take picture" in text_lower or "click photo" in text_lower:
            success, msg = take_photo()
            if success:
                speak("Photo taken")
                return f"[Camera] {msg}"
            else:
                speak(msg)
                return f"[Error] {msg}"
        
        elif "close camera" in text_lower:
            speak("Press ESC to close camera window")
            return "[Camera] Press ESC to close"
    
    # VOLUME COMMANDS
    if "volume" in text_lower or "sound" in text_lower or "आवाज़" in text_lower:
        # Set volume to specific level
        match = re.search(r'volume (\d+)', text_lower)
        if match:
            level = int(match.group(1))
            if 0 <= level <= 100:
                success, msg = set_volume(level)
                if success:
                    speak(f"Volume set to {level} percent")
                    return f"[Volume] {msg}"
                else:
                    return f"[Error] {msg}"
        
        # Volume up/down
        if "volume up" in text_lower or "increase volume" in text_lower or "sound up" in text_lower:
            success, msg = volume_up()
            if success:
                current = get_volume()
                if current:
                    speak(f"Volume increased to {current} percent")
                return f"[Volume] {msg}"
        
        if "volume down" in text_lower or "decrease volume" in text_lower or "sound down" in text_lower:
            success, msg = volume_down()
            if success:
                current = get_volume()
                if current:
                    speak(f"Volume decreased to {current} percent")
                return f"[Volume] {msg}"
        
        if "mute" in text_lower:
            success, msg = mute_volume()
            if success:
                speak("Volume muted")
                return f"[Volume] {msg}"
        
        if "unmute" in text_lower:
            success, msg = unmute_volume()
            if success:
                speak("Volume unmuted")
                return f"[Volume] {msg}"
        
        # Get current volume
        current = get_volume()
        if current is not None:
            speak(f"Current volume is {current} percent")
            return f"[Volume] Current volume: {current}%"
        else:
            return "[Volume] Volume control not available"
    
    # TASK/REMINDER COMMANDS
    if any(word in text_lower for word in ["remind", "task", "yaad", "reminder", "schedule"]):
        run_time = extract_time_from_text(text_lower)
        success, name, time, display_id = save_task(text, run_time)
        if success:
            time_str = time.strftime("%I:%M %p")
            response = f"Done! Task #{display_id}: {name} at {time_str}"
            speak(response)
            return f"[Task] ✅ #{display_id}: {name} at {time_str}"
        else:
            response = "Sorry, couldn't schedule the task"
            speak(response)
            return f"[Error] {response}"
    
    # SHOW TASKS
    elif "show tasks" in text_lower or "list tasks" in text_lower or "pending tasks" in text_lower:
        tasks = get_pending_tasks()
        if tasks:
            result = f"[Tasks] You have {len(tasks)} pending:\n"
            for task in tasks:
                time_str = task['run_time'].strftime("%I:%M %p on %B %d")
                display_id = task.get('display_id', '?')
                result += f"   {display_id}. {task['name']} at {time_str}\n"
            speak(f"You have {len(tasks)} pending tasks")
            return result
        else:
            speak("No pending tasks")
            return "[Tasks] No pending tasks"
    
    # DELETE TASK - FIXED
    elif "delete task" in text_lower or "remove task" in text_lower or "cancel task" in text_lower:
        tasks = get_pending_tasks()
        if not tasks:
            speak("No tasks to delete")
            return "[Tasks] No pending tasks"
        
        # Extract task identifier
        identifier = re.sub(r"(delete|remove|cancel)\s+task\s+", "", text_lower).strip()
        
        if identifier:
            success, msg = delete_task(identifier)
            if success:
                speak(f"Deleted {msg}")
                return f"[Tasks] ✅ Deleted: {msg}"
            else:
                if "Multiple tasks found" in msg:
                    return f"[Tasks] {msg}"
                else:
                    speak(msg)
                    return f"[Error] {msg}"
        else:
            # Show list of tasks with numbers
            result = "[Tasks] Which task to delete? (say 'delete task 1' etc.)\n"
            for task in tasks:
                display_id = task.get('display_id', '?')
                time_str = task['run_time'].strftime("%I:%M %p")
                result += f"   {display_id}. {task['name']} at {time_str}\n"
            return result
    
    # YOUTUBE - DIRECT PLAY
    elif "youtube" in text_lower or "play" in text_lower:
        query = re.sub(r"(play|youtube|on youtube|please play)", "", text_lower).strip()
        if query:
            speak(f"Playing {query} on YouTube")
            threading.Thread(target=play_youtube_direct, args=(query,), daemon=True).start()
            return f"[YouTube] Playing {query}"
        return "[YouTube] What should I play?"
    
    # SEARCH
    elif "search" in text_lower or "google" in text_lower:
        query = re.sub(r"(search|google|for)", "", text_lower).strip()
        if query:
            success = search_browser(query)
            if success:
                speak(f"Searching for {query}")
                return f"[Search] {query}"
            else:
                speak("No browser found")
                return "[Error] No browser found"
        return "[Search] What should I search for?"
    
    # OPEN APP
    elif "open" in text_lower or "launch" in text_lower:
        # Check for camera first
        if "camera" in text_lower:
            success, msg = open_camera()
            if success:
                speak("Opening camera")
                return f"[Camera] {msg}"
        
        result = open_application(text_lower)
        if result:
            speak(result)
            return f"[App] {result}"
        else:
            query = re.sub(r"(open|launch)", "", text_lower).strip()
            if query:
                success = search_browser(query)
                if success:
                    speak(f"Searching {query}")
                    return f"[Search] {query}"
            return f"[App] Could not open {query}"
    
    # TIME
    elif "time" in text_lower:
        now = datetime.datetime.now().strftime("%I:%M %p")
        response = f"The time is {now}"
        speak(response)
        return f"[Time] {response}"
    
    # DATE
    elif "date" in text_lower or "day" in text_lower:
        now = datetime.datetime.now().strftime("%A, %B %d, %Y")
        response = f"Today is {now}"
        speak(response)
        return f"[Date] {response}"
    
    # HELP
    elif "help" in text_lower or "what can you do" in text_lower:
        help_text = """Available Commands:

📝 TASKS:
  • 'remind me to [task] at [time]' - Set reminder
  • 'show tasks' - Show all pending tasks
  • 'delete task [number]' - Delete a task (e.g., 'delete task 1')

📷 CAMERA:
  • 'open camera' - Open laptop camera
  • 'take photo' - Take a photo

🔊 VOLUME:
  • 'volume up/down' - Increase/decrease volume
  • 'volume [0-100]' - Set specific volume
  • 'mute/unmute' - Mute/unmute sound

🎵 MEDIA:
  • 'play [song] on youtube' - Play YouTube video
  • 'search [query]' - Google search

📱 APPS:
  • 'open chrome/notepad/calculator/spotify'
  
⏰ TIME/DATE:
  • 'time' - Current time
  • 'date' - Today's date

🎤 VOICE: Say 'NEXUS' then command"""
        
        speak("Here are my commands")
        return f"[Help]\n{help_text}"
    
    # DEFAULT
    else:
        response = "I didn't understand that command. Type 'help' to see all commands."
        speak(response)
        return f"[NEXUS] {response}"

def open_application(app_name):
    """Open applications"""
    user_profile = os.environ['USERPROFILE']
    
    apps = {
        "vscode": [
            fr"{user_profile}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            r"C:\Program Files\Microsoft VS Code\Code.exe"
        ],
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        ],
        "spotify": [
            fr"{user_profile}\AppData\Roaming\Spotify\Spotify.exe",
            r"C:\Program Files\Spotify\Spotify.exe"
        ],
        "word": [
            r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"
        ],
        "excel": [
            r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE"
        ]
    }
    
    app_lower = app_name.lower()
    
    if "chrome" in app_lower or "google" in app_lower:
        for path in apps["chrome"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "Chrome opened"
        # Fallback to Edge
        for path in apps["edge"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "Edge opened (Chrome not found)"
        return "No browser found"
    
    elif "edge" in app_lower:
        for path in apps["edge"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "Edge opened"
        return "Edge not found"
    
    elif "notepad" in app_lower:
        subprocess.Popen("notepad.exe")
        return "Notepad opened"
    
    elif "calculator" in app_lower or "calc" in app_lower:
        subprocess.Popen("calc.exe")
        return "Calculator opened"
    
    elif "spotify" in app_lower:
        for path in apps["spotify"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "Spotify opened"
        return "Spotify not found"
    
    elif "vscode" in app_lower or "visual studio" in app_lower or "code" in app_lower:
        for path in apps["vscode"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "VS Code opened"
        return "VS Code not found"
    
    elif "word" in app_lower or "microsoft word" in app_lower:
        for path in apps["word"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "Word opened"
        return "Word not found"
    
    elif "excel" in app_lower:
        for path in apps["excel"]:
            if os.path.exists(path):
                subprocess.Popen(path)
                return "Excel opened"
        return "Excel not found"
    
    return None

# ==========================================
# 10. VOICE WORKER
# ==========================================
class VoiceWorker(threading.Thread):
    def __init__(self, ui_callback):
        super().__init__(daemon=True)
        self.ui_callback = ui_callback
        self.running = True
        
    def run(self):
        recognizer = sr.Recognizer()
        
        try:
            with sr.Microphone() as source:
                self.ui_callback("🎤 Microphone ready. Say 'NEXUS'...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                
                while self.running:
                    try:
                        audio = recognizer.listen(source, timeout=1, phrase_time_limit=3)
                        text = recognizer.recognize_google(audio).lower()
                        
                        if "nexus" in text:
                            speak("Yes?")
                            self.ui_callback("🎯 Listening...")
                            
                            audio_cmd = recognizer.listen(source, timeout=5, phrase_time_limit=5)
                            cmd = recognizer.recognize_google(audio_cmd)
                            
                            self.ui_callback(f"📝 {cmd}")
                            res = process_command(cmd, from_voice=True)
                            self.ui_callback(f"✅ {res}")
                            
                    except sr.UnknownValueError:
                        continue
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        self.ui_callback(f"⚠️ Error: {e}")
                        
        except Exception as e:
            self.ui_callback(f"❌ Mic error: {e}")

# ==========================================
# 11. GUI WITH ALL FEATURES - FIXED CLOSING
# ==========================================
class NexusUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NEXUS - Personal Assistant")
        self.geometry("1300x850")
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1300 // 2)
        y = (self.winfo_screenheight() // 2) - (850 // 2)
        self.geometry(f'+{x}+{y}')
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=2)
        
        # Title with glow effect
        self.title_frame = ctk.CTkFrame(self, fg_color="transparent", height=80)
        self.title_frame.grid(row=0, column=0, pady=20)
        self.title_frame.grid_columnconfigure(0, weight=1)
        
        self.label = ctk.CTkLabel(
            self.title_frame, 
            text="NEXUS", 
            font=("Orbitron", 48, "bold"), 
            text_color="#22d3ee"
        )
        self.label.grid(row=0, column=0)
        
        self.tagline = ctk.CTkLabel(
            self.title_frame,
            text="Your Personal Assistant",
            font=("Arial", 14),
            text_color="#88aaee"
        )
        self.tagline.grid(row=1, column=0)
        
        # Main container
        self.main_container = ctk.CTkFrame(self)
        self.main_container.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)
        
        # Status Box (Upper half)
        self.status_box = ctk.CTkTextbox(
            self.main_container, 
            font=("Consolas", 12), 
            wrap="word",
            height=200
        )
        self.status_box.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        # Tasks Table (Lower half)
        self.table_frame = ctk.CTkFrame(self.main_container)
        self.table_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.table_frame.grid_columnconfigure(0, weight=1)
        self.table_frame.grid_rowconfigure(1, weight=1)
        
        # Table header with delete button
        self.table_header = ctk.CTkFrame(self.table_frame, fg_color="#1e293b", height=50)
        self.table_header.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.table_header.grid_columnconfigure(0, weight=1)
        self.table_header.grid_columnconfigure(1, weight=0)
        
        self.table_label = ctk.CTkLabel(
            self.table_header, 
            text="📋 Scheduled Tasks", 
            font=("Arial", 18, "bold"),
            text_color="#22d3ee"
        )
        self.table_label.grid(row=0, column=0, padx=15, pady=10, sticky="w")
        
        self.delete_btn = ctk.CTkButton(
            self.table_header,
            text="🗑️ Delete Selected",
            fg_color="#dc2626",
            hover_color="#b91c1c",
            width=150,
            height=35,
            font=("Arial", 13, "bold"),
            command=self.delete_selected_task
        )
        self.delete_btn.grid(row=0, column=1, padx=15, pady=8)
        
        # Create Treeview for tasks
        self.tree_frame_inner = ctk.CTkFrame(self.table_frame)
        self.tree_frame_inner.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.tree_frame_inner.grid_columnconfigure(0, weight=1)
        self.tree_frame_inner.grid_rowconfigure(0, weight=1)
        
        # Style for treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#2d3748",
                        foreground="#e2e8f0",
                        rowheight=30,
                        fieldbackground="#2d3748",
                        borderwidth=0)
        style.configure("Treeview.Heading", 
                        background="#1e293b",
                        foreground="#22d3ee",
                        font=('Arial', 11, 'bold'),
                        borderwidth=0)
        style.map('Treeview', background=[('selected', '#2563eb')])
        
        # Create treeview with selection
        self.tree = ttk.Treeview(self.tree_frame_inner, columns=("#", "Task", "Time", "Status"), show="headings", height=8)
        self.tree.heading("#", text="#")
        self.tree.heading("Task", text="Task Name")
        self.tree.heading("Time", text="Scheduled Time")
        self.tree.heading("Status", text="Status")
        
        self.tree.column("#", width=50, anchor="center")
        self.tree.column("Task", width=450)
        self.tree.column("Time", width=200)
        self.tree.column("Status", width=100, anchor="center")
        
        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(self.tree_frame_inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Bind double-click to delete
        self.tree.bind("<Double-1>", lambda e: self.delete_selected_task())
        
        # Input Frame
        self.input_frame = ctk.CTkFrame(self, fg_color="#1e293b", height=80)
        self.input_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        self.manual_entry = ctk.CTkEntry(
            self.input_frame, 
            placeholder_text="Type command here... (e.g., 'remind me to eat food at 5pm')", 
            height=50,
            font=("Arial", 14),
            border_width=2,
            border_color="#22d3ee"
        )
        self.manual_entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.manual_entry.bind("<Return>", lambda e: self.send_command())
        
        self.send_btn = ctk.CTkButton(
            self.input_frame, 
            text="Send", 
            width=120,
            height=50,
            font=("Arial", 16, "bold"),
            fg_color="#22d3ee",
            hover_color="#0ea5e9",
            command=self.send_command
        )
        self.send_btn.grid(row=0, column=1, padx=10)
        
        # Button Frame
        self.button_frame = ctk.CTkFrame(self, fg_color="#0f172a", height=70)
        self.button_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        # Configure 9 columns
        for i in range(9):
            self.button_frame.grid_columnconfigure(i, weight=1)
        
        # Buttons with improved styling
        buttons = [
            ("🎙️ Start Voice", "#059669", self.start_voice),
            ("🛑 Stop Voice", "#dc2626", self.stop_voice),
            ("🧹 Clear Log", "#4b5563", lambda: self.status_box.delete("1.0", "end")),
            ("⏰ Test Task", "#d97706", self.test_task),
            ("📋 Refresh", "#2563eb", self.refresh_table),
            ("📷 Camera", "#7c3aed", self.camera_command),
            ("🔊 Volume", "#0891b2", self.volume_command),
            ("💡 Recommend", "#065f46", self._show_recommendations),
            ("❓ Help", "#db2777", self.show_help)
        ]
        
        for i, (text, color, cmd) in enumerate(buttons):
            btn = ctk.CTkButton(
                self.button_frame, 
                text=text, 
                fg_color=color,
                hover_color=self.adjust_color(color, 20),
                height=45,
                font=("Arial", 13, "bold"),
                corner_radius=8,
                command=cmd
            )
            btn.grid(row=0, column=i, padx=5)
        
        # Status bar
        self.status_bar = ctk.CTkFrame(self, fg_color="#0f172a", height=30)
        self.status_bar.grid(row=4, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.status_bar.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="✅ System Ready | Female Voice Enabled",
            font=("Arial", 11),
            text_color="#94a3b8"
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        # Browser and features status
        browser_path, browser_type = get_available_browser()
        status_text = "✅ Chrome" if browser_type == "chrome" else "✅ Edge" if browser_type == "edge" else "⚠️ No Browser"
        status_text += " | " + ("✅ Camera" if CAMERA_AVAILABLE else "⚠️ Camera")
        status_text += " | " + ("✅ Volume" if VOLUME_AVAILABLE else "⚠️ Volume")
        self.status_label.configure(text=f"System Ready | {status_text}")
        
        # Initial status
        self.worker = None
        self.update_status("🚀 NEXUS Personal Assistant Started")
        self.update_status("📝 Type 'help' for all commands")
        self.update_status("⏰ Click 'Test Task' for 10-second alert")
        self.update_status("🎤 Say 'NEXUS' then your command")
        self.update_status("🗑️ Delete tasks: select and click Delete or type 'delete task 1'")
        self.update_status("✨ Task-specific alerts: 'khane ka time ho gaya', 'gym jaane ka time', etc.")
        self.update_status("💡 Click '💡 Recommend' or type 'show recommendations' to see your top commands")
        
        # Show startup recommendations after a short delay
        self.after(3500, self._show_recommendations)
        
        # Start periodic table refresh
        self.refresh_table()
        self.after(5000, self.auto_refresh)
        
        # Track help window to prevent multiple instances
        self.help_window = None
    
    def adjust_color(self, color, amount):
        """Adjust color brightness"""
        # Simple color adjustment for hover effect
        colors = {
            "#059669": "#047857",
            "#dc2626": "#b91c1c",
            "#4b5563": "#374151",
            "#d97706": "#b45309",
            "#2563eb": "#1d4ed8",
            "#7c3aed": "#6d28d9",
            "#0891b2": "#0e7490",
            "#db2777": "#be185d",
            "#065f46": "#047857",   # Recommendations button hover
        }
        return colors.get(color, color)
    
    def _show_recommendations(self):
        """Show personalized command recommendations in the status box."""
        recs = command_recommender.format_recommendations()
        self.update_status("─" * 50)
        self.update_status(recs)
        self.update_status("─" * 50)

    def auto_refresh(self):
        """Auto refresh table"""
        self.refresh_table()
        self.after(5000, self.auto_refresh)
    
    def refresh_table(self):
        """Refresh tasks table"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add pending tasks
        for task in tasks_memory:
            if task['status'] == 'active':
                time_str = task['run_time'].strftime("%I:%M %p on %B %d")
                display_name = task['name'][:50] + "..." if len(task['name']) > 50 else task['name']
                display_id = task.get('display_id', '?')
                self.tree.insert("", "end", values=(
                    display_id,
                    display_name,
                    time_str,
                    "⏳ Pending"
                ))
        
        # Add completed tasks (last 5)
        completed = [t for t in tasks_memory if t['status'] == 'completed'][-5:]
        for task in completed:
            time_str = task['run_time'].strftime("%I:%M %p on %B %d")
            display_name = task['name'][:50] + "..." if len(task['name']) > 50 else task['name']
            display_id = task.get('display_id', '?')
            self.tree.insert("", "end", values=(
                display_id,
                display_name,
                time_str,
                "✅ Done"
            ))
    
    def delete_selected_task(self):
        """Delete selected task from table - FIXED"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a task to delete")
            return
        
        # Get task number from selected item
        item = self.tree.item(selected[0])
        task_number = str(item['values'][0])
        task_name = item['values'][1]
        
        # Confirm deletion
        confirm = messagebox.askyesno("Confirm Delete", f"Delete task #{task_number}: {task_name}?")
        
        if confirm:
            success, msg = delete_task(task_number)
            if success:
                self.update_status(f"✅ Deleted: {msg}")
                self.refresh_table()
            else:
                self.update_status(f"❌ {msg}")
                messagebox.showerror("Delete Failed", msg)
    
    def update_status(self, msg):
        """Thread-safe status update"""
        def _update():
            ts = datetime.datetime.now().strftime('%H:%M:%S')
            self.status_box.insert("end", f"[{ts}] {msg}\n")
            self.status_box.see("end")
        self.after(0, _update)
    
    def test_task(self):
        """Test task with 10-second alert"""
        test_time = datetime.datetime.now() + datetime.timedelta(seconds=10)
        success, name, time, display_id = save_task("Test Task - This is a test reminder", test_time)
        if success:
            self.update_status(f"✅ Test task #{display_id} scheduled! Alert in 10 seconds")
            self.refresh_table()
        else:
            self.update_status("❌ Test task failed")
    
    def camera_command(self):
        """Quick camera command"""
        success, msg = open_camera()
        if success:
            self.update_status(f"✅ {msg}")
        else:
            self.update_status(f"❌ {msg}")
    
    def volume_command(self):
        """Show volume control dialog"""
        current = get_volume()
        if current is None:
            self.update_status("❌ Volume control not available")
            messagebox.showerror("Error", "Volume control not available.\nPlease install: pip install pycaw comtypes")
            return
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Volume Control")
        dialog.geometry("350x250")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color="#1e293b")
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (350 // 2)
        y = (dialog.winfo_screenheight() // 2) - (250 // 2)
        dialog.geometry(f'+{x}+{y}')
        
        label = ctk.CTkLabel(dialog, text=f"Current Volume: {current}%", font=("Arial", 18, "bold"), text_color="#22d3ee")
        label.pack(pady=20)
        
        slider = ctk.CTkSlider(dialog, from_=0, to=100, number_of_steps=100, height=20, progress_color="#22d3ee")
        slider.set(current)
        slider.pack(pady=20, padx=30, fill="x")
        
        def set_vol():
            val = int(slider.get())
            success, msg = set_volume(val)
            if success:
                self.update_status(f"✅ {msg}")
                dialog.destroy()
            else:
                self.update_status(f"❌ {msg}")
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        set_btn = ctk.CTkButton(btn_frame, text="Set Volume", command=set_vol, fg_color="#22d3ee", hover_color="#0ea5e9", width=120, height=40, font=("Arial", 14, "bold"))
        set_btn.pack(side="left", padx=10)
        
        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy, fg_color="#4b5563", width=120, height=40, font=("Arial", 14))
        cancel_btn.pack(side="left", padx=10)
        
        # Ensure dialog can be closed with X button
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    
    def show_help(self):
        """Show help in new window - COMPLETELY FIXED"""
        # If help window already exists, just bring it to front
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.lift()
            self.help_window.focus_force()
            return
        
        # Create new help window
        self.help_window = ctk.CTkToplevel(self)
        self.help_window.title("NEXUS Help")
        self.help_window.geometry("650x750")
        self.help_window.transient(self)
        self.help_window.configure(fg_color="#0f172a")
        
        # Center window
        self.help_window.update_idletasks()
        x = (self.help_window.winfo_screenwidth() // 2) - (650 // 2)
        y = (self.help_window.winfo_screenheight() // 2) - (750 // 2)
        self.help_window.geometry(f'+{x}+{y}')
        
        # Make sure it stays on top
        self.help_window.lift()
        self.help_window.focus_force()
        
        # Title
        title_label = ctk.CTkLabel(self.help_window, text="NEXUS - Help & Commands", 
                                  font=("Orbitron", 24, "bold"), text_color="#22d3ee")
        title_label.pack(pady=20)
        
        # Create a frame for textbox and button
        content_frame = ctk.CTkFrame(self.help_window, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        help_textbox = ctk.CTkTextbox(content_frame, font=("Consolas", 12), wrap="word", 
                                      fg_color="#1e293b", text_color="#e2e8f0")
        help_textbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        help_content = """NEXUS - Personal Assistant

📝 TASK MANAGEMENT:
  • Set reminder: 'remind me to [task] at [time]'
    Example: 'remind me to eat food at 5pm'
    Example: 'mujhe 6 baje padhna yaad dilana'
  
  • Show tasks: 'show tasks' or 'list tasks'
  
  • Delete task: 'delete task [number]'
    Example: 'delete task 1' (deletes first task)
    Example: 'delete task gym' (deletes tasks with 'gym')
  
  • Test task: Click 'Test Task' button for 10-second alert

📷 CAMERA:
  • Open camera: 'open camera' or 'start camera'
  • Take photo: 'take photo' (while camera is open)
  • Close: Press ESC key

🔊 VOLUME CONTROL:
  • Volume up: 'volume up' or 'increase volume'
  • Volume down: 'volume down' or 'decrease volume'
  • Set specific: 'volume 50' (0-100)
  • Mute: 'mute'
  • Unmute: 'unmute'

🎵 MEDIA:
  • Play YouTube: 'play [song] on youtube'
    Example: 'play despacito on youtube'
  
  • Google search: 'search [query]'
    Example: 'search python tutorial'

📱 APPLICATIONS:
  • 'open chrome' - Chrome browser
  • 'open edge' - Edge browser
  • 'open notepad' - Notepad
  • 'open calculator' - Calculator
  • 'open spotify' - Spotify
  • 'open vscode' - VS Code
  • 'open word' - Microsoft Word
  • 'open excel' - Microsoft Excel

⏰ SYSTEM:
  • 'time' - Current time
  • 'date' - Today's date

🎤 VOICE COMMANDS:
  • Say 'NEXUS' then your command
  • Example: "NEXUS, volume up"
  • Example: "NEXUS, show tasks"
  • Example: "NEXUS, delete task 1"

✨ SPECIAL FEATURES:
  • Task-specific alerts: 
    - Food: "Jnab! Khane ka time ho gaya"
    - Gym: "Jnab! Gym jaane ka time ho gaya"
    - Study: "Jnab! Padhne ka time ho gaya"
    - Medicine: "Jnab! Dawai lene ka time ho gaya"
    - Meeting: "Jnab! Meeting ka time ho gaya"
    - Sleep: "Jnab! Sone ka time ho gaya"
  • Female voice output
  • 5-minute early alert for tasks
  • Command repetition detection (6 times)
  • Auto-refresh task table
  • Visual task deletion

💡 TIPS:
  • Tasks are numbered for easy deletion
  • Double-click task in table to delete
  • Use 'delete task' without number to see list
  • Volume control requires pycaw installed"""
        
        help_textbox.insert("1.0", help_content)
        help_textbox.configure(state="disabled")
        
        # Close button with proper command
        close_btn = ctk.CTkButton(content_frame, text="Close", 
                                  command=self.close_help_window, 
                                  fg_color="#22d3ee", width=100, height=35)
        close_btn.pack(pady=10)
        
        # Ensure window can be closed with X button
        self.help_window.protocol("WM_DELETE_WINDOW", self.close_help_window)
        
        # Bind Escape key to close
        self.help_window.bind("<Escape>", lambda e: self.close_help_window())
    
    def close_help_window(self):
        """Close help window properly"""
        if self.help_window is not None:
            self.help_window.destroy()
            self.help_window = None
    
    def send_command(self):
        """Send manual command from entry"""
        cmd = self.manual_entry.get().strip()
        if cmd:
            self.update_status(f"📝 {cmd}")
            res = process_command(cmd, from_voice=False)
            for line in str(res).split('\n'):
                if line.strip():
                    self.update_status(f"✅ {line}")
            self.manual_entry.delete(0, "end")
            self.refresh_table()
    
    def start_voice(self):
        """Start voice recognition"""
        if self.worker and self.worker.is_alive():
            self.update_status("⚠️ Voice already running")
            return
        self.worker = VoiceWorker(self.update_status)
        self.worker.start()
        self.update_status("✅ Voice recognition started - Say 'NEXUS'")
    
    def stop_voice(self):
        """Stop voice recognition"""
        if self.worker:
            self.worker.running = False
            self.worker = None
            self.update_status("🛑 Voice stopped")
    
    def on_closing(self):
        """Clean up on close"""
        self.stop_voice()
        # Close help window if open
        self.close_help_window()
        scheduler.shutdown()
        self.destroy()

# ==========================================
# MAIN WITH LOADING WINDOW - FIXED
# ==========================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 NEXUS PERSONAL ASSISTANT")
    print("="*60 + "\n")
    
    # Show loading window only once
    loading = LoadingWindow()
    loading.focus()
    
    # Start main app after delay
    def start_app():
        app = NexusUI()
        app.after(100, loading.destroy_window)
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    
    # Use after to ensure loading shows properly
    loading.after(2000, start_app)
    loading.mainloop()