from flask import Flask, render_template, request, redirect, url_for
import sys
import os
from . import db

# Your project's root is 'IPA-Project', and this file is in 'backend'.
# Flask needs to know where the templates and static folders are relative to this file.
# The default paths work because they are in the same 'backend' folder.
app = Flask(__name__, template_folder='templates', static_folder='static')
app.debug = True

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
app.config['MONGODB_URI'] = os.environ.get('MONGODB_URI')
app.config['DB_NAME'] = os.environ.get('DB_NAME')

# initialize database connection with web
db.init_db(app)

# Teardown DB connection after website goes down
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.close_db()

@app.route('/', methods=['POST'])
def index():
    return render_template('index.html')

# This path is just for handling adding devices
@app.route('/add_device', methods=['POST'])
def add_device_route():
    """
    Handles the form submission from index.html.
    This is the SYNCHRONOUS test you wanted.
    """
    if request.method == 'POST':
        ip = request.form.get('ip_address')
        username = request.form.get('username')
        password = request.form.get('password')

        # This talks DIRECTLY to MongoDB
        success = db.add_router(ip, username, password)
        
        if success:
            print(f"Successfully added {ip} to database.")
        else:
            print(f"Device {ip} already exists.")

        # Go to the page that shows all devices
        return redirect(url_for('user_devices_route'))

@app.route('/user_devices')
def user_devices():
    all_routers = db.get_all_routers()
    return render_template('user_devices.html', routers=all_routers)

@app.route('/manage/<ip>')
def manage_device(ip):
    router = db.get_router_info(ip)
    # 1. Get latest data from DB
    config = db.get_latest_running_config(ip)
    details = db.get_latest_device_details(ip)
    interfaces = db.get_latest_interface_status(ip)
    vrfs = db.get_latest_vrf_details(ip)
    print("in manage_device route rn")
    # 2. Render the template
    return render_template('manage_devices.html', 
                            ip=ip, 
                            router=router,
                            config=config, 
                            details=details, 
                            interfaces=interfaces,
                            vrfs=vrfs)


if __name__ == '__main__':
    # Runs server
    app.run(debug=True, host='0.0.0.0', port=5000)

