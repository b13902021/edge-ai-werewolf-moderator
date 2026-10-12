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

# ==========================================
# 1. 語音引擎初始化 (微軟 Edge 真人神經語音 + 本機備援)
# ==========================================

pygame.mixer.init()

# 新增一個全域變數，用來控制錯誤訊息只印一次
_fallback_warning_printed = False

def speak(text):
    """使用 Edge TTS 生成真人語音，若失敗則自動降級為本機 pyttsx3 備援 (支援 Win/Mac)"""
    print(f"[法官廣播]: {text}")
    
    def fallback_speak():
        global _fallback_warning_printed
        try:
            # 只有第一次觸發備援時會印出提示，之後就默默執行
            if not _fallback_warning_printed:
                print("[系統提示]: 雲端語音連線失敗，切換至本機備援語音... (後續將不再重複提示)")
                _fallback_warning_printed = True
                
            engine = pyttsx3.init()
            engine.setProperty('rate', 160)
            
            zh_voice_keywords = ['Hanhan', 'Yating', 'Zhiwei', 'Taipei', 'Ting-Ting', 'Mei-Jia', 'Sin-Ji']
            for voice in engine.getProperty('voices'):
                if any(keyword in voice.name for keyword in zh_voice_keywords):
                    engine.setProperty('voice', voice.id)
                    break
                    
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            # 本機端也徹底壞掉時的最後防線
            if not _fallback_warning_printed:
                print(f"備用語音錯誤: {e}")
                _fallback_warning_printed = True

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

def put_chinese_text(img, text, position, text_color=(0, 255, 255), font_size=30):
    """使用 Pillow 在 OpenCV 影像上繪製中文字"""
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    try:
        font = ImageFont.truetype("msjh.ttc", font_size)
    except IOError:
        font = ImageFont.load_default()
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

    # 台灣嚴格版數字 3 (OK 手勢：大拇指食指收起，其餘完全伸直)
    if up_fingers == [False, False, True, True, True]: return 3

    # === 1~9 常規手勢 ===
    if up_fingers == [False, True, False, False, False]: return 1
    if up_fingers == [False, True, True, False, False]: return 2
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
def read_gesture(cap, n, prompt=""):
    target_gestures = []
    first_seen_time = 0
    last_seen_time = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break

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
def show_message(text, duration=3.0):
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
    label = tk.Label(root, text=text, font=("微軟正黑體", 24, "bold"), 
                     fg="#ff6b6b", bg="#2b2b2b")
    label.pack(expand=True)

    root.after(int(duration * 1000), root.destroy)
    root.mainloop()