import socket
import sys
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session
import requests
import os
from database import db, User
from functools import wraps
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from producers.usgs_producer import producers

VM_IP = "172.31.60.136"

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8", 80))
    local_ip = s.getsockname()[0]
finally:
    s.close()

HOST = VM_IP if local_ip == VM_IP else "127.0.0.1"


#Configuration de Flask
app = Flask(__name__)
app.secret_key = "supersecretkey"
FAUST_IP = "http://localhost:6066"

#Configuration de la base SQLite
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "instance", "streamdb.sqlite")
os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Configuration email
MAIL_USERNAME = "xxx.xxx@xxx.com"
MAIL_PASSWORD = "xxx psvq ehmu udpq" 
MAIL_FROM = "Alerte Séisme <xxx.xxx@xxx.com>"
MAIL_SERVER = "xxx.xxx.com"
MAIL_PORT = 587

producer_csv = producers[1]
producer_global_csv = producers[0]
is_injecting = False

@app.route('/inject-csv')
def inject_csv():
    global is_injecting

    if is_injecting:
        return jsonify({"status": "Déjà en cours"})

    def run():
        global is_injecting
        is_injecting = True

        try:
            root_dir = os.path.abspath(os.path.join(basedir, ".."))
            csv_path = os.path.join(root_dir, "producers", "data", "all_month.csv")
            #Injecter un CSV plus petit pour test anomaly de l'Isolation Forest
            #csv_path = os.path.join(root_dir, "producers", "data", "all_month.csv")
            producer_csv.send_csv_events(
                csv_path=csv_path,
                delay=0.005,
                limit=500,
                randomize=False
            )

            producer_global_csv.send_csv_events(
                csv_path=csv_path,
                delay=0.005,
                limit=500,
                randomize=False
            )
        finally:
            is_injecting = False

    threading.Thread(target=run, daemon=True).start()

    return jsonify({"status": "Injection lancée"})

def send_earthquake_alert(to_email, magnitude, location):
    subject = "Alerte Séisme détecté"
    body = f"""
Un séisme a été détecté près de chez vous!

Localisation : {location}
Magnitude : {magnitude}

Merci de rester vigilant.
"""

    msg = MIMEMultipart()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
        
    except Exception as e:
        print("Failed to send email:", e)


def send_registeration_email(to_email, username):
    subject = "Bienvenue sur Alerte Séisme !"
    body = f"""
Bonjour {username},

Bienvenue sur Alerte Séisme ! Vous êtes maintenant inscrit pour recevoir des alertes en cas de séismes dans votre région.

Merci de votre confiance !
"""

    msg = MIMEMultipart()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
            
    except Exception as e:
            print("Failed to send email:", e)


#Page d'accueil
@app.route('/')
def index():
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else None
    return render_template('index.html', user=user)



sent_alerts = set()  
@app.route('/data')
def proxy_faust_data():
    try:
        res = requests.get(f'{FAUST_IP}/data')
        res.raise_for_status()
        data = res.json()  

        users = User.query.all()
        for event in data:
            magnitude = float(event.get("magnitude", 0))
            location = event.get("name", "Inconnue")
            region = event.get("region", "Inconnue")
            
            quake_id = f"{location}_{event.get('time', magnitude)}"

            if magnitude > 1:
                for user in users:
                    if user.get_region() != region or not user.is_alerts_enabled():
                        continue
                    key = (user.id, quake_id)
                    if key in sent_alerts:
                        continue

                    try:
                        send_earthquake_alert(user.get_email(), magnitude, location)
                        print("Alert sent to", user.get_email(), "for earthquake of magnitude", magnitude, "at", location)
                        sent_alerts.add(key)
                    except Exception as e:
                        print("Failed to send alert to", user.get_email(), ":", e)

        return jsonify(data)

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


@app.route('/stats/global')
def proxy_faust_global_stats():
    try:
        res = requests.get(f'{FAUST_IP}/stats/global')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/stats/trends')
def proxy_faust_trends():
    try:
        res = requests.get(f'{FAUST_IP}/stats/trends')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stats/topk/global')
def proxy_faust_topk_global():
    try:
        res = requests.get(f'{FAUST_IP}/stats/topk/global')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stats/topk/region')
def proxy_faust_topk_region():
    try:
        res = requests.get(f'{FAUST_IP}/stats/topk/region')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stats/topk/region/<region_name>')
def proxy_faust_topk_specific_region(region_name):
    try:
        res = requests.get(f'{FAUST_IP}/stats/topk/region/{region_name}')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/clusters')
def proxy_faust_cluster():
    try:
        res = requests.get(f'{FAUST_IP}/clusters')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


#Page de connexion
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # On récupère tous les utilisateurs et on compare l'email décrypté
        user = None
        for u in User.query.all():
            if u.get_email() == email:
                user = u
                break

        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("Connexion réussie !", "success")
            return redirect(url_for("index"))
        else:
            flash("Identifiants incorrects.", "danger")

    return render_template("login.html")


#Page d'inscription
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        region = request.form['region']
        alerts_enabled = request.form.get('alerts_enabled') == 'on'

        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for('register'))

        # Vérifier si l'username existe
        if User.query.filter_by(username=username).first():
            flash("Nom d'utilisateur déjà utilisé.", "danger")
            return redirect(url_for('register'))

        # Vérifier si l'email existe
        for u in User.query.all():
            if u.get_email() == email:
                flash("Email déjà utilisé.", "danger")
                return redirect(url_for('register'))


        new_user = User(username=username)
        new_user.set_password(password)
        new_user.set_email(email) 
        new_user.set_region(region)
        new_user.set_alerts_enabled(alerts_enabled)
        db.session.add(new_user)
        db.session.commit()


        flash("Inscription réussie ! Vous pouvez maintenant vous connecter.", "success")

        if alerts_enabled:
            try:
                send_registeration_email(email, username)
            except Exception as e:
                print("Failed to send registration email:", e)
        
        return redirect(url_for('login'))
    return render_template('register.html')


#Page de profil
@app.route('/profil')
def profil():
    user_id = session.get("user_id")
    if not user_id:
        flash("Veuillez vous connecter pour accéder à votre profil.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(user_id)
    return render_template("profil.html", user=user)

@app.route('/profil/edit', methods=['GET', 'POST'])
def edit_profil():
    user_id = session.get("user_id")
    if not user_id:
        flash("Veuillez vous connecter pour modifier votre profil.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(user_id)

    if request.method == 'POST':
        new_username = request.form['username']
        new_email = request.form['email']
        alerts_enabled = request.form.get('alerts_enabled') == 'on'

        # Vérifier unicité email
        for u in User.query.all():
            if u.get_email() == new_email and u.id != user.id:
                flash("Cet email est déjà utilisé.", "danger")
                return redirect(url_for('edit_profil'))

        user.username = new_username
        user.set_email(new_email)
        user.set_alerts_enabled(alerts_enabled)
        db.session.commit()

        flash("Profil mis à jour avec succès", "success")
        return redirect(url_for('profil'))

    return render_template('edit_profil.html', user=user)

#Admin + Décorateur pour vérifier l'admin
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        user = User.query.get(user_id)
        if not user or not user.is_admin:
            flash("Accès réservé à l'administrateur.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_dashboard():
    users = User.query.all()

    if request.method == "POST":
        action = request.form.get("action")
        user_id = request.form.get("user_id")
        user = User.query.get(user_id)

        if not user:
            flash("Utilisateur introuvable.", "danger")
            return redirect(url_for("admin_dashboard"))

        if action == "update":
            user.username = request.form["username"]
            user.set_email(request.form["email"])
            user.is_admin = "is_admin" in request.form
            db.session.commit()
            flash(f"Utilisateur {user.username} mis à jour ", "success")

        elif action == "delete" and not user.is_admin:
            db.session.delete(user)
            db.session.commit()
            flash("Utilisateur supprimé ", "info")

        return redirect(url_for("admin_dashboard"))

    return render_template("admin.html", users=users)


#Déconnexion
@app.route('/logout')
def logout():
    session.clear()
    flash("Déconnexion réussie.", "info")
    return redirect(url_for("index"))

@app.route('/graph')
def graph_page():
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else None
    return render_template('graph.html', user=user)


#KMeans

@app.route('/kmeans')
def kmean():
    user_id = session.get("user_id")
    user = User.query.get(user_id) if user_id else None
    return render_template('kmeans.html', user=user)

@app.route('/kmeans/earthquakes')
def proxy_kmeans_earthquakes():
    """Route proxy pour récupérer tous les séismes"""
    try:
        res = requests.get(f'{FAUST_IP}/kmeans/earthquakes')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/kmeans/cluster')
def proxy_kmeans_cluster():
    """Route proxy pour le clustering K-Means"""
    try:
        k = request.args.get('k', 5)
        res = requests.get(f'{FAUST_IP}/kmeans/cluster?k={k}')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    

@app.route('/kmeans/update')
def proxy_kmeans_update():
    """Route proxy pour la mise à jour incrémentale K-Means"""
    try:
        res = requests.get(f'{FAUST_IP}/kmeans/update')
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/kmeans/wait-for-update')
def proxy_kmeans_wait():
    """Route proxy pour le long polling K-Means"""
    try:
        res = requests.get(f'{FAUST_IP}/kmeans/wait-for-update', timeout=130)
        res.raise_for_status()
        return jsonify(res.json())
    except requests.Timeout:
        return jsonify({
            "has_update": False,
            "total_earthquakes": 0,
            "timeout": True
        })
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500

#Lancement
if __name__ == '__main__':
    os.makedirs(os.path.join(basedir, "instance"), exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(host=HOST, port=5000, debug=True)