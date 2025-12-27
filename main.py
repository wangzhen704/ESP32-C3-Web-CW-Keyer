import network
import socket
import time
from machine import Pin

# ================= 用户配置区域 =================
SSID = "ESP_Keyer"
PASSWORD = "12345678"
MY_CALLSIGN = "BI1PRR"

# 引脚定义
KEY_PIN_NUM  = 6   # 光耦 (控制电台)
# --- 板载 LED 定义 (合宙 ESP32-C3 Core) ---
DOT_LED_NUM  = 12   # D4 灯
DASH_LED_NUM = 13   # D5 灯

# LED 极性 (通常是低电平亮)
LED_ON  = 0
LED_OFF = 1

# ================= 硬件初始化 =================
key_pin  = Pin(KEY_PIN_NUM, Pin.OUT)
dot_led  = Pin(DOT_LED_NUM, Pin.OUT)
dash_led = Pin(DASH_LED_NUM, Pin.OUT)

# 初始状态：电台不发射，灯全灭
key_pin.value(0)
dot_led.value(LED_OFF)
dash_led.value(LED_OFF)

# ================= 莫斯电码逻辑 =================
MORSE_CODE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '1': '.----', '2': '..---', '3': '...--', '4': '....-', '5': '.....',
    '6': '-....', '7': '--...', '8': '---..', '9': '----.', '0': '-----',
    '.': '.-.-.-', ',': '--..--', '?': '..--..', '/': '-..-.', '=': '-...-',
    ' ': ' ' 
}

current_wpm = 20

# 辅助函数：控制光耦和LED
def trigger_dot(duration):
    # 开始：光耦导通，点灯亮
    key_pin.value(1)
    dot_led.value(LED_ON)
    time.sleep_ms(duration)
    # 结束：光耦断开，点灯灭
    key_pin.value(0)
    dot_led.value(LED_OFF)

def trigger_dash(duration):
    # 开始：光耦导通，划灯亮
    key_pin.value(1)
    dash_led.value(LED_ON)
    time.sleep_ms(duration)
    # 结束：光耦断开，划灯灭
    key_pin.value(0)
    dash_led.value(LED_OFF)

def play_string(text, wpm):
    dot_len = int(1200 / wpm)
    dash_len = dot_len * 3
    elem_gap = dot_len      # 元素间隔
    char_gap = dot_len * 3  # 字符间隔
    word_gap = dot_len * 7  # 单词间隔
    
    print(f"TX: {text}")
    
    for char in text.upper():
        if char == ' ':
            time.sleep_ms(word_gap - char_gap)
            continue
            
        if char in MORSE_CODE:
            code = MORSE_CODE[char]
            for symbol in code:
                if symbol == '.':
                    trigger_dot(dot_len)
                elif symbol == '-':
                    trigger_dash(dash_len)
                
                # 元素之间的间隔 (灯和电台都必须是关的)
                time.sleep_ms(elem_gap)
            
            # 字符之间的间隔
            time.sleep_ms(char_gap)

# ================= 网络与服务器 (保持不变) =================

def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=SSID, password=PASSWORD, authmode=3)
    while not ap.active(): pass
    print('AP IP:', ap.ifconfig()[0])

def url_decode(s):
    res = ''
    i = 0
    while i < len(s):
        if s[i] == '+': res += ' '; i += 1
        elif s[i] == '%' and i + 2 < len(s):
            try: res += chr(int(s[i+1:i+3], 16)); i += 3
            except: res += s[i]; i += 1
        else: res += s[i]; i += 1
    return res

# HTML 页面 (AJAX版 + Log)
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>BI1PRR Dual-LED Keyer</title>
  <style>
    body { font-family: sans-serif; text-align: center; background-color: #121212; color: #e0e0e0; margin: 0; padding: 5px; }
    #logArea { 
        width: 96%; height: 120px; 
        background-color: #000; color: #00ff00; font-family: monospace; font-size: 14px;
        border: 1px solid #333; margin-bottom: 5px; padding: 5px; 
        overflow-y: scroll; text-align: left;
    }
    textarea#msgBox { width: 96%; height: 50px; font-size: 18px; margin-bottom: 5px; padding: 5px; background: #333; color: #fff; border: 1px solid #555; text-transform: uppercase;}
    .section-title { font-size: 12px; color: #888; text-align: left; margin: 5px 0 2px 10px; border-bottom: 1px solid #333; }
    .grid-container { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; padding: 0 5px; }
    .btn { padding: 8px 0; font-size: 13px; border-radius: 4px; border: none; font-weight: bold; cursor: pointer; color: white;}
    .btn:active { transform: scale(0.98); }
    .btn-call { background-color: #1976D2; }
    .btn-rst  { background-color: #7B1FA2; }
    .btn-info { background-color: #F57C00; color: black; }
    .btn-end  { background-color: #D32F2F; }
    .btn-misc { background-color: #455A64; }
    .control-bar { display: flex; align-items: center; justify-content: space-between; padding: 5px; background: #1e1e1e; margin-top: 10px; border-top: 1px solid #333;}
    .send-btn { background-color: #388E3C; color: white; padding: 10px 20px; font-size: 18px; border: none; border-radius: 5px; font-weight: bold; flex-grow: 1; margin-left: 10px;}
    .clr-btn { background-color: #D32F2F; color: white; padding: 10px; font-size: 14px; border: none; border-radius: 5px;}
    input[type=number] { width: 50px; padding: 8px; text-align: center; border-radius: 5px; border: none; background: #eee; color: #000;}
  </style>
  <script>
    function add(text) {
      var box = document.getElementById('msgBox');
      if (box.value.length > 0 && box.value.slice(-1) != ' ') box.value += ' ';
      box.value += text;
    }
    function sendData() {
      var msg = document.getElementById('msgBox').value;
      if (!msg) return;
      var speed = document.getElementById('speed').value;
      var log = document.getElementById('logArea');
      var time = new Date().toLocaleTimeString('en-US', {hour12: false, hour: "numeric", minute: "numeric", second: "numeric"});
      log.value += "[" + time + "] TX: " + msg + "\\n";
      log.scrollTop = log.scrollHeight;
      document.getElementById('msgBox').value = '';
      fetch('/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: "message=" + encodeURIComponent(msg) + "&speed=" + speed
      }).catch(err => { log.value += "[ERR] Send failed!\\n"; });
    }
    function clearLog() { document.getElementById('logArea').value = ''; }
  </script>
</head>
<body>
  <textarea id="logArea" readonly placeholder="LOG READY..."></textarea>
  <textarea id="msgBox" placeholder="INPUT..."></textarea>
  
  <div class="section-title">1. CALL</div>
  <div class="grid-container">
    <button class="btn btn-call" onclick="add('CQ CQ CQ DE BI1PRR BI1PRR PSE K')">CQ MACRO</button>
    <button class="btn btn-call" onclick="add('DE BI1PRR')">DE ME</button>
    <button class="btn btn-misc" onclick="add('KN')">KN</button>
  </div>
  <div class="section-title">2. REPORT</div>
  <div class="grid-container">
    <button class="btn btn-rst" onclick="add('UR RST 5NN 5NN')">599</button>
    <button class="btn btn-rst" onclick="add('OP NAME IS WANG ZHEN')">NAME</button>
    <button class="btn btn-rst" onclick="add('HW?')">HW?</button>
    <button class="btn btn-rst" onclick="add('R R')">R R</button>
    <button class="btn btn-rst" onclick="add('QSL?')">QSL?</button>
    <button class="btn btn-rst" onclick="add('GM')">GM</button>
  </div>
  <div class="section-title">3. INFO</div>
  <div class="grid-container">
    <button class="btn btn-info" onclick="add('MY RIG IS IC-705')">RIG 705</button>
    <button class="btn btn-info" onclick="add('PWR 10W')">10W</button>
    <button class="btn btn-info" onclick="add('ANT V-DIP')">V-DIP</button>
    <button class="btn btn-info" onclick="add('QTH BEIJING')">QTH BJ</button>
    <button class="btn btn-info" onclick="add('TNX RPRT')">TNX</button>
    <button class="btn btn-info" onclick="add('FB')">FB</button>
  </div>
  <div class="section-title">4. END</div>
  <div class="grid-container">
    <button class="btn btn-end" onclick="add('TNX FB QSO')">TNX QSO</button>
    <button class="btn btn-end" onclick="add('HPE CUAGN')">CUAGN</button>
    <button class="btn btn-end" onclick="add('73 TU E E')">73 TU</button>
  </div>
  <div class="control-bar">
    <button class="clr-btn" onclick="clearLog()">CLR</button>
    <input type="number" id="speed" value="20" min="5" max="40">
    <button class="send-btn" onclick="sendData()">TX (SEND)</button>
  </div>
</body>
</html>
"""

def start_server():
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)
    print('Web server listening on', addr)

    while True:
        try:
            cl, addr = s.accept()
            request = cl.recv(1024)
            request = str(request)
            msg_to_send = ""
            new_wpm = current_wpm
            if "POST /send" in request:
                try:
                    body = request.split('\\r\\n\\r\\n')[1]
                    parts = body.split('&')
                    for part in parts:
                        key, val = part.split('=')
                        if key == 'message': msg_to_send = url_decode(val).split("'")[0]
                        elif key == 'speed': new_wpm = int(val.split("'")[0])
                except: pass
                cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nOK")
                cl.close()
                if msg_to_send: play_string(msg_to_send, new_wpm)
            else:
                response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + HTML_PAGE
                cl.send(response)
                cl.close()
        except:
            try: cl.close()
            except: pass

# 运行
start_ap()
start_server()
