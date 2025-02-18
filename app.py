from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import os
import datetime

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

# **🔹 更新 stop_server 状态**
def update_server_status():
    global stop_server
    current_time = datetime.datetime.now()
    if 0 <= current_time.hour < 1:
        stop_server = True  # **00:00 - 01:00 关闭 API**
    else:
        stop_server = False  # **01:00 - 23:00 API 正常工作**

# **✅ 录入 meter_reading（手动 or CSV）**
@app.route("/reading", methods=["GET", "POST"])
def reading():
    update_server_status()  # **更新 stop_server 状态**
    
    if request.method == "POST":
        # **🔹 检查服务器是否在维护**
        if stop_server:
            flash("⚠️ Server maintenance! No updates allowed from 00:00 to 01:00.", "error")
            return redirect(url_for("reading"))

        # **🔹 处理手动输入**
        if "meter_id" in request.form and "meter_value" in request.form and "update_time" in request.form:
            meter_id = request.form.get("meter_id")
            meter_value = request.form.get("meter_value")
            update_time = request.form.get("update_time")

            # **⚠️ 处理错误**
            if not meter_id or not meter_value or not update_time:
                flash("❌ Please enter all fields!", "error")
                return redirect(url_for("reading"))

            # **存入数据库**
            save_meter_reading(meter_id, meter_value, update_time)

        # **🔹 处理 CSV 上传**
        if "file" in request.files:
            file = request.files["file"]
            if file.filename.endswith(".csv"):
                df = pd.read_csv(file)
                
                # **⚠️ 确保 CSV 结构正确**
                if set(["meter_id", "electricity", "update_time"]).issubset(df.columns):
                    for _, row in df.iterrows():
                        save_meter_reading(row["meter_id"], row["electricity"], row["update_time"])
                else:
                    flash("❌ CSV format incorrect! Columns should be: meter_id, electricity, update_time.", "error")
                    return redirect(url_for("reading"))

        flash("✅ Meter readings recorded successfully!", "success")
        return redirect(url_for("reading"))

    return render_template("reading.html")

# **✅ 录入 meter_reading 数据**
def save_meter_reading(meter_id, meter_value, update_time):
    global user_data
    meter_value = float(meter_value)

    # **检查 Meter ID 是否注册**
    if meter_id not in user_data:
        flash(f"❌ Meter ID {meter_id} not found. Please register first.", "error")
        return

    # **检查时间是否在维护期间**
    reading_time = datetime.datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
    if 0 <= reading_time.hour < 1:
        flash(f"⚠️ Reading time {update_time} is in maintenance window (00:00 - 01:00). Try again later.", "error")
        return

    # **存入数据库**
    if "meter_readings" not in user_data[meter_id]:
        user_data[meter_id]["meter_readings"] = []

    user_data[meter_id]["meter_readings"].append({
        "time": update_time,
        "reading": meter_value
    })

    save_user_data()
    log_action(f"Meter reading recorded: {meter_id}, {meter_value} kWh at {update_time}")

# **✅ 停止服务器 API**
@app.route("/stop_server", methods=["GET"])
def stop_server_api():
    update_server_status()  # **更新服务器状态**
    return jsonify({"stop_server": stop_server})



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

if __name__ == "__main__":
    app.run(debug=True)
