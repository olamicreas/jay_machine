from flask import Flask, render_template, request, redirect, url_for, flash
import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flash messages

# Configuration
DISK_SIZE_THRESHOLD_GB = 200  # Threshold for disk size in GB
SERVICENOW_INSTANCE = "https://nomuracmdbtest.service-now.com/api/nose/incident"  # Replace with your instance
SERVICENOW_USERNAME = "your_username"
SERVICENOW_PASSWORD = "your_password"
SERVICENOW_RITM_TABLE = "sc_request_item"
VCENTER_USERNAME = "your_vcenter_username"
VCENTER_PASSWORD = "your_vcenter_password"

# Mapping from the image
vcenter_mapping = {
    ('saitama', 'np'): 'sdcvad00152',
    ('saitama', 'p'): 'sdcvap00023',
    ('toyosu', 'p'): 'tdcvap00102',
    ('toyosu', 'np'): 'tdcvad00102',
    ('hongkong', 'np'): 'hkvqvad00092',
    ('hongkong', 'p'): 'hkvqvap00082',
    ('singapore', 'p'): 'sinvap00075',
    ('singapore', 'np'): 'sinvad00092',
    ('redhill', 'p'): 'redvap00015',
    ('redhill', 'np'): 'redvad00024',
    ('woking', 'p'): 'wokvap00015',
    ('woking', 'np'): 'wokvad00024',
    ('piscataway', 'np'): 'pscvad00102',
    ('piscataway', 'p'): 'pscvap00038',
    ('totowa', 'p'): 'totvap00038'
}

# Function to determine the appropriate vCenter URL based on datacenter and environment
def get_vcenter_url(datacenter, environment):
    vc = vcenter_mapping.get((datacenter, environment))
    if vc:
        return f"https://{vc}.vcenter.example.com"
    else:
        return None

# Function to get VM info
def get_vm_info(vcenter_url, vm_name):
    url = f"{vcenter_url}/rest/vcenter/vm?filter.names.1={vm_name}"
    response = requests.get(url, auth=(VCENTER_USERNAME, VCENTER_PASSWORD), verify=False)
    response.raise_for_status()
    vm_info = response.json()
    if vm_info['value']:
        return vm_info['value'][0]['vm']
    return None

# Function to get VM details including disk sizes
def get_vm_details(vcenter_url, vm_id):
    url = f"{vcenter_url}/rest/vcenter/vm/{vm_id}"
    response = requests.get(url, auth=(VCENTER_USERNAME, VCENTER_PASSWORD), verify=False)
    response.raise_for_status()
    vm_details = response.json()
    disks = [disk['capacity'] for disk in vm_details['value']['disks']]
    return disks

# Function to create RITM in ServiceNow
def create_ritm(vm_name, datacenter, environment, disks):
    url = f"{SERVICENOW_INSTANCE}/api/now/table/{SERVICENOW_RITM_TABLE}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    auth = (SERVICENOW_USERNAME, SERVICENOW_PASSWORD)
    payload = {
        "short_description": f"Storage upgrade required for VM: {vm_name}",
        "description": (f"The VM {vm_name} located in datacenter {datacenter} "
                        f"and environment {environment} has insufficient disk space. "
                        f"Disks: {json.dumps(disks)}"),
        "u_vm_name": vm_name,
        "u_datacenter": datacenter,
        "u_environment": environment,
        "u_disks": json.dumps(disks)
    }
    response = requests.post(url, auth=auth, headers=headers, json=payload)
    response.raise_for_status()
    result = response.json()
    return result['result']['number']

# Function to send email
def send_email(ritm_number, vm_info):
    sender_email = "your_email@example.com"
    recipient_email = "cloud_ops@example.com"
    subject = "Action Required: Storage Upgrade"
    body = f"RITM Number: {ritm_number}\n\nVM Info: {vm_info}"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP('smtp.example.com', 587) as server:
            server.starttls()
            server.login(sender_email, "your_password")
            server.sendmail(sender_email, recipient_email, msg.as_string())
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    datacenter = request.form['datacenter']
    environment = request.form['environment']
    vm_name = request.form['vm_name']

    vcenter_url = get_vcenter_url(datacenter, environment)
    if not vcenter_url:
        flash("Invalid datacenter or environment.", "error")
        return redirect(url_for('index'))

    vm_id = get_vm_info(vcenter_url, vm_name)
    
    if vm_id is None:
        flash("VM not found.", "error")
        return redirect(url_for('index'))
    
    disks = get_vm_details(vcenter_url, vm_id)
    disks_gb = [disk / (1024 ** 3) for disk in disks]  # Convert to GB
    sufficient_space = all(disk > DISK_SIZE_THRESHOLD_GB for disk in disks_gb)

    if sufficient_space:
        flash("It's okay to proceed with the upgrade.", "success")
    else:
        ritm_number = create_ritm(vm_name, datacenter, environment, disks_gb)
        send_email(ritm_number, {
            "vm_name": vm_name,
            "datacenter": datacenter,
            "environment": environment,
            "disks": disks_gb
        })
        flash(f"Action needed by Cloud Ops. RITM {ritm_number} was created. Please follow up with Cloud Ops.", "warning")

    return redirect(url_for('result', datacenter=datacenter, environment=environment, vm_name=vm_name))

@app.route('/result')
def result():
    datacenter = request.args.get('datacenter')
    environment = request.args.get('environment')
    vm_name = request.args.get('vm_name')
    
    vcenter_url = get_vcenter_url(datacenter, environment)
    vm_id = get_vm_info(vcenter_url, vm_name)
    disks = get_vm_details(vcenter_url, vm_id)
    disks_gb = [disk / (1024 ** 3) for disk in disks]  # Convert to GB
    
    return render_template('result.html', datacenter=datacenter, environment=environment, vm_name=vm_name, disks=disks_gb)

if __name__ == '__main__':
    app.run(debug=True)
