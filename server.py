from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
import json

app = FastAPI()

# เก็บรายชื่อเครื่องบอทที่ออนไลน์ และคนที่กำลังเปิดเว็บดูอยู่
connected_bots = {}
web_monitors = []

# โค้ดหน้าเว็บ HTML + JavaScript แบบฝังในตัว
html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Bot Monitor Dashboard</title>
    <style>
        body { font-family: Arial; text-align: center; background: #222; color: white; }
        select, button { padding: 10px; font-size: 16px; margin: 10px; cursor: pointer; }
        #monitor { max-width: 90%; max-height: 70vh; border: 2px solid #555; background: #000; }
        .controls { margin-bottom: 20px; }
    </style>
</head>
<body>
    <h2>Bot Monitor Dashboard</h2>
    <div class="controls">
        <select id="botSelect">
            <option value="">-- เลือกเครื่องบอท --</option>
        </select>
        <button id="playBtn" onclick="togglePlay()">เริ่มดูจอ</button>
    </div>
    <img id="monitor" src="" alt="ภาพหน้าจอจะแสดงที่นี่" />

    <script>
        // เปลี่ยนจาก http เป็น ws หรือ wss อัตโนมัติ
        let protocol = window.location.protocol === "https:" ? "wss" : "ws";
        let ws = new WebSocket(protocol + "://" + window.location.host + "/ws");
        
        let isPlaying = false;
        let requestInterval;

        ws.onopen = function() {
            ws.send("MONITOR"); // บอกเซิร์ฟเวอร์ว่าฉันคือคนดูเว็บ
        };

        ws.onmessage = function(event) {
            // ถ้ารับข้อความมาเป็น String (อัปเดตรายชื่อเครื่องบอท)
            if (typeof event.data === "string") {
                let data = JSON.parse(event.data);
                if (data.type === "bot_list") {
                    let select = document.getElementById("botSelect");
                    let currentVal = select.value;
                    select.innerHTML = '<option value="">-- เลือกเครื่องบอท --</option>';
                    data.bots.forEach(bot => {
                        select.innerHTML += `<option value="${bot}">${bot}</option>`;
                    });
                    select.value = currentVal;
                }
            } 
            // ถ้ารับมาเป็นก้อนข้อมูล (รูปภาพหน้าจอ)
            else {
                let url = URL.createObjectURL(event.data);
                let img = document.getElementById("monitor");
                img.src = url;
                img.onload = () => URL.revokeObjectURL(url); // คืนพื้นที่แรม
            }
        };

        function togglePlay() {
            let targetBot = document.getElementById("botSelect").value;
            let btn = document.getElementById("playBtn");
            
            if (!targetBot) {
                alert("กรุณาเลือกเครื่องบอทก่อน!");
                return;
            }

            isPlaying = !isPlaying;
            if (isPlaying) {
                btn.innerText = "หยุด (Pause)";
                btn.style.color = "red";
                // ส่งคำสั่งขอภาพรัวๆ ทุก 0.5 วินาที
                requestInterval = setInterval(() => {
                    ws.send(JSON.stringify({action: "request_frame", target: targetBot}));
                }, 500);
            } else {
                btn.innerText = "เริ่มดูจอ";
                btn.style.color = "black";
                clearInterval(requestInterval);
            }
        }
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    bot_name = None
    try:
        # รอรับการยืนยันตัวตนว่าใครเชื่อมต่อเข้ามา
        auth_msg = await websocket.receive_text()
        
        if auth_msg.startswith("BOT:"):
            # ถ้าเป็นเครื่องบอท
            bot_name = auth_msg.split(":")[1]
            connected_bots[bot_name] = websocket
            await update_monitors() # อัปเดต Dropdown หน้าเว็บ
            
            while True:
                # รอรับรูปจากบอท แล้วส่งต่อให้คนดูเว็บทุกคน
                data = await websocket.receive_bytes()
                for monitor in web_monitors:
                    await monitor.send_bytes(data)

        elif auth_msg == "MONITOR":
            # ถ้าเป็นคนเปิดหน้าเว็บ
            web_monitors.append(websocket)
            await websocket.send_text(json.dumps({"type": "bot_list", "bots": list(connected_bots.keys())}))
            
            while True:
                # รอรับคำสั่งจากเว็บ ว่าอยากดูภาพของเครื่องไหน
                msg = await websocket.receive_text()
                data = json.loads(msg)
                if data["action"] == "request_frame":
                    target = data["target"]
                    if target in connected_bots:
                        await connected_bots[target].send_text("GET_FRAME")
                        
    except WebSocketDisconnect:
        if bot_name in connected_bots:
            del connected_bots[bot_name]
            await update_monitors()
        if websocket in web_monitors:
            web_monitors.remove(websocket)

async def update_monitors():
    # ส่งรายชื่อเครื่องคอมที่เปิดโปรแกรมอยู่ไปอัปเดตหน้าเว็บ
    bot_list = json.dumps({"type": "bot_list", "bots": list(connected_bots.keys())})
    for monitor in web_monitors:
        try:
            await monitor.send_text(bot_list)
        except:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)