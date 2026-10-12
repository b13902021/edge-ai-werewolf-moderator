import cv2
import sys
import time
from ai_moderator import speak, read_gesture, show_message

# 角色配置
night_states = ["WOLF", "WITCH", "SEER", "HUNTER"]
wolf_count = 3
power_role_count = 3
villager_count = 4
player_count = wolf_count + power_role_count + villager_count

wolf_ids = set()
power_ids = set()
villager_ids = set()

witch_id = 0
antitode = True
poison = True

seer_id = 0
hunter_id = 0
gun = True

day = 1
survivors = set(range(1, player_count + 1))

def judging_game_over():
    if len(wolf_ids.intersection(survivors)) == 0:
        speak("遊戲結束，正義聯盟獲勝")
        sys.exit(0)
    elif len({witch_id, seer_id, hunter_id}.intersection(survivors)) == 0 or \
         len(villager_ids.intersection(survivors)) == 0:
        speak("遊戲結束，邪惡聯盟獲勝")
        sys.exit(0)

def shooting():
    global survivors
    speak(f"{hunter_id}號，啟動獵人技能，你要帶走的對象是")
    while True:
        try:
            op = int(input("請輸入要槍擊的號碼，悶槍請輸入0: "))
        except ValueError:
            continue
            
        if op == 0:
            speak("獵人選擇悶槍")
            break
        elif op not in survivors:
            print("此玩家已死亡或不存在")
        else:
            survivors.discard(op)
            speak(f"{op}號玩家淘汰")
            judging_game_over()
            break

def night():
    global wolf_ids, witch_id, seer_id, hunter_id
    global antitode, poison, gun

    cap = cv2.VideoCapture(0)
    state = "WOLF"
    wolf_kill = 0
    witch_poison = 0

    speak("天黑請閉眼")
    speak("狼人現身請睜眼")
    if day == 1:
        while True:
            temp_wolves = read_gesture(cap, wolf_count, "請比出你們的號碼")
            # 檢查是否有任何號碼 <= 0 或大於總玩家人數
            if any(x <= 0 or x > player_count for x in temp_wolves):
                show_message("請再比一次")
            elif len(set(temp_wolves)) != len(temp_wolves):
                show_message("玩家號碼不能重複，請再比一次")
            else:
                wolf_ids = set(temp_wolves)
                break
        
    speak("狼人請殺人")
    while state == "WOLF":
        # 讀取單一動作陣列的第一個元素
        wolf_kill = read_gesture(cap, 1, "若選擇空刀請比倒讚")[0]
        
        if wolf_kill == 0:
            show_message("請再比一次")
        elif wolf_kill > 0 and wolf_kill not in survivors:
            show_message("此玩家已死亡或不存在")
        else:
            if wolf_kill == -1: 
                wolf_kill = 0 # 將倒讚轉換為內部空刀邏輯
            state = "WITCH"
            
    speak("狼人請閉眼")
    
    speak("女巫請睜眼")
    if day == 1:
        while True:
            witch_id = read_gesture(cap, 1, "請比出你的號碼")[0]
            if witch_id <= 0 or witch_id > player_count:
                show_message("請再比一次")
            elif witch_id in wolf_ids:
                show_message("此號碼已被使用")
            else:
                break
        
    speak("他被殺死了，你要救他嗎，你要使用毒藥嗎，你要毒誰呢")
    if witch_id in survivors and antitode:
        if wolf_kill > 0:
            show_message(f"{wolf_kill}號被殺死")
        else:
            show_message("沒有人被刀")
            
    if witch_id in survivors and (antitode or poison):
        while state == "WITCH":
            op = read_gesture(cap, 1, "使用解藥比讚，使用毒藥比號碼，都不用比倒讚")[0]
            if op == 0 and not antitode:
                show_message("你已用完解藥")
            elif op == 0 and wolf_kill == witch_id:
                show_message("女巫不能自救")
            elif op > 0 and not poison:
                show_message("你已用完毒藥")
            elif op > 0 and op not in survivors:
                show_message("此玩家已死亡或不存在")
            else:
                if op == 0:
                    antitode = False
                    wolf_kill = 0
                elif op > 0:
                    poison = False
                    witch_poison = op
                state = "SEER"
                
    if witch_id not in survivors:
        time.sleep(15)
        state = "SEER"
        
    speak("女巫請閉眼")

    # === 預言家階段 ===
    speak("預言家請睜眼")
    if day == 1:
        while True:
            seer_id = read_gesture(cap, 1, "請比出你的號碼")[0]
            if seer_id <= 0 or seer_id > player_count:
                show_message("請再比一次")
            elif seer_id in wolf_ids or seer_id == witch_id:
                show_message("此號碼已被使用")
            else:
                break
        
    speak("選擇你要查驗的號碼是")
    if seer_id in survivors:
        while state == "SEER":
            op = read_gesture(cap, 1, "比出你想查驗的號碼")[0]
            if op <= 0:
                show_message("請再比一次")
            elif op not in survivors:
                show_message("此玩家已死亡或不存在")
            else:
                if op in wolf_ids:
                    show_message(f"{op}號的身分是狼人")
                else:
                    show_message(f"{op}號的身分是好人")
                state = "HUNTER"
    else:
        time.sleep(15)
        state = "HUNTER"
        
    speak("預言家請閉眼")

    # === 獵人階段 ===
    speak("獵人請睜眼")
    if day == 1:
        while True:
            hunter_id = read_gesture(cap, 1, "請比出你的號碼")[0]
            if hunter_id <= 0 or hunter_id > player_count:
                show_message("請再比一次")
            elif hunter_id in wolf_ids or hunter_id in {witch_id, seer_id}:
                show_message("此號碼已被使用")
            else:
                break
        
    speak("今晚的開槍手勢")
    if witch_poison == hunter_id:
        gun = False
        
    if gun:
        show_message("出局可以開槍")
    else:
        show_message("出局無法開槍")
        
    speak("獵人請閉眼")

    cap.release()
    cv2.destroyAllWindows()
    
    # 過濾掉 0 與 -1，僅回傳實際死亡號碼
    dead = {wolf_kill, witch_poison}
    dead.discard(0)
    dead.discard(-1)
    return sorted(list(dead))
    
if __name__ == "__main__":
    while True:
        # 夜晚
        dead_ids = night()
        
        # 白天
        survivors.difference_update(dead_ids)
        
        if day == 1:
            power_ids = {witch_id, seer_id, hunter_id}
            villager_ids = set(range(1, player_count + 1)).difference(wolf_ids).difference(power_ids)
            
        speak("天亮請睜眼")
        if len(dead_ids) == 0:
            speak("昨晚是平安夜")
        else:
            dead_str = "，".join([f"{num}號" for num in dead_ids])
            speak(f"昨晚，{dead_str}被殺死")
            judging_game_over()
            
            if hunter_id in dead_ids and gun:
                shooting()
                
        while True:
            try:
                vote_id = int(input("請輸入被放逐的玩家號碼，平票則輸入0: "))
            except ValueError:
                continue
                
            if vote_id == 0:
                speak("無人被放逐")
                break
            elif vote_id not in survivors:
                print("此玩家已死亡或不存在")
            else:
                survivors.discard(vote_id)
                speak(f"{vote_id}號玩家遭到放逐")
                judging_game_over()
                
                if hunter_id == vote_id and gun:
                    shooting()
                break
                
        input("按下 Enter 鍵以進入下一夜...")
        day += 1
