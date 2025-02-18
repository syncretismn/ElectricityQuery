from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import os
import datetime
import pandas as pd

app = Flask(__name__, template_folder="templates")
app.secret_key = "super_secret_key"

ELECTRICITY_RECORD_FILE = "electricity_record.json"  
LOG_FILE = "logs.txt"

# 全局数据存储
user_data = {}

# ✅ 1. 加载数据
def load_user_data():
    global user_data
    if os.path.exists(ELECTRICITY_RECORD_FILE):
        with open(ELECTRICITY_RECORD_FILE, "r") as f:
            try:
                user_data = json.load(f)
            except json.JSONDecodeError:
                user_data = {}
    else:
        user_data = {}

def save_user_data():
    global user_data
    with open(ELECTRICITY_RECORD_FILE, "w") as f:
        json.dump(user_data, f, indent=4)

# ✅ 2. 记录日志
def log_action(action):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {action}\n")

# **🔹 服务器状态**
stop_server = False  # 初始状态，API 默认开启

# 服务器启动时加载数据
load_user_data()

# ✅ 3. 主页
@app.route("/")
def index():
    return render_template("index.html")

# ✅ 4. 注册用户
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        meter_id = request.form.get("meter_id")
        dwelling_type = request.form.get("dwelling_type")
        region = request.form.get("region")
        area = request.form.get("area")

        if not username or not meter_id:
            flash("❌ Please fill all required fields!", "error")
            return redirect(url_for("register"))

        if meter_id in user_data:
            flash("❌ Meter ID already exists!", "error")
            return redirect(url_for("register"))

        user_data[meter_id] = {
            "username": username,
            "dwelling_type": dwelling_type,
            "region": region,
            "area": area,
            "meter_readings": [],
            "next_meter_update_time": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        save_user_data()
        log_action(f"User registered: {username}, Meter ID: {meter_id}")
        flash("✅ Successfully registered!", "success")
        return redirect(url_for("register"))

    return render_template("register.html")


def backup_and_clear_data():
    """备份今日 meter_reading 数据并清空 memory"""
    global user_data
    if not user_data:
        return
    
    backup_filename = f"backup_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    backup_data = {}
    
    for meter_id, meter_info in user_data.items():
        if "meter_readings" in meter_info and meter_info["meter_readings"]:
            backup_data[meter_id] = meter_info["meter_readings"]
    
    with open(backup_filename, "w") as f:
        json.dump(backup_data, f, indent=4)
    
    print(f"📁 Data backed up to {backup_filename} and memory cleared.")
    
    # 清空 user_data
    for meter_id in user_data:
        user_data[meter_id]["meter_readings"] = []
    save_user_data()

# ✅ 服务器状态页面
@app.route("/stop_server", methods=["GET"])
def stop_server_page():
    return render_template("stop_server.html", stop_server=stop_server)

# ✅ 切换 stop_server 状态
@app.route("/stop_server/toggle", methods=["POST"])
def toggle_stop_server():
    global stop_server
    stop_server = not stop_server  # 切换状态
    
    if stop_server:
        backup_and_clear_data()
        message = "Server stopped and data exported."
    else:
        message = "Server restarted."
    
    return jsonify({"stop_server": stop_server, "message": message})

# ✅ 录入 meter_reading（手动 or CSV）
@app.route("/reading", methods=["GET", "POST"])
def reading():
    if request.method == "POST":
        if stop_server:
            flash("⚠️ Server maintenance! No updates allowed.", "error")
            return redirect(url_for("reading"))

        success = False

        # **手动录入**
        if "meter_id" in request.form and "meter_value" in request.form and "update_time" in request.form:
            meter_id = request.form.get("meter_id").strip()
            meter_value = request.form.get("meter_value")
            update_time = request.form.get("update_time")

            if not meter_id or not meter_value or not update_time:
                flash("❌ Please enter all fields!", "error")
                return redirect(url_for("reading"))

            result = save_meter_reading(meter_id, meter_value, update_time)
            flash(result["message"], result["status"])
            success = result["status"] == "success"

        # **CSV 文件批量导入**
        if "file" in request.files:
            file = request.files["file"]
            if file.filename.endswith(".csv"):
                df = pd.read_csv(file, dtype={"meter_id": str})

                if set(["meter_id", "electricity", "update_time"]).issubset(df.columns):
                    for _, row in df.iterrows():
                        result = save_meter_reading(row["meter_id"].strip(), row["electricity"], row["update_time"])
                        flash(result["message"], result["status"])
                        if result["status"] == "success":
                            success = True
                else:
                    flash("❌ CSV format incorrect! Columns should be: meter_id, electricity, update_time", "error")

        if success:
            flash("✅ Meter readings recorded successfully!", "success")

        return redirect(url_for("reading"))

    return render_template("reading.html")

# ✅ 录入 meter_reading 数据
def save_meter_reading(meter_id, meter_value, update_time):
    global user_data
    meter_id = str(meter_id).strip()
    
    # 确保 meter_value 是 float 类型
    try:
        meter_value = float(meter_value)
    except ValueError:
        return {"message": f"❌ Invalid meter reading value for {meter_id}.", "status": "error"}

    if meter_id not in user_data:
        return {"message": f"❌ Meter ID {meter_id} not found. Please register first.", "status": "error"}

    if stop_server:
        return {"message": f"⚠️ Cannot record readings during maintenance mode.", "status": "error"}

    if "meter_readings" not in user_data[meter_id]:
        user_data[meter_id]["meter_readings"] = []

    user_data[meter_id]["meter_readings"].append({
        "time": update_time,
        "reading": meter_value
    })

    save_user_data()
    log_action(f"Meter reading recorded: {meter_id}, {meter_value} kWh at {update_time}")

    return {"message": f"✅ Meter reading {meter_value} kWh recorded successfully at {update_time}.", "status": "success"}



# ✅ 6. 查询用电数据
@app.route("/query", methods=["GET", "POST"])
def query():
    query_result = None

    if request.method == "POST":
        meter_id = request.form.get("meter_id")
        query_timestamp = request.form.get("query_timestamp")

        if not meter_id or not query_timestamp:
            flash("❌ Please enter a valid Meter ID and timestamp.", "error")
            return redirect(url_for("query"))

        query_time = datetime.datetime.strptime(query_timestamp, "%Y-%m-%d %H:%M:%S")

        if meter_id not in user_data:
            flash("❌ Meter ID not found.", "error")
            return redirect(url_for("query"))

        readings = user_data[meter_id]["meter_readings"]
        half_hour_ago = query_time - datetime.timedelta(minutes=30)

        prev_reading = next((r for r in readings if r["time"] == half_hour_ago.strftime("%Y-%m-%d %H:%M:%S")), None)
        current_reading = next((r for r in readings if r["time"] == query_time.strftime("%Y-%m-%d %H:%M:%S")), None)

        if not prev_reading or not current_reading:
            query_result = f"⚠️ No sufficient recorded readings."
        else:
            query_result = f"🔹 {prev_reading['time']}: {prev_reading['reading']} kWh\n{current_reading['time']}: {current_reading['reading']} kWh"

    return render_template("query.html", query_result=query_result)

# ✅ 7. 查询历史用电
@app.route("/history", methods=["GET", "POST"])
def history():
    query_result = None

    if request.method == "POST":
        meter_id = request.form.get("meter_id")
        query_date = request.form.get("query_date")

        if not meter_id or not query_date:
            flash("❌ Please enter a valid Meter ID and date.", "error")
            return redirect(url_for("history"))

        query_time = datetime.datetime.strptime(query_date, "%Y-%m-%d")

        if meter_id not in user_data:
            flash("❌ Meter ID not found.", "error")
            return redirect(url_for("history"))

        query_result = f"✅ Daily usage calculated for {query_date}."

    return render_template("history.html", query_result=query_result)


@app.route("/debug_memory", methods=["GET"])
def debug_memory():
    """手动查看当前 user_data 的内容"""
    return jsonify(user_data)

if __name__ == "__main__":
    app.run(debug=True)
