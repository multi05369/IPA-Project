from flask import Flask, render_template, request, redirect, flash, jsonify
from netmiko import ConnectHandler
import os
import db
from dotenv import load_dotenv

load_dotenv()
# Your project's root is 'IPA-Project', and this file is in 'backend'.
# Flask needs to know where the templates and static folders are relative to this file.
# The default paths work because they are in the same 'backend' folder.
app = Flask(__name__, template_folder='templates', static_folder='static')
app.debug = True

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

# Teardown DB connection after website goes down
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.close_db()


# Routes for web pages
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

# This path is just for handling adding devices
@app.route('/add_device', methods=['POST'])
def add_device_route():
    ip = request.form.get('ip_address')
    username = request.form.get('username')
    password = request.form.get('password')
    device_type = request.form.get('device_type')

    if not ip:
        flash("Please provide an IP address.", "warning")
        return redirect('/')

    success = db.add_device(ip, username, password, device_type)

    if success:
        flash(f"Device {ip} added successfully!", "success")
    else:
        flash(f"Device {ip} already exists.", "warning")

    return redirect('/user_devices')

@app.route('/user_devices')
def user_devices():
    all_devices = db.get_all_devices()
    return render_template('user_devices.html', devices=all_devices)

@app.route('/manage/<ip>')
def manage_device(ip):
    router = db.get_router_info(ip)
    config = db.get_latest_running_config(ip)
    details = db.get_latest_device_details(ip) #show version
    interfaces = db.get_latest_interface_status(ip) #show ip interface brief
    vrfs = db.get_latest_vrf_details(ip) #show vrf
    running_configs = db.get_latest_running_config(ip) #show running config

    return render_template(
        'manage_devices.html',
        ip=ip,
        router=router,
        config=config,
        details=details,
        interfaces=interfaces,
        vrfs=vrfs,
        running_configs=running_configs
    )

# This is for rabbit MQ connection to everytime you press refresh config button
@app.route("/interface/<ip>/<iface>/toggle", methods=["POST"])
def toggle_interface(ip, iface):
    enable = request.json.get("enable", True)
    device = db.get_device_by_ip(ip)
    conn = ConnectHandler(**device)

    if enable:
        conn.send_config_set([f"interface {iface}", "no shutdown"])
    else:
        conn.send_config_set([f"interface {iface}", "shutdown"])

    conn.disconnect()
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    # Runs server
    app.run(host='0.0.0.0', port=5000)

