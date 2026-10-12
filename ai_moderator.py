import cv2
import mediapipe as mp
import tkinter as tk
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import time
import math

# --- 導入真人語音所需套件 ---
import pyttsx3 
import asyncio
import edge_tts
import pygame
import tempfile
import os
import subprocess
import sys
from functools import lru_cache

# ==========================================
# 1. 語音引擎初始化 (微軟 Edge 真人神經語音 + 跨平台本機備援)
# ==========================================

pygame.mixer.init()

# 新增一個全域變數，用來控制錯誤訊息只印一次
_fallback_warning_printed = False

def speak(text):
    """使用 Edge TTS 生成真人語音，若失敗則使用 macOS/Linux/Windows 本機備援"""
    print(f"[法官廣播]: {text}")
    
    def fallback_speak():
        global _fallback_warning_printed
        try:
            # 只有第一次觸發備援時會印出提示
            if not _fallback_warning_printed:
                print("[系統提示]: 雲端語音連線失敗，切換至本機備援語音... (後續將不再重複提示)")
                _fallback_warning_printed = True
                
            # 1. Mac 系統
            if sys.platform == "darwin":
                subprocess.run(
                    ["/usr/bin/say", "-v", "Meijia", "-r", "160", text],
                    check=True,
                )
                return

            # 2. Linux 系統 (包含 Ubuntu, WSL 等)
            if sys.platform.startswith("linux"):
                # 呼叫 Linux 內建的 espeak (需確保系統已安裝 espeak)
                subprocess.run(
                    ["espeak", "-v", "zh", "-s", "160", text], 
                    check=True,
                )
                return

            # 3. Windows 系統 (透過 pyttsx3 呼叫內建語音)
            engine = pyttsx3.init()
            engine.setProperty('rate', 160)
            
            zh_voice_keywords = ['Hanhan', 'Yating', 'Zhiwei', 'Taipei']
            for voice in engine.getProperty('voices'):
                if any(keyword in voice.name for keyword in zh_voice_keywords):
                    engine.setProperty('voice', voice.id)
                    break
                    
            engine.say(text)
            engine.runAndWait()
            
        except Exception as e:
            # 終極防線：當該作業系統連內建語音都壞掉或沒安裝時，切換為無聲字幕
            print(f">>> [法官無聲字幕]: {text}")
            time.sleep(2)

    async def _speak():
        try:
            communicate = edge_tts.Communicate(text, "zh-TW-YunJheNeural", rate="+10%")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                temp_path = fp.name
                
            await communicate.save(temp_path)
            
            pygame.mixer.music.load(temp_path)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
                
            pygame.mixer.music.unload()
            os.remove(temp_path)
            
        except Exception:
            fallback_speak()
            
    asyncio.run(_speak())

@lru_cache(maxsize=16)
def chinese_font(font_size):
    """Load a Chinese-capable font once per size."""
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "msjh.ttc"),
        "msjh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, font_size)
        except OSError:
            continue
    raise RuntimeError("找不到中文字型。請安裝 Noto Sans CJK 或設定中文字型路徑。")

def put_chinese_text(img, text, position, text_color=(0, 255, 255), font_size=30):
    """Draw Chinese text with a contrasting panel on camera frames."""
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = chinese_font(font_size)
    bounds = draw.textbbox(position, text, font=font)
    background = (245, 245, 245) if sum(text_color) < 384 else (20, 20, 20)
    draw.rectangle((bounds[0] - 4, bounds[1] - 4,
                    bounds[2] + 4, bounds[3] + 4), fill=background)
    draw.text(position, text, font=font, fill=text_color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

# ==========================================
# 2. 視覺引擎初始化 (維持鎖定 0.10.9)
# ==========================================
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=10, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

def recognize_gesture(hand_landmarks):
    lm = hand_landmarks.landmark
    
    def get_dist(p1, p2):
        return math.hypot(lm[p1].x - lm[p2].x, lm[p1].y - lm[p2].y)

    def is_finger_ext(tip, pip, mcp):
        """【終極解法：向量內積】判斷手指是否與手掌方向一致"""
        # 掌心向量 (從手腕 0 到指根 mcp)
        vx_palm = lm[mcp].x - lm[0].x
        vy_palm = lm[mcp].y - lm[0].y
        
        # 手指向量 (從第二關節 pip 到指尖 tip)
        vx_finger = lm[tip].x - lm[pip].x
        vy_finger = lm[tip].y - lm[pip].y
        
        # 內積大於 0 代表方向一致 (伸展)，小於 0 代表往回彎 (收攏)
        return (vx_palm * vx_finger + vy_palm * vy_finger) > 0.0

    # 4 根手指套用向量內積判斷
    index_ext = is_finger_ext(8, 6, 5)
    middle_ext = is_finger_ext(12, 10, 9)
    ring_ext = is_finger_ext(16, 14, 13)
    pinky_ext = is_finger_ext(20, 18, 17)
    
    # 大拇指特判：拇指伸直時，指尖會遠離小指根部 (17)；收起時會貼近。
    thumb_ext = get_dist(4, 17) > get_dist(3, 17)

    up_fingers = [thumb_ext, index_ext, middle_ext, ring_ext, pinky_ext]
    ext_count = sum(up_fingers)

    # === 特殊手勢：讚(0) 與 倒讚(-1) ===
    # 嚴格要求只有大拇指伸展
    if thumb_ext and not index_ext and not middle_ext and not ring_ext and not pinky_ext:
        if lm[4].y > lm[2].y: return -1 # 拇指尖低於拇指關節 = 倒讚
        return 0                        # 否則 = 讚

    # === 特殊手勢：11 與 12 ===
    if index_ext and not ring_ext and not pinky_ext:
        if lm[8].y > lm[0].y:  # 食指指尖 Y 座標大於手腕 (朝下)
            if middle_ext and lm[12].y > lm[0].y:
                return 12
            elif not middle_ext:
                return 11

    # 拳頭
    if ext_count == 0: return 10 

    # === 1~9 常規手勢 ===
    if up_fingers == [False, True, False, False, False]: return 1
    if up_fingers == [False, True, True, False, False]: return 2
    if up_fingers == [False, True, True, True, False]: return 3
    if up_fingers == [False, False, True, True, True]: return 3
    if up_fingers == [False, True, True, True, True]: return 4
    if up_fingers == [True, True, True, True, True]: return 5
    if up_fingers == [True, False, False, False, True]: return 6
    if up_fingers == [True, True, False, False, False]: return 7
    if up_fingers == [True, True, True, False, False]: return 8
    if up_fingers == [True, True, True, True, False]: return 9

    return None

# ==========================================
# 3. 核心工具：讀取 N 個手勢
# ==========================================
class CameraError(RuntimeError):
    """The camera could not supply frames for gesture recognition."""

def read_gesture(cap, n, prompt=""):
    target_gestures = []
    first_seen_time = 0
    last_seen_time = 0

    while True:
        if not cap.isOpened():
            raise CameraError("攝影機未開啟。請確認攝影機已連接，並允許執行程式的應用程式使用攝影機。")
        ret, frame = cap.read()
        if not ret or frame is None:
            raise CameraError("無法讀取攝影機畫面。請關閉其他使用攝影機的程式，檢查連線與攝影機權限後重試。")

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)
        
        current_nums = []
        
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                num = recognize_gesture(hand_landmarks)
                if num is not None:
                    current_nums.append(num)
                    wrist = hand_landmarks.landmark[0]
                    h, w, _ = frame.shape
                    cv2.putText(frame, str(num), (int(wrist.x * w), int(wrist.y * h)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)

        current_nums.sort() 

        # --- 3 秒確認機制 (含 0.5 秒防閃爍) ---
        current_time = time.time()
        
        if len(current_nums) == n:
            if current_nums == target_gestures:
                last_seen_time = current_time
                elapsed = current_time - first_seen_time
                
                cv2.putText(frame, f"Hold: {max(0, 3.0 - elapsed):.1f}s", (10, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
                
                if elapsed >= 3.0:
                    cv2.imshow("Edge AI Werewolf Moderator", frame)
                    cv2.waitKey(1)
                    return current_nums
            else:
                if current_time - last_seen_time > 0.5:
                    target_gestures = current_nums
                    first_seen_time = current_time
                    last_seen_time = current_time
        else:
            if current_time - last_seen_time > 0.5:
                target_gestures = []

        # 顯示狀態 UI (字體縮小為 24，純黑字體)
        if prompt:
            frame = put_chinese_text(frame, prompt, (10, 10), text_color=(0, 0, 0), font_size=24)
        
        frame = put_chinese_text(frame, f"等待 {n} 個手勢確認", (10, frame.shape[0] - 40), text_color=(0, 0, 0), font_size=24)
        
        cv2.imshow("Edge AI Werewolf Moderator", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            exit()

# ==========================================
# 4. 顯示機密文字視窗
# ==========================================
# ==========================================
# 4. 顯示機密文字視窗
# ==========================================
def show_message(text, duration=3.0):
    # --- 1. Mac 專屬解法 (以 OpenCV 視窗取代 Tkinter，防當機) ---
    if sys.platform == "darwin":
        # Reuse OpenCV's Cocoa application; creating Tk here can abort macOS.
        window = "Edge AI Werewolf Moderator"
        font = chinese_font(24)
        left, top, right, bottom = font.getbbox(text)
        width = max(640, right - left + 40)
        panel = np.full((180, width, 3), 43, dtype=np.uint8)
        panel = put_chinese_text(
            panel, text, ((width - (right - left)) // 2 - left,
                          (180 - (bottom - top)) // 2 - top),
            text_color=(255, 107, 107), font_size=24,
        )
        try:
            cv2.imshow(window, panel)
            deadline = time.monotonic() + max(0, duration)
            while time.monotonic() < deadline:
                if cv2.waitKey(20) & 0xFF == ord("q"):
                    raise SystemExit(0)
        finally:
            # Remove secret information before the next game phase.
            cv2.imshow(window, np.full_like(panel, 43))
            cv2.waitKey(1)
        return

    # --- 2. Windows & Linux 解法 (維持無痕 Tkinter 視窗) ---
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    
    window_width, window_height = 550, 150
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = int((screen_width - window_width) / 2)
    y = int((screen_height - window_height) / 2)
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    root.configure(bg="#2b2b2b")
    
    # 針對 Linux 派發開源黑體，Windows 則維持微軟正黑體
    tk_font = "Noto Sans CJK TC" if sys.platform.startswith("linux") else "微軟正黑體"
    
    label = tk.Label(root, text=text, font=(tk_font, 24, "bold"), 
                     fg="#ff6b6b", bg="#2b2b2b")
    label.pack(expand=True)

    root.after(int(duration * 1000), root.destroy)
    root.mainloop()