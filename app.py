from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import threading
import time
import os
import requests

# OPTIONAL: serial only works locally (NOT on Render)
try:
    import serial
except:
    serial = None

# ==========================
# APP SETUP
# ==========================
app = Flask(__name__)

# ==========================
# EMAILJS CONFIG
# ==========================
EMAILJS_PUBLIC_KEY = "YRq3an66cPNbr5ONQ"
EMAILJS_SERVICE_ID = "service_lpu930n"
EMAILJS_TEMPLATE_ID = "template_purircj"

# ==========================
# SOIL DRY THRESHOLDS
# ==========================
SOIL_DRY_LEVELS = {"Sandy": 10, "Clay": 30, "Loamy": 25}

# ==========================
# IN-MEMORY DATABASE
# ==========================
plants = {
    1: {
        "name": "Demo Plant",
        "soil": "Loamy",
        "sensorData": {"soilMoisture": 0, "temperature": 0, "humidity": 0},
        "lastWatered": None,
        "wateringLogs": {},
        "lastAlert": 0
    }
}
plant_id_counter = 2

# ==========================
# UI PAGE
# ==========================
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Soilism</title>
<style>
:root{--bg-main:#d9d6cf;--bg-panel:#143a32;--bg-accent:#7fa89a;--bg-btn:#8fb7a8;--text-dark:#0f1f1b;--text-light:#e9f3ef;}
.dark-mode{--bg-main:#121212;--bg-panel:#1f1f1f;--bg-accent:#3a7f66;--bg-btn:#2f5f4a;--text-dark:#e9f3ef;--text-light:#d9d6cf;}
body{margin:0;font-family:Tahoma,sans-serif;background:var(--bg-main);color:var(--text-dark);}
.dashboard{max-width:1000px;margin:20px auto;padding:16px;}
.top-bar{background:var(--bg-accent);padding:12px;text-align:center;font-weight:700;}
.pokedex{display:grid;grid-template-columns:1fr 1.2fr;gap:20px;}
.sensor-panel{background:var(--bg-panel);color:var(--text-light);border-radius:12px;padding:20px;}
.sensor-item{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.2);}
.sensor-item:last-child{border:none;}
.right-panel{display:flex;flex-direction:column;}
.card,.plant-item{background:#fff;border-radius:12px;padding:16px;padding-right:56px;}
.dark-mode .card,.dark-mode .plant-item{background:#2a2a2a;color:var(--text-light);}
input,select,button{width:100%;padding:10px;margin-top:8px;border-radius:8px;border:1px solid #ccc;}
button{background:var(--bg-btn);border:none;font-weight:600;cursor:pointer;}
#plantList{margin-top:76px;display:flex;flex-direction:column;gap:20px;}
.plant-item{position:relative;cursor:pointer;}
.delete-btn{position:absolute;top:0;right:0;width:56px;height:100%;display:flex;align-items:center;justify-content:center;background:none;border:none;font-size:20px;cursor:pointer;}
.history-btn{margin-top:8px;background:#4da6ff;color:white;border:none;padding:6px;border-radius:6px;font-size:13px;}
.ok{color:#3cb371;}.low{color:#e0a800;}.high{color:#d9534f;}
@media(max-width:768px){.pokedex{grid-template-columns:1fr;}}
</style>
</head>
<body>
<div class="top-bar">SOILISM ❋</div>
<div class="dashboard">
<div class="pokedex">
<div class="sensor-panel">
<h3>PLANT DATA (IDEAL LEVELS)</h3>
<div id="soilLabel">—</div>
<div class="sensor-item"><span>Soil Moisture</span><span id="idealMoisture">—</span></div>
<div class="sensor-item"><span>Temperature</span><span id="idealTemp">—</span></div>
<div class="sensor-item"><span>Humidity</span><span id="idealHumidity">—</span></div>
</div>
<div class="right-panel">
<div class="card">
<h3>Add New Plant</h3>
<input id="plantName" placeholder="Plant Name">
<select id="soilType">
<option value="">Soil Type</option>
<option>Sandy</option>
<option>Clay</option>
<option>Loamy</option>
</select>
<button id="addPlantBtn">Add</button>
<button id="modeToggle">🌙</button>
</div>
<div id="plantList"></div>
</div>
</div>
</div>
<div id="waterModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,.5); align-items:center; justify-content:center; z-index:999;">
<div style="background:#fff;padding:20px;border-radius:12px;max-width:400px;width:90%">
<h3>💦 Watering History</h3>
<ul id="waterHistory" style="font-size:14px;line-height:1.6"></ul>
<button onclick="closeModal()">Close</button>
</div>
</div>
<script>
const IDEAL_TEXT={Sandy:{m:"10–30 %",t:"18–30 °C",h:"30–50 %"},Clay:{m:"30–60 %",t:"16–28 °C",h:"50–70 %"},Loamy:{m:"25–45 %",t:"18–26 °C",h:"40–60 %"}};
const IDEAL_NUM={Sandy:{m:[10,30],t:[18,30],h:[30,50]},Clay:{m:[30,60],t:[16,28],h:[50,70]},Loamy:{m:[25,45],t:[18,26],h:[40,60]}};

const plantName=document.getElementById("plantName");
const soilType=document.getElementById("soilType");
const addPlantBtn=document.getElementById("addPlantBtn");
const modeToggle=document.getElementById("modeToggle");
const plantList=document.getElementById("plantList");
const idealMoisture=document.getElementById("idealMoisture");
const idealTemp=document.getElementById("idealTemp");
const idealHumidity=document.getElementById("idealHumidity");
const soilLabel=document.getElementById("soilLabel");
const modal=document.getElementById("waterModal");
const historyList=document.getElementById("waterHistory");

function updateLabel(soil){
  soilLabel.textContent=soil.toUpperCase();
  idealMoisture.textContent=IDEAL_TEXT[soil].m;
  idealTemp.textContent=IDEAL_TEXT[soil].t;
  idealHumidity.textContent=IDEAL_TEXT[soil].h;
}

function status(v,min,max){
  if(v<min)return'<span class="low">Low</span>';
  if(v>max)return'<span class="high">High</span>';
  return'<span class="ok">OK</span>';
}

function loadPlants(){
  fetch("/plants")
  .then(r=>r.json())
  .then(data=>{
    plantList.innerHTML="";
    for(const id in data){
      const p=data[id];
      const s=p.sensorData;
      const r=IDEAL_NUM[p.soil];
      const div=document.createElement("div");
      div.className="plant-item";
      div.innerHTML=`
        <strong>${p.name}</strong><br>
        <small>Soil: ${p.soil}</small>

        <div style="margin-top:12px;line-height:1.6">
          🌡 ${s.temperature}°C (${status(s.temperature,r.t[0],r.t[1])})<br>
          💧 ${s.soilMoisture}% (${status(s.soilMoisture,r.m[0],r.m[1])})<br>
          🌫 ${s.humidity}% (${status(s.humidity,r.h[0],r.h[1])})
        </div>

        <div style="margin-top:10px;font-size:13px">
          🕒 Last watered: ${p.lastWatered||"Never"}<br>
          📊 Times watered: ${p.wateringLogs?Object.keys(p.wateringLogs).length:0}
        </div>

        <button class="history-btn">📜 View Watering History</button>
        <button class="delete-btn">🗑️</button>
      `;

      div.querySelector(".history-btn").onclick=e=>{
        e.stopPropagation();
        openHistory(p.wateringLogs);
      };

      div.querySelector(".delete-btn").onclick=e=>{
        e.stopPropagation();
        if(confirm("Delete this plant?")){
          fetch("/delete/"+id,{method:"POST"}).then(loadPlants);
        }
      };

      div.onclick=()=>updateLabel(p.soil);

      plantList.appendChild(div);
    }
  });
}

function openHistory(logs){
  historyList.innerHTML="";
  if(!logs || Object.keys(logs).length === 0){
    historyList.innerHTML="<li>No watering records</li>";
  } else {
    Object.values(logs).reverse().forEach(l=>{
      const li=document.createElement("li");
      li.textContent=l.time;
      historyList.appendChild(li);
    });
  }
  modal.style.display="flex";
}

function closeModal(){modal.style.display="none";}

addPlantBtn.onclick=()=>{
  if(!plantName.value||!soilType.value){
    alert("Fill all fields");
    return;
  }
  fetch("/add",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name:plantName.value,soil:soilType.value})
  }).then(()=>{
    plantName.value="";
    soilType.value="";
    loadPlants();
  });
};

modeToggle.onclick=()=>{
  document.body.classList.toggle("dark-mode");
  modeToggle.textContent=document.body.classList.contains("dark-mode")?"☀️":"🌙";
};

setInterval(loadPlants,2000);
loadPlants();
</script>
</body>
</html>
"""

# ==========================
# EMAIL FUNCTION
# ==========================
def send_email_notification(plant):
    payload = {
        "service_id": EMAILJS_SERVICE_ID,
        "template_id": EMAILJS_TEMPLATE_ID,
        "user_id": EMAILJS_PUBLIC_KEY,
        "template_params": {
            "plant_name": plant["name"],
            "soil_type": plant["soil"],
            "soil_moisture": plant["sensorData"]["soilMoisture"],
            "temperature": plant["sensorData"]["temperature"],
            "humidity": plant["sensorData"]["humidity"],
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    }

    try:
        requests.post(
            "https://api.emailjs.com/api/v1.0/email/send",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print("✅ Email sent")
    except Exception as e:
        print("❌ Email error:", e)

# ==========================
# SERIAL THREAD (LOCAL ONLY)
# ==========================
def serial_worker():
    if serial is None:
        print("⚠ Serial module not available.")
        return

    last_data = None

    while True:
        try:
            ser = serial.Serial("COM4", 9600, timeout=1)
            print("✅ Arduino connected on COM4")
            time.sleep(2)

            while True:
                line = ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                parts = [p.strip() for p in line.split(",")]
                if len(parts) != 3:
                    continue

                try:
                    soil = int(parts[0])
                    temp = float(parts[1])
                    hum = float(parts[2])
                except:
                    continue

                new_data = {"soilMoisture": soil, "temperature": temp, "humidity": hum}

                # Update ALL plants
                for plant in plants.values():
                    plant["sensorData"] = new_data

                if new_data != last_data:
                    print(f"📊 Updated all plants: {new_data}")
                    last_data = new_data.copy()

                # Check dry soil alerts
                for plant in plants.values():
                    threshold = SOIL_DRY_LEVELS.get(plant["soil"], 25)
                    now = time.time()

                    if soil <= threshold and now - plant["lastAlert"] > 3600:
                        print(f"⚠ Dry soil → emailing {plant['name']}")
                        send_email_notification(plant)
                        plant["lastAlert"] = now

        except Exception as e:
            print("⚠ Arduino not connected — retrying...", e)
            time.sleep(5)

# ==========================
# ROUTES
# ==========================
@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/plants")
def get_plants():
    return jsonify(plants)

@app.route("/add", methods=["POST"])
def add_plant():
    global plant_id_counter
    data = request.json

    plants[plant_id_counter] = {
        "name": data["name"],
        "soil": data["soil"],
        "sensorData": {"soilMoisture": 0, "temperature": 0, "humidity": 0},
        "lastWatered": None,
        "wateringLogs": {},
        "lastAlert": 0
    }

    plant_id_counter += 1
    return "", 200

@app.route("/delete/<int:pid>", methods=["POST"])
def delete_plant(pid):
    plants.pop(pid, None)
    return "", 200

@app.route("/water/<int:pid>", methods=["POST"])
def water_plant(pid):
    if pid not in plants:
        return "", 404

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plants[pid]["wateringLogs"][now] = {"time": now}
    plants[pid]["lastWatered"] = now
    return "", 200

# ==========================
# NEW ROUTE: SENSOR UPDATE (WORKS ONLINE)
# ==========================
@app.route("/update_sensor", methods=["POST"])
def update_sensor():
    data = request.json

    try:
        soil = int(data["soilMoisture"])
        temp = float(data["temperature"])
        hum = float(data["humidity"])
    except:
        return jsonify({"error": "Invalid sensor values"}), 400

    new_data = {"soilMoisture": soil, "temperature": temp, "humidity": hum}

    for plant in plants.values():
        plant["sensorData"] = new_data

    # Check dry soil alerts
    for plant in plants.values():
        threshold = SOIL_DRY_LEVELS.get(plant["soil"], 25)
        now = time.time()

        if soil <= threshold and now - plant["lastAlert"] > 3600:
            print(f"⚠ Dry soil → emailing {plant['name']}")
            send_email_notification(plant)
            plant["lastAlert"] = now

    return jsonify({"success": True, "data": new_data}), 200

# ==========================
# RUN SERVER
# ==========================
if __name__ == "__main__":
    # ONLY run serial on local computer (NOT render)
    if os.environ.get("RENDER") is None:
        threading.Thread(target=serial_worker, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
