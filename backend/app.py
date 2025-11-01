from flask import Flask, render_template
import sys

# Your project's root is 'IPA-Project', and this file is in 'backend'.
# Flask needs to know where the templates and static folders are relative to this file.
# The default paths work because they are in the same 'backend' folder.
app = Flask(__name__, template_folder='templates', static_folder='static')
app.debug = True

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/user_devices')
def user_devices():
    return render_template('user_devices.html')

@app.route('/manage_devices')
def manage_devices():
    return render_template('manage_devices.html')


if __name__ == '__main__':
    # Force UTF-8 output for Windows
    sys.stdout.reconfigure(encoding='utf-8')

    print("Running on: http://127.0.0.1:5001")
    print("-----------------------------------")
    
    # Disable Flask’s auto banner
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    # --- THE ONLY CHANGE IS ON THE LINE BELOW ---
    # We tell the Flask reloader to also watch our compiled CSS file for changes.
    app.run(
        host='127.0.0.1', 
        port=5001, 
        debug=True, 
        use_reloader=True, 
        extra_files=['*'] # <-- ADD THIS LINE
    )

