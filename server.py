from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
import json

app = FastAPI()

connected_bots = {}
web_monitors = []

html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Bot Monitor Dashboard</title>
    <style>
        body { font-family: Arial; text-align: center; background: #222; color: white; }
        select, button, input { padding: 8px; font-size: 16px; margin: 5px; cursor: pointer; border-radius: 5px; }
        #monitor { max-width: 90%; max-height: 70vh; border: 2px solid #555; background: #000; margin-top: 10px; }
        .controls { margin-bottom: 20px; background: #333; padding: 15px; border-radius: 10px; display: inline-block; }
        label { font-size: 16px; margin-left: 10px; }
    </style>
</head>
<body>
    <h2>Bot Monitor Dashboard</h2>
    <div class="controls">
        <select id="botSelect">
            <option value="">-- เลือกเครื่องบอท --</option>
        </select>
        
        <select id="monitorSelect">
            <option value="1">จอหลัก (Monitor 1)</option>
            <option value="2">จอรอง (Monitor 2)</option>
            <option value="0">ดูรวมทุกจอ</option>
        </select>

        <label for="fpsInput">FPS:</label>
        <input type="number" id="fpsInput" value="2" min="1" max="30" style="width: 60px;">

        <button id="playBtn" onclick="togglePlay()">เริ่มดูจอ</button>
    </div>
    <br>
    <img id="monitor" src="" alt="ภาพหน้าจอจะแสดงที่นี่" />

    <script>
        let protocol = window.location.protocol === "https:" ? "wss" : "ws";
        let ws = new WebSocket(protocol + "://" + window.location.host + "/ws");
        
        let isPlaying = false;
        let requestInterval;

        ws.onopen = function() {
            ws.send("MONITOR");
        };

        ws.onmessage = function(event) {
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
            } else {
                let url = URL.createObjectURL(event.data);
                let img = document.getElementById("monitor");
                img.src = url;
                img.onload = () => URL.revokeObjectURL(url);
            }
        };

        // ฟังก์ชันคำนวณและเริ่มการขอภาพตาม FPS ที่ตั้งไว้
        function startInterval() {
            let targetBot = document.getElementById("botSelect").value;
            let targetScreen = document.getElementById("monitorSelect").value;
            let fps = parseInt(document.getElementById("fpsInput").value) || 2;
            
            // จำกัดไม่ให้กรอก FPS มั่ว
            if (fps < 1) fps = 1;
            if (fps > 30) fps = 30;
            
            let delay = 1000 / fps; // แปลง FPS เป็นมิลลิวินาที

            requestInterval = setInterval(() => {
                ws.send(JSON.stringify({
                    action: "request_frame", 
                    target: targetBot,
                    screen: targetScreen 
                }));
            }, delay);
        }

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
                startInterval();
            } else {
                btn.innerText = "เริ่มดูจอ";
                btn.style.color = "black";
                clearInterval(requestInterval);
            }
        }

        // ทำให้เมื่อเปลี่ยนตัวเลข FPS จะมีผลทันทีโดยไม่ต้องกดปุ่มหยุด/เริ่มใหม่
        document.getElementById("fpsInput").addEventListener("change", function() {
            if (isPlaying) {
                clearInterval(requestInterval);
                startInterval();
            }
        });
        
        // ทำให้เมื่อเปลี่ยนจอ จะมีผลทันทีเช่นกัน
        document.getElementById("monitorSelect").addEventListener("change", function() {
            if (isPlaying) {
                clearInterval(requestInterval);
                startInterval();
            }
        });
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
        auth_msg = await websocket.receive_text()
        
        if auth_msg.startswith("BOT:"):
            bot_name = auth_msg.split(":")[1]
            connected_bots[bot_name] = websocket
            await update_monitors()
            
            while True:
                data = await websocket.receive_bytes()
                for monitor in web_monitors:
                    await monitor.send_bytes(data)

        elif auth_msg == "MONITOR":
            web_monitors.append(websocket)
            await websocket.send_text(json.dumps({"type": "bot_list", "bots": list(connected_bots.keys())}))
            
            while True:
                msg = await websocket.receive_text()
                data = json.loads(msg)
                if data["action"] == "request_frame":
                    target = data["target"]
                    screen = data["screen"]
                    if target in connected_bots:
                        await connected_bots[target].send_text(f"GET_FRAME:{screen}")
                        
    except WebSocketDisconnect:
        if bot_name in connected_bots:
            del connected_bots[bot_name]
            await update_monitors()
        if websocket in web_monitors:
            web_monitors.remove(websocket)

async def update_monitors():
    bot_list = json.dumps({"type": "bot_list", "bots": list(connected_bots.keys())})
    for monitor in web_monitors:
        try:
            await monitor.send_text(bot_list)
        except:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)