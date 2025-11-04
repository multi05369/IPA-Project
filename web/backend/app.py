from flask import Flask, render_template, request, redirect, flash, jsonify
from netmiko import ConnectHandler
import os
import db
from dotenv import load_dotenv

load_dotenv()
# Your project's root is 'IPA-Project', and this file is in 'backend'.
# Flask needs to know where the templates and static folders are relative to this file.
# The default paths work because they are in the same 'backend' folder.
app = Flask(__name__, template_folder="templates", static_folder="static")
app.debug = True

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")


# Teardown DB connection after website goes down
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.close_db()


# Routes for web pages
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


# This path is just for handling adding devices
@app.route("/add_device", methods=["POST"])
def add_device_route():
    ip = request.form.get("ip_address")
    username = request.form.get("username")
    password = request.form.get("password")
    device_type = request.form.get("device_type")

    if not ip:
        flash("Please provide an IP address.", "warning")
        return redirect("/")

    success = db.add_device(ip, username, password, device_type)

    if success:
        flash(f"Device {ip} added successfully!", "success")
    else:
        flash(f"Device {ip} already exists.", "warning")

    return redirect("/user_devices")


@app.route("/user_devices")
def user_devices():
    all_devices = db.get_all_devices()
    return render_template("user_devices.html", devices=all_devices)


@app.route("/manage/<ip>")
def manage_device(ip):
    router = db.get_device_info(ip)
    config = db.get_latest_running_config(ip)
    details = db.get_latest_device_details(ip)  # show version
    interfaces = db.get_latest_interface_status(ip)  # show ip interface brief
    vrfs = db.get_latest_vrf_details(ip)  # show vrf
    running_configs = db.get_latest_running_config(ip)  # show running config

    return render_template(
        "manage_devices.html",
        ip=ip,
        router=router,
        config=config,
        details=details,
        interfaces=interfaces,
        vrfs=vrfs,
        running_configs=running_configs,
    )


# Save Changes button route
# ADD THIS NEW ROUTE
@app.route("/manage/<ip>/update_interfaces", methods=["POST"])
def update_interfaces(ip):
    # Get the list of updates from the frontend
    # e.g., [ {"name": "eth01", "enabled": True}, ... ]
    updates = request.json.get("interfaces", [])

    # 1. Get device credentials from DB
    # (Using get_router_info as it's defined in your db.py)
    device = db.get_device_info(ip)
    if not device:
        return jsonify({"status": "error", "message": "Device not found"}), 404

    # Prepare Netmiko-compatible device dictionary
    host = device.get("ip") or device.get("host")
    if not host:
        return (
            jsonify(
                {"status": "error", "message": "Device IP/host not found in database."}
            ),
            400,
        )

    netmiko_device = {
        "device_type": "cisco_ios",  # You should make this dynamic from device.get('device_type')
        "host": host,
        "username": device.get("username"),
        "password": device.get("password"),
    }

    # 2. Build the configuration commands
    config_commands = []
    for update in updates:
        iface_name = update.get("name")
        is_enabled = update.get("enabled")

        config_commands.append(f"interface {iface_name}")
        if is_enabled:
            config_commands.append("no shutdown")
        else:
            config_commands.append("shutdown")

    try:
        # 3. Apply changes to the actual device
        with ConnectHandler(**netmiko_device) as conn:
            conn.send_config_set(config_commands)
            # Fetch real interface status after config
            interfaces_output = conn.send_command(
                "show ip interface brief", use_textfsm=True
            )

        # Parse and update DB with real status
        # interfaces_output is a list of dicts if TextFSM template is available
        real_status = []
        if isinstance(interfaces_output, list):
            for iface in interfaces_output:
                real_status.append(
                    {
                        "name": iface.get("intf", iface.get("interface", "")),
                        "status": iface.get("status", ""),
                        "ip": iface.get("ipaddr", iface.get("ip_address", "")),
                        "enabled": iface.get("status", "").lower() == "up",
                    }
                )
            # Optionally update DB with real status (if you have a function for this)
            if hasattr(db, "update_interface_statuses"):
                db.update_interface_statuses(ip, real_status)
        else:
            # Fallback: just update with requested states
            db.update_interface_statuses(ip, updates)

        return jsonify(
            {
                "status": "success",
                "message": "Changes applied and saved.",
                "interfaces": real_status if real_status else updates,
            }
        )

    except Exception as e:
        print(f"Error applying interface config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# End of Save Changes button route


# Download the configuration file
@app.route("/download_config/<ip>", methods=["GET"])
def download_config(ip):
    try:
        config = db.get_latest_running_config(ip)

        if (
            config == "No configuration found"
            or config == "Error fetching configuration"
        ):
            return jsonify({"status": "error", "message": config}), 404

        device_info = db.get_device_info(ip)
        hostname = device_info.get("hostname", "device") if device_info else "device"

        # Create filename: hostname_ip_running-config.txt
        filename = f"{hostname}_{ip}_running-config.txt"

        return jsonify({"status": "ok", "filename": filename, "config": config})
    except Exception as e:
        print(f"Error downloading config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Ping endpoint: POST /manage/<ip>/ping
@app.route("/manage/<ip>/ping", methods=["POST"])
def ping_from_router(ip):
    data = request.get_json()
    target_ip = data.get("target_ip")
    if not target_ip:
        return jsonify({"status": "error", "message": "No target IP provided."}), 400

    device = db.get_device_info(ip)
    host = device.get("ip") or device.get("host")
    if not host:
        return (
            jsonify(
                {"status": "error", "message": "Device IP/host not found in database."}
            ),
            400,
        )

    netmiko_device = {
        "device_type": "cisco_ios",
        "host": host,
        "username": device.get("username"),
        "password": device.get("password"),
    }
    try:
        with ConnectHandler(**netmiko_device) as conn:
            ping_cmd = f"ping {target_ip}"
            output = conn.send_command(ping_cmd)
        # Save to MongoDB outputs collection
        db.save_command_output(ip, ping_cmd, output, success=True)
        return jsonify({"status": "ok", "output": output})
    except Exception as e:
        db.save_command_output(ip, f"ping {target_ip}", str(e), success=False)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    # Runs server
    app.run(host="0.0.0.0", port=8080)
