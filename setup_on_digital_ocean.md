# 🚀 Django + Gunicorn + Nginx Deployment Guide (Ubuntu VPS)

This guide outlines the steps to deploy a Django application using **Gunicorn** as the application server and **Nginx** as the reverse proxy on a single Ubuntu VPS.

---

## 📁 Project Structure
The guide assumes the following directory layout:
```text
/root/knossos_django_app/
├── knossos/ (Django Project Root)
└── venv/    (Python Virtual Environment)


⚙️ 1. Install Dependencies
Update your system and install the necessary system-level packages.

Bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip nginx git curl build-essential

🐍 2. Setup Project

cd /root
git clone YOUR_GIT_REPO_URL knossos_django_app
cd knossos_django_app

python3 -m venv venv
source venv/bin/activate

cd knossos
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

🧪 3. Test Django
python manage.py migrate
python manage.py collectstatic --noinput
    
    Test manually:
    /root/knossos_django_app/venv/bin/python -m gunicorn --bind 0.0.0.0:8000 knossos.wsgi:application
    Open:
    http://YOUR_SERVER_IP:8000


⚙️ 4. Gunicorn systemd Service
nano /etc/systemd/system/gunicorn.service

Paste:
[Unit]
Description=Gunicorn for knossos Django project
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=/root/knossos_django_app/knossos
ExecStart=/root/knossos_django_app/venv/bin/python -m gunicorn --workers 3 --bind unix:/run/gunicorn.sock knossos.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target

Enable & start:
    systemctl daemon-reload
    systemctl reset-failed gunicorn
    systemctl start gunicorn
    systemctl enable gunicorn
    systemctl status gunicorn


🌐 5. Nginx Configuration
nano /etc/nginx/sites-available/knossos

Paste:
    server {
            listen 80;
            server_name YOUR_SERVER_IP yourdomain.com www.yourdomain.com;

            client_max_body_size 20M;

            location = /favicon.ico { access_log off; log_not_found off; }

            location /static/ {
                alias /root/knossos_django_app/knossos/staticfiles/;
            }

            location /media/ {
                alias /root/knossos_django_app/knossos/media/;
            }

            location / {
                include proxy_params;
                proxy_pass http://unix:/run/gunicorn.sock;
            }
        }

Enable site:
    ln -s /etc/nginx/sites-available/knossos /etc/nginx/sites-enabled/
    rm /etc/nginx/sites-enabled/default
    nginx -t
    systemctl restart nginx
    systemctl enable nginx

🔥 6. Firewall
    ufw allow OpenSSH
    ufw allow 'Nginx Full'
    ufw enable
    ufw status

📦 7. Static Files
    cd /root/knossos_django_app/knossos
    source /root/knossos_django_app/venv/bin/activate
    python manage.py collectstatic --noinput

⚠️ 8. Permissions Fix (because using /root) ->not needed
    chmod 755 /root
    chmod -R 755 /root/knossos_django_app

🧪 9. Test Everything
    http://YOUR_SERVER_IP


🛠 Debug Commands
Gunicorn logs:
journalctl -u gunicorn -n 50 --no-pager

Nginx logs:
tail -n 50 /var/log/nginx/error.log

Check socket:
ls -l /run/gunicorn.sock