from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response, Response
from flask_sqlalchemy import SQLAlchemy
from flask_compress import Compress
from sqlalchemy import and_, or_
from datetime import datetime, timezone
from itsdangerous import URLSafeSerializer, BadSignature
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from threading import Thread, Event
import xml.etree.ElementTree as ET
import html
import os
import random
import re
import requests
import hashlib
import json
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gaia_conseil_2026_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gaia_conseil.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ADMIN_REGISTRATION_CODE'] = 'GAIA-ADMIN-2026'
app.config['ADMIN_DISPLAY_NAME'] = 'Relyas — Centre de Commande'

db = SQLAlchemy(app)
Compress(app)

@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 2592000  # 30 jours
        response.cache_control.public = True
    return response


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    nom = db.Column(db.String(100))
    role = db.Column(db.String(20), default='user')
    temp = db.Column(db.Float, default=28.4)
    liquide = db.Column(db.Integer, default=62)
    banned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    expediteur = db.Column(db.String(50))
    destinataire = db.Column(db.String(50))
    contenu = db.Column(db.Text)
    date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    media_url = db.Column(db.String(255))
    media_type = db.Column(db.String(20))


class SensorData(db.Model):
    """Télémétrie en temps réel des capteurs embarqués"""
    id = db.Column(db.Integer, primary_key=True)
    drone_id = db.Column(db.String(50))
    farmer_username = db.Column(db.String(50), db.ForeignKey('user.username'))
    humidity = db.Column(db.Float)  # Humidité relative %
    temperature = db.Column(db.Float)  # Température ambiante °C
    soil_ph = db.Column(db.Float)  # pH du sol
    soil_moisture = db.Column(db.Float)  # Humidité du sol %
    nitrogen_level = db.Column(db.Float)  # Azote mg/kg
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Alert(db.Model):
    """Alertes critiques du système RELYAS"""
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50))  # epidemic, drought, disease, frost, etc.
    severity = db.Column(db.String(20))  # critical, high, medium, low
    farmer_username = db.Column(db.String(50), db.ForeignKey('user.username'))
    message = db.Column(db.Text)
    data_snapshot = db.Column(db.Text)  # JSON des données
    activated = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AdminRecommendation(db.Model):
    """Recommandations d'aide à la décision (SAD)"""
    id = db.Column(db.Integer, primary_key=True)
    admin_username = db.Column(db.String(50), db.ForeignKey('user.username'))
    farmer_username = db.Column(db.String(50), db.ForeignKey('user.username'))
    content = db.Column(db.Text)  # Recommandation personnalisée
    based_on_sensor_data = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    read = db.Column(db.Boolean, default=False)


class QuickTemplate(db.Model):
    """Modèles de messages rapides (persistés)"""
    id = db.Column(db.Integer, primary_key=True)
    owner_username = db.Column(db.String(50), db.ForeignKey('user.username'), nullable=True)
    title = db.Column(db.String(150))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class DroneFleet(db.Model):
    """Gestion de la flotte de drones"""
    id = db.Column(db.Integer, primary_key=True)
    drone_id = db.Column(db.String(50), unique=True)
    farmer_username = db.Column(db.String(50), db.ForeignKey('user.username'))
    status = db.Column(db.String(20), default='offline')  # online, offline, maintenance
    battery_level = db.Column(db.Float)  # %
    last_connection = db.Column(db.DateTime)
    location = db.Column(db.String(255))  # GPS coordinates or zone
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


def ivory_coast_price_reference():
    return {
        'official_market_price': 1823,
        'official_market_label': "Prix de mise en marche Cote d'Ivoire",
        'farmgate_price': 1200,
        'farmgate_label': 'Prix bord champ producteur',
        'campaign_period': 'Campagne intermediaire 2025-2026',
        'source_label': "Reperes officiels Cote d'Ivoire"
    }


def init_db():
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username='admin').first():
            db.session.add(User(username='admin', password='123', role='admin', nom='Direction GAIA'))

        if not User.query.filter_by(username='paul').first():
            db.session.add(User(username='paul', password='123', role='user', nom='Paul Yao'))

        db.session.commit()


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)


def get_admin_users():
    return User.query.filter_by(role='admin').order_by(User.username.asc()).all()


def get_non_admin_users():
    return User.query.filter(User.role != 'admin').order_by(User.username.asc()).all()


def get_primary_admin(exclude_username=None):
    admins = get_admin_users()
    for admin in admins:
        if admin.username != exclude_username:
            return admin
    return admins[0] if admins else None


def get_dashboard_url(role):
    return url_for('admin_dashboard' if role == 'admin' else 'user_dashboard')


def resolve_display_username(expediteur):
    if not expediteur:
        return expediteur

    user = User.query.filter_by(username=expediteur).first()
    if user:
        return user.username

    legacy_user = User.query.filter_by(nom=expediteur).first()
    if legacy_user:
        return legacy_user.username

    return expediteur


def get_remember_serializer():
    return URLSafeSerializer(app.config['SECRET_KEY'], salt='remember-login')


def build_remember_token(user):
    serializer = get_remember_serializer()
    return serializer.dumps({'username': user.username, 'role': user.role})


def get_user_from_remember_cookie():
    token = request.cookies.get('gaia_remember')
    if not token:
        return None

    try:
        payload = get_remember_serializer().loads(token)
    except BadSignature:
        return None

    username = payload.get('username')
    role = payload.get('role')
    if not username or not role:
        return None

    user = User.query.filter_by(username=username, role=role).first()
    return user


def admin_required(f):
    """Décorateur pour protéger les routes réservées aux admins"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        if not current_user or current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Acces refuse.'}), 403
        return f(*args, **kwargs)
    return decorated_function


def generate_relyas_token(username):
    """Génère un token SHA-256 pour la sécurité RELYAS"""
    token = f"{username}:{datetime.now().isoformat()}:{os.urandom(16).hex()}"
    return hashlib.sha256(token.encode()).hexdigest()


def expert_thread_query_for_user(username):
    admin_usernames = [admin.username for admin in get_admin_users()]
    return Message.query.filter(
        or_(
            and_(Message.expediteur == username, Message.destinataire.in_(admin_usernames)),
            and_(Message.destinataire == username, Message.expediteur.in_(admin_usernames))
        )
    ).order_by(Message.date.asc())


def expert_thread_query_for_admin(target_username):
    admin_usernames = [admin.username for admin in get_admin_users()]
    return Message.query.filter(
        or_(
            and_(Message.expediteur == target_username, Message.destinataire.in_(admin_usernames)),
            and_(Message.destinataire == target_username, Message.expediteur.in_(admin_usernames))
        )
    ).order_by(Message.date.asc())


def clean_html_excerpt(content, max_length=220):
    if not content:
        return ''
    text = re.sub(r'<[^>]+>', ' ', content)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_length:
        return text[:max_length].rsplit(' ', 1)[0] + '...'
    return text


def extract_meta_content(page_html, meta_name):
    patterns = [
        rf'<meta[^>]+property=["\']{meta_name}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{meta_name}["\']',
        rf'<meta[^>]+name=["\']{meta_name}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{meta_name}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, page_html, re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
    return ''


def extract_first_image(description_html):
    if not description_html:
        return ''
    # Look for img tags
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description_html, re.IGNORECASE)
    if match:
        img_url = html.unescape(match.group(1))
        if img_url.startswith('http'):
            return img_url
    return ''


def enrich_article_metadata(link):
    try:
        response = requests.get(
            link,
            timeout=2,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            allow_redirects=True
        )
        if response.status_code != 200:
            return {}

        page_html = response.text
        image = extract_meta_content(page_html, 'og:image')
        
        # Try multiple meta tag patterns for image
        if not image:
            image = extract_meta_content(page_html, 'twitter:image')
        if not image:
            image = extract_meta_content(page_html, 'image')
        if not image:
            image = extract_first_image(page_html)
        
        description = extract_meta_content(page_html, 'og:description')
        if not description:
            description = extract_meta_content(page_html, 'description')
        
        site_name = extract_meta_content(page_html, 'og:site_name')
        if not site_name:
            site_name = extract_meta_content(page_html, 'site_name')
        
        return {
            'image': image if image and image.startswith('http') else '',
            'description': description,
            'site_name': site_name
        }
    except Exception:
        return {}


def fallback_agri_news():
    today = datetime.now().strftime('%Y-%m-%d')
    return [
        {
            'titre': 'Prix du cacao stables sur le marche ivoirien cette semaine',
            'lien': '#',
            'source': 'BCC - Bourse du Cacao',
            'pays': "Cote d'Ivoire",
            'date': today,
            'description': "Les cours du cacao se maintiennent autour de 3200 FCFA/kg sur la Bourse du Cacao d'Abidjan. La production de la saison 2025/2026 s'annonce prometteuse.",
            'image': '/static/fond_marche.png'
        },
        {
            'titre': 'Campagne agricole 2025/2026 : previsions encourageantes pour le cafe',
            'lien': '#',
            'source': "Ministere de l'Agriculture",
            'pays': "Cote d'Ivoire",
            'date': today,
            'description': "Le ministere annonce une production record de cafe robusta avec plus de 200 000 tonnes attendues.",
            'image': '/static/fond_gaia.png'
        },
        {
            'titre': 'Innovation technologique : drones pour surveillance des plantations',
            'lien': '#',
            'source': 'CommodAfrica',
            'pays': 'Afrique',
            'date': today,
            'description': "Adoption croissante des technologies numeriques dans l'agriculture ivoirienne pour mieux suivre les parcelles.",
            'image': '/static/fond_marche.png'
        }
    ]


def fetch_live_agri_news(limit=6):
    feed_urls = [
        "https://news.google.com/rss/search?q=cacao+Cote+d%27Ivoire+OR+agriculture+Cote+d%27Ivoire&hl=fr&gl=CI&ceid=CI:fr",
        "https://www.fao.org/news/rss-feed/en/"
    ]
    news_items = []
    seen = set()

    for feed_url in feed_urls:
        try:
            response = requests.get(
                feed_url,
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            if response.status_code != 200:
                continue

            root = ET.fromstring(response.content)
            for item in root.findall('.//item'):
                title = (item.findtext('title') or '').strip()
                link = (item.findtext('link') or '').strip()
                pub_date = (item.findtext('pubDate') or '').strip()
                source = (item.findtext('source') or '').strip()
                description_html = item.findtext('description') or ''

                if not title or not link:
                    continue

                key = f'{title}|{link}'
                if key in seen:
                    continue
                seen.add(key)

                # Quick extraction from description first (no extra HTTP call)
                image = extract_first_image(description_html)
                description = clean_html_excerpt(description_html)

                # Try meta extraction if no image found yet (with timeout)
                if not image:
                    try:
                        meta = enrich_article_metadata(link)
                        image = meta.get('image', '')
                        if not description:
                            description = clean_html_excerpt(meta.get('description', ''))
                        if not source:
                            source = meta.get('site_name') or source
                    except Exception:
                        pass

                # Use fallback images if no image found
                if not image:
                    image = '/static/fond_marche.png' if 'cacao' in title.lower() or 'cafe' in title.lower() else '/static/fond_gaia.png'

                if not source:
                    source = urlparse(link).netloc.replace('www.', '').split('.')[0].upper()

                if pub_date:
                    try:
                        pub_date = parsedate_to_datetime(pub_date).strftime('%Y-%m-%d')
                    except Exception:
                        pub_date = datetime.now().strftime('%Y-%m-%d')
                else:
                    pub_date = datetime.now().strftime('%Y-%m-%d')

                pays = "Cote d'Ivoire" if 'ivoire' in f'{title} {description}'.lower() else 'Afrique'

                news_items.append({
                    'titre': title,
                    'lien': link,
                    'source': source,
                    'pays': pays,
                    'date': pub_date,
                    'description': description or 'Actualite agricole en cours de mise a jour.',
                    'image': image
                })

                if len(news_items) >= limit:
                    return news_items
        except Exception:
            continue

    return news_items


# Cached news and background updater to avoid blocking requests
cached_news = fallback_agri_news()
_news_stop_event = Event()

def _news_updater(interval=60):
    global cached_news
    while not _news_stop_event.is_set():
        try:
            news = fetch_live_agri_news(6)
            if news:
                cached_news = news
        except Exception:
            pass
        _news_stop_event.wait(interval)


# Start news updater thread when running the app (handled in __main__)


@app.route('/image_proxy')
def image_proxy():
    url = request.args.get('url', '')
    if not url:
        return ('', 400)

    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return ('', 400)

    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5, stream=True, allow_redirects=True)
        if r.status_code != 200:
            return ('', 502)

        content = r.content
        # Limit size to avoid proxying huge files
        max_size = 5 * 1024 * 1024
        if len(content) > max_size:
            return ('', 413)

        content_type = r.headers.get('Content-Type', 'application/octet-stream')
        resp = Response(content, content_type=content_type)
        resp.cache_control.max_age = 2592000
        resp.cache_control.public = True
        return resp
    except Exception:
        return ('', 502)


@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/login_page')
def login_page():
    remembered_user = get_user_from_remember_cookie()
    return render_template('login.html', remembered_user=remembered_user)


@app.route('/login_process', methods=['POST'])
def login_process():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    user = User.query.filter_by(username=username, password=password).first()
    if not user:
        return jsonify({'success': False, 'message': 'Erreur identifiants'})

    session['user_id'] = user.id
    session['role'] = user.role
    session['nom'] = user.username

    remember_me = bool(data.get('remember_me'))
    response = make_response(jsonify({
        'success': True,
        'role': user.role,
        'redirect_url': get_dashboard_url(user.role)
    }))

    if remember_me:
        response.set_cookie(
            'gaia_remember',
            build_remember_token(user),
            max_age=60 * 60 * 24 * 30,
            httponly=True,
            samesite='Lax'
        )
    else:
        response.set_cookie('gaia_remember', '', expires=0)

    return response


@app.route('/register_process', methods=['POST'])
def register_process():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    nom = (data.get('nom') or '').strip()
    role = (data.get('role') or 'user').strip().lower()
    admin_code = (data.get('admin_code') or '').strip()

    if not nom or not username or not password:
        return jsonify({'success': False, 'message': 'Tous les champs sont obligatoires.'}), 400

    if role not in {'user', 'admin'}:
        return jsonify({'success': False, 'message': 'Type de compte invalide.'}), 400

    if len(username) < 3:
        return jsonify({'success': False, 'message': "L'identifiant doit contenir au moins 3 caracteres."}), 400

    if len(password) < 4:
        return jsonify({'success': False, 'message': 'Le mot de passe doit contenir au moins 4 caracteres.'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Cet identifiant existe deja.'}), 409

    if role == 'admin' and admin_code != app.config['ADMIN_REGISTRATION_CODE']:
        return jsonify({'success': False, 'message': "Code administrateur invalide."}), 403

    user = User(username=username, password=password, nom=nom, role=role)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session['role'] = user.role
    session['nom'] = user.username

    response = make_response(jsonify({
        'success': True,
        'role': user.role,
        'redirect_url': get_dashboard_url(user.role)
    }))
    response.set_cookie('gaia_remember', '', expires=0)
    return response


@app.route('/remember_login', methods=['POST'])
def remember_login():
    user = get_user_from_remember_cookie()
    if not user:
        response = make_response(jsonify({'success': False, 'message': 'Aucune connexion mémorisée.'}), 401)
        response.set_cookie('gaia_remember', '', expires=0)
        return response

    session['user_id'] = user.id
    session['role'] = user.role
    session['nom'] = user.username

    return jsonify({
        'success': True,
        'role': user.role,
        'redirect_url': get_dashboard_url(user.role)
    })


@app.route('/send_message', methods=['POST'])
def send_message():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'message': 'Non authentifie'}), 401

    data = request.json or {}
    dest = data.get('destinataire', 'communaute')
    contenu = (data.get('contenu') or '').strip()

    if not contenu:
        return jsonify({'success': False, 'message': 'Message vide.'}), 400

    media_url = data.get('media_url')
    media_type = data.get('media_type')

    if dest == 'communaute':
        msg = Message(expediteur=current_user.username, destinataire='communaute', contenu=contenu, media_url=media_url, media_type=media_type)
        db.session.add(msg)
        db.session.commit()
        return jsonify({'success': True})

    if dest == 'admin':
        admin = get_primary_admin(exclude_username=current_user.username)
        if not admin:
            return jsonify({'success': False, 'message': 'Aucun administrateur disponible.'}), 404

        msg = Message(expediteur=current_user.username, destinataire=admin.username, contenu=contenu, media_url=media_url, media_type=media_type)
        db.session.add(msg)
        db.session.commit()
        return jsonify({'success': True})

    return jsonify({'success': False, 'message': 'Destination invalide.'}), 400


@app.route('/get_messages')
def get_messages():
    current_user = get_current_user()
    if not current_user:
        return jsonify([])

    dest = request.args.get('destinataire', 'communaute')

    if dest == 'communaute':
        msgs = Message.query.filter_by(destinataire='communaute').order_by(Message.date.asc()).all()
    elif current_user.role == 'user':
        msgs = expert_thread_query_for_user(current_user.username).all()
    else:
        target_username = request.args.get('target_user')
        if not target_username:
            return jsonify([])
        msgs = expert_thread_query_for_admin(target_username).all()

    return jsonify([
        {
            'expediteur': m.expediteur,
            'display_expediteur': resolve_display_username(m.expediteur),
            'destinataire': m.destinataire,
            'contenu': m.contenu,
            'date': m.date.strftime('%Y-%m-%d %H:%M:%S'),
            'media_url': m.media_url,
            'media_type': m.media_type
        }
        for m in msgs
    ])


@app.route('/admin_get_users')
def admin_get_users():
    current_user = get_current_user()
    if not current_user or current_user.role != 'admin':
        return jsonify([]), 403

    results = []
    for user in get_non_admin_users():
        last_message = expert_thread_query_for_admin(user.username).order_by(Message.date.desc()).first()
        results.append({
            'username': user.username,
            'nom': user.nom,
            'role': user.role,
            'last_message': last_message.contenu if last_message else "Aucune conversation pour l'instant.",
            'last_date': last_message.date.strftime('%Y-%m-%d %H:%M:%S') if last_message else ''
        })

    return jsonify(results)


@app.route('/admin_send_message', methods=['POST'])
def admin_send_message():
    current_user = get_current_user()
    if not current_user or current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Acces refuse.'}), 403

    data = request.json or {}
    target_username = (data.get('target_username') or '').strip()
    contenu = (data.get('contenu') or '').strip()
    media_url = data.get('media_url')
    media_type = data.get('media_type')

    if not target_username or not contenu:
        return jsonify({'success': False, 'message': 'Destinataire ou message manquant.'}), 400

    target_user = User.query.filter_by(username=target_username).first()
    if not target_user or target_user.role == 'admin':
        return jsonify({'success': False, 'message': 'Utilisateur introuvable.'}), 404

    msg = Message(expediteur=current_user.username, destinataire=target_username, contenu=contenu, media_url=media_url, media_type=media_type)
    db.session.add(msg)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/get_quick_templates')
def get_quick_templates():
    current_user = get_current_user()
    owner = request.args.get('owner')
    # If owner provided, return owner-specific + global (owner null)
    if owner:
        templates = QuickTemplate.query.filter(or_(QuickTemplate.owner_username == owner, QuickTemplate.owner_username == None)).order_by(QuickTemplate.created_at.desc()).all()
    elif current_user:
        templates = QuickTemplate.query.filter(or_(QuickTemplate.owner_username == current_user.username, QuickTemplate.owner_username == None)).order_by(QuickTemplate.created_at.desc()).all()
    else:
        templates = QuickTemplate.query.filter_by(owner_username=None).order_by(QuickTemplate.created_at.desc()).all()

    return jsonify([{
        'id': t.id,
        'owner_username': t.owner_username,
        'title': t.title,
        'content': t.content,
        'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for t in templates])


@app.route('/create_quick_template', methods=['POST'])
def create_quick_template():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'message': 'Non authentifie'}), 401

    data = request.json or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    owner = data.get('owner_username') or current_user.username

    if not content:
        return jsonify({'success': False, 'message': 'Contenu vide'}), 400

    tpl = QuickTemplate(owner_username=owner, title=title or content[:50], content=content)
    db.session.add(tpl)
    db.session.commit()
    return jsonify({'success': True, 'id': tpl.id})


@app.route('/delete_quick_template', methods=['POST'])
def delete_quick_template():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'message': 'Non authentifie'}), 401

    data = request.json or {}
    tpl_id = data.get('id')
    if not tpl_id:
        return jsonify({'success': False, 'message': 'Id manquant'}), 400

    tpl = QuickTemplate.query.get(tpl_id)
    if not tpl:
        return jsonify({'success': False, 'message': 'Template introuvable'}), 404

    # Only owner or admin can delete
    if tpl.owner_username and tpl.owner_username != current_user.username and current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Acces refuse'}), 403

    db.session.delete(tpl)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/upload_media', methods=['POST'])
def upload_media():
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'message': 'Non authentifie'}), 401

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Aucun fichier'}), 400

    f = request.files['file']
    filename = f.filename or 'upload'
    ext = os.path.splitext(filename)[1]
    # generate safe name
    safe_name = hashlib.sha1((filename + str(datetime.now().timestamp()) + os.urandom(8).hex()).encode()).hexdigest() + ext
    dest_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    f.save(dest_path)
    url_path = f"/static/uploads/{safe_name}"
    # determine media type
    content_type = f.content_type or ''
    media_type = 'image' if content_type.startswith('image') else ('audio' if content_type.startswith('audio') else 'file')
    return jsonify({'success': True, 'url': url_path, 'media_type': media_type})


@app.route('/get_agri_news')
def get_agri_news():
    # Return cached news if available, otherwise fallback
    if cached_news:
        return jsonify(cached_news)
    return jsonify(fallback_agri_news())


@app.route('/get_cacao_data')
def get_cacao_data():
    try:
        cacao_data = get_real_cacao_data()
        if cacao_data:
            return jsonify(cacao_data)

        base_price = 3200
        variation = random.uniform(-100, 100)
        current_price = base_price + variation

        cacao_data = {
            'symbol': 'CACAO-CI',
            'name': "Cacao Cote d'Ivoire",
            'country': "Cote d'Ivoire",
            'current_price': round(current_price, 2),
            'previous_close': round(base_price, 2),
            'change': round(variation, 2),
            'change_percent': round((variation / base_price) * 100, 2),
            'volume': random.randint(100000, 500000),
            'market': "Bourse du Cacao d'Abidjan",
            'last_update': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'trend': 'bullish' if variation > 0 else 'bearish',
            'quality_grades': {
                'grade_1': round(current_price * 1.05, 2),
                'grade_2': round(current_price, 2),
                'grade_3': round(current_price * 0.95, 2)
            },
            'forecast': {
                'short_term': 'Prix stables avec demande mondiale croissante',
                'long_term': 'Croissance attendue grace aux programmes de qualite'
            },
            'indicators': {
                'rsi': round(random.uniform(25, 75), 2),
                'macd': round(random.uniform(-15, 15), 2),
                'moving_avg_50': round(current_price + random.uniform(-30, 30), 2),
                'volatility': round(random.uniform(2, 8), 2)
            },
            'production_stats': {
                'current_season': '2025/2026',
                'estimated_production': '2.2 millions de tonnes',
                'export_target': '85% de la production mondiale'
            },
            'ivory_coast_prices': ivory_coast_price_reference()
        }
        return jsonify(cacao_data)

    except Exception:
        return jsonify({
            'error': 'Service temporairement indisponible',
            'symbol': 'CACAO-CI',
            'current_price': 3200.00,
            'change': 0.00,
            'change_percent': 0.00,
            'last_update': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'country': "Cote d'Ivoire",
            'ivory_coast_prices': ivory_coast_price_reference()
        })


def get_real_cacao_data():
    try:
        yahoo_url = 'https://query1.finance.yahoo.com/v8/finance/chart/CC=F'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(yahoo_url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                result = data['chart']['result'][0]
                if 'meta' in result:
                    meta = result['meta']
                    current_price = meta.get('regularMarketPrice', 3200)
                    current_price_fcfa = (current_price * 600) / 1000

                    return {
                        'symbol': 'CC=F',
                        'name': 'Cacao Futures',
                        'country': "Cote d'Ivoire",
                        'current_price': round(current_price_fcfa, 2),
                        'previous_close': round((meta.get('previousClose', current_price) * 600) / 1000, 2),
                        'change': round(((current_price - meta.get('previousClose', current_price)) * 600) / 1000, 2),
                        'change_percent': round(meta.get('regularMarketChangePercent', 0), 2),
                        'volume': meta.get('regularMarketVolume', 0),
                        'market': 'ICE Futures US',
                        'last_update': datetime.fromtimestamp(
                            meta.get('regularMarketTime', datetime.now().timestamp())
                        ).strftime('%Y-%m-%d %H:%M:%S UTC'),
                        'trend': 'bullish' if current_price > meta.get('previousClose', current_price) else 'bearish',
                        'source': 'Yahoo Finance',
                        'ivory_coast_prices': ivory_coast_price_reference()
                    }
    except Exception as e:
        print(f'Erreur recuperation donnees cacao reelles: {e}')

    return None


@app.route('/user_dashboard')
def user_dashboard():
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('login_page'))
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return render_template('dashboard.html', user=current_user)


@app.route('/admin_dashboard')
def admin_dashboard():
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('login_page'))
    if current_user.role != 'admin':
        return redirect(url_for('user_dashboard'))
    return render_template('admin_dashboard_enhanced.html', user=current_user, admin_display_name=app.config.get('ADMIN_DISPLAY_NAME', 'RELYAS ADMIN'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


# ============ ROUTES RELYAS ADMIN SOC ============

@app.route('/get_dashboard_stats')
@admin_required
def get_dashboard_stats():
    """Statistiques du tableau de bord RELYAS"""
    total_farmers = User.query.filter_by(role='user').count()
    total_drones = DroneFleet.query.count()
    online_drones = DroneFleet.query.filter_by(status='online').count()
    active_alerts = Alert.query.filter_by(activated=True).count()
    critical_alerts = Alert.query.filter_by(activated=True, severity='critical').count()
    
    return jsonify({
        'total_farmers': total_farmers,
        'total_drones': total_drones,
        'online_drones': online_drones,
        'active_alerts': active_alerts,
        'critical_alerts': critical_alerts
    })


@app.route('/get_telemetry_data')
@admin_required
def get_telemetry_data():
    """Récupère les données de télémétrie en temps réel"""
    farmer_username = request.args.get('farmer_username', '')
    
    if farmer_username:
        # Données pour un planteur spécifique
        data = SensorData.query.filter_by(farmer_username=farmer_username).order_by(SensorData.timestamp.desc()).limit(1).first()
        if data:
            return jsonify({
                'drone_id': data.drone_id,
                'humidity': data.humidity,
                'temperature': data.temperature,
                'soil_ph': data.soil_ph,
                'soil_moisture': data.soil_moisture,
                'nitrogen_level': data.nitrogen_level,
                'timestamp': data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })
        return jsonify({}), 404
    
    # Tous les capteurs actifs
    all_data = SensorData.query.order_by(SensorData.timestamp.desc()).limit(50).all()
    return jsonify([{
        'farmer_username': d.farmer_username,
        'drone_id': d.drone_id,
        'humidity': d.humidity,
        'temperature': d.temperature,
        'timestamp': d.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for d in all_data])


@app.route('/get_alerts')
@admin_required
def get_alerts():
    """Récupère toutes les alertes actives"""
    severity_filter = request.args.get('severity', '')
    
    query = Alert.query.filter_by(activated=True)
    if severity_filter:
        query = query.filter_by(severity=severity_filter)
    
    alerts = query.order_by(Alert.created_at.desc()).all()
    
    return jsonify([{
        'id': a.id,
        'alert_type': a.alert_type,
        'severity': a.severity,
        'farmer_username': a.farmer_username,
        'message': a.message,
        'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for a in alerts])


@app.route('/create_alert', methods=['POST'])
@admin_required
def create_alert():
    """Crée une alerte critiquement via RELYAS"""
    data = request.json or {}
    farmer_username = data.get('farmer_username', '').strip()
    alert_type = data.get('alert_type', '').strip()
    severity = data.get('severity', 'high').strip()
    message = data.get('message', '').strip()
    
    if not all([farmer_username, alert_type, message]):
        return jsonify({'success': False, 'message': 'Données manquantes'}), 400
    
    if severity not in ['critical', 'high', 'medium', 'low']:
        return jsonify({'success': False, 'message': 'Niveau de sévérité invalide'}), 400
    
    user = User.query.filter_by(username=farmer_username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Planteur introuvable'}), 404
    
    alert = Alert(
        alert_type=alert_type,
        severity=severity,
        farmer_username=farmer_username,
        message=message,
        data_snapshot=json.dumps({})
    )
    db.session.add(alert)
    db.session.commit()
    
    return jsonify({'success': True, 'alert_id': alert.id})


@app.route('/send_recommendation', methods=['POST'])
@admin_required
def send_recommendation():
    """Envoie une recommandation d'aide à la décision (SAD)"""
    current_user = get_current_user()
    data = request.json or {}
    farmer_username = data.get('farmer_username', '').strip()
    content = data.get('content', '').strip()
    
    if not all([farmer_username, content]):
        return jsonify({'success': False, 'message': 'Données manquantes'}), 400
    
    user = User.query.filter_by(username=farmer_username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Planteur introuvable'}), 404
    
    recommendation = AdminRecommendation(
        admin_username=current_user.username,
        farmer_username=farmer_username,
        content=content,
        based_on_sensor_data=True
    )
    db.session.add(recommendation)
    db.session.commit()
    
    # Envoyer aussi un message direct
    msg = Message(
        expediteur=current_user.username,
        destinataire=farmer_username,
        contenu=f"📋 [RECOMMANDATION] {content}"
    )
    db.session.add(msg)
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/get_fleet_status')
@admin_required
def get_fleet_status():
    """Récupère l'état complet de la flotte de drones"""
    fleet = DroneFleet.query.all()
    
    return jsonify([{
        'drone_id': d.drone_id,
        'farmer_username': d.farmer_username,
        'status': d.status,
        'battery_level': d.battery_level,
        'location': d.location,
        'last_connection': d.last_connection.strftime('%Y-%m-%d %H:%M:%S') if d.last_connection else 'N/A'
    } for d in fleet])


@app.route('/register_drone', methods=['POST'])
def register_drone():
    """Enregistre un nouveau drone (route pour les drones/planteurs)"""
    data = request.json or {}
    drone_id = data.get('drone_id', '').strip()
    farmer_username = data.get('farmer_username', '').strip()
    location = data.get('location', '').strip()
    
    if not all([drone_id, farmer_username]):
        return jsonify({'success': False, 'message': 'Données manquantes'}), 400
    
    user = User.query.filter_by(username=farmer_username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Planteur introuvable'}), 404
    
    existing_drone = DroneFleet.query.filter_by(drone_id=drone_id).first()
    if existing_drone:
        # Mise à jour du drone existant
        existing_drone.status = 'online'
        existing_drone.last_connection = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Drone mis à jour'})
    
    drone = DroneFleet(
        drone_id=drone_id,
        farmer_username=farmer_username,
        status='online',
        battery_level=100.0,
        location=location
    )
    db.session.add(drone)
    db.session.commit()
    
    return jsonify({'success': True, 'drone_id': drone.drone_id})


@app.route('/post_sensor_data', methods=['POST'])
def post_sensor_data():
    """Reçoit les données de télémétrie des drones (POST par les drones)"""
    data = request.json or {}
    drone_id = data.get('drone_id', '').strip()
    farmer_username = data.get('farmer_username', '').strip()
    
    if not all([drone_id, farmer_username]):
        return jsonify({'success': False, 'message': 'Données manquantes'}), 400
    
    sensor_reading = SensorData(
        drone_id=drone_id,
        farmer_username=farmer_username,
        humidity=float(data.get('humidity', 0)),
        temperature=float(data.get('temperature', 0)),
        soil_ph=float(data.get('soil_ph', 0)),
        soil_moisture=float(data.get('soil_moisture', 0)),
        nitrogen_level=float(data.get('nitrogen_level', 0))
    )
    db.session.add(sensor_reading)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Données enregistrées'})


@app.route('/get_farmer_recommendations')
def get_farmer_recommendations():
    """Récupère les recommandations pour un planteur (accessible aux planteurs)"""
    current_user = get_current_user()
    if not current_user or current_user.role != 'user':
        return jsonify([])
    
    recommendations = AdminRecommendation.query.filter_by(
        farmer_username=current_user.username,
        read=False
    ).order_by(AdminRecommendation.created_at.desc()).all()
    
    return jsonify([{
        'id': r.id,
        'admin_username': r.admin_username,
        'content': r.content,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for r in recommendations])


# ============ ROUTES DE GESTION ADMIN ============

@app.route('/get_all_users')
@admin_required
def get_all_users():
    """Récupère tous les utilisateurs (sauf admins) avec statut"""
    users = User.query.filter(User.role != 'admin').all()
    
    results = []
    for user in users:
        latest_telemetry = SensorData.query.filter_by(farmer_username=user.username).order_by(SensorData.timestamp.desc()).first()
        latest_alert = Alert.query.filter_by(farmer_username=user.username).order_by(Alert.created_at.desc()).first()
        
        results.append({
            'username': user.username,
            'nom': user.nom,
            'role': user.role,
            'banned': user.banned,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'last_telemetry': latest_telemetry.timestamp.strftime('%Y-%m-%d %H:%M:%S') if latest_telemetry else 'N/A',
            'has_alerts': latest_alert is not None
        })
    
    return jsonify(results)


@app.route('/ban_user', methods=['POST'])
@admin_required
def ban_user():
    """Bannit un utilisateur"""
    data = request.json or {}
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'success': False, 'message': 'Utilisateur non spécifié'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user or user.role == 'admin':
        return jsonify({'success': False, 'message': 'Utilisateur introuvable'}), 404
    
    user.banned = True
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Utilisateur {username} a été banni'})


@app.route('/unban_user', methods=['POST'])
@admin_required
def unban_user():
    """Débannit un utilisateur"""
    data = request.json or {}
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'success': False, 'message': 'Utilisateur non spécifié'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Utilisateur introuvable'}), 404
    
    user.banned = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Utilisateur {username} a été débanni'})


@app.route('/delete_user', methods=['POST'])
@admin_required
def delete_user():
    """Supprime un utilisateur et ses données associées"""
    data = request.json or {}
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'success': False, 'message': 'Utilisateur non spécifié'}), 400
    
    user = User.query.filter_by(username=username).first()
    if not user or user.role == 'admin':
        return jsonify({'success': False, 'message': 'Utilisateur introuvable'}), 404
    
    # Supprimer les données associées
    Message.query.filter(or_(Message.expediteur == username, Message.destinataire == username)).delete()
    SensorData.query.filter_by(farmer_username=username).delete()
    Alert.query.filter_by(farmer_username=username).delete()
    AdminRecommendation.query.filter_by(farmer_username=username).delete()
    DroneFleet.query.filter_by(farmer_username=username).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'Utilisateur {username} et ses données ont été supprimés'})


@app.route('/generate_ai_advice')
@admin_required
def generate_ai_advice():
    """Génère des conseils basés sur l'IA en analysant les données des capteurs"""
    farmer_username = request.args.get('farmer_username', '').strip()
    
    if not farmer_username:
        return jsonify({'success': False, 'message': 'Planteur non spécifié'}), 400
    
    user = User.query.filter_by(username=farmer_username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Planteur introuvable'}), 404
    
    # Récupérer les dernières données de télémétrie
    latest_data = SensorData.query.filter_by(farmer_username=farmer_username).order_by(SensorData.timestamp.desc()).first()
    
    if not latest_data:
        return jsonify({
            'success': False,
            'message': 'Aucune donnée de télémétrie disponible pour cet utilisateur'
        }), 404
    
    # Analyse IA simple (règles métier)
    advice = generate_smart_advice(latest_data)
    
    return jsonify({
        'success': True,
        'advice': advice,
        'data': {
            'humidity': latest_data.humidity,
            'temperature': latest_data.temperature,
            'soil_ph': latest_data.soil_ph,
            'soil_moisture': latest_data.soil_moisture,
            'nitrogen_level': latest_data.nitrogen_level,
            'timestamp': latest_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
    })


def generate_smart_advice(sensor_data):
    """Génère des conseils intelligents basés sur les données des capteurs"""
    advice_list = []
    
    # Analyse Humidité
    if sensor_data.humidity > 80:
        advice_list.append({
            'type': 'humidity',
            'level': 'high',
            'message': f'⚠️ Humidité très élevée ({sensor_data.humidity}%). Risque de maladies fongiques. Améliorer la ventilation et réduire l\'irrigation.'
        })
    elif sensor_data.humidity < 40:
        advice_list.append({
            'type': 'humidity',
            'level': 'low',
            'message': f'⚠️ Humidité faible ({sensor_data.humidity}%). Risque de stress hydrique. Augmenter l\'irrigation et utiliser du paillis.'
        })
    else:
        advice_list.append({
            'type': 'humidity',
            'level': 'optimal',
            'message': f'✓ Humidité optimale ({sensor_data.humidity}%). Maintenir les pratiques actuelles.'
        })
    
    # Analyse Température
    if sensor_data.temperature > 35:
        advice_list.append({
            'type': 'temperature',
            'level': 'high',
            'message': f'⚠️ Température très élevée ({sensor_data.temperature}°C). Augmenter l\'ombrage et l\'irrigation. Risque de brûlure foliaire.'
        })
    elif sensor_data.temperature < 15:
        advice_list.append({
            'type': 'temperature',
            'level': 'low',
            'message': f'⚠️ Température basse ({sensor_data.temperature}°C). Installer des couvertures de protection. Ralentissement de croissance attendu.'
        })
    else:
        advice_list.append({
            'type': 'temperature',
            'level': 'optimal',
            'message': f'✓ Température idéale ({sensor_data.temperature}°C). Conditions de croissance excellentes.'
        })
    
    # Analyse pH du sol
    if sensor_data.soil_ph < 5.5:
        advice_list.append({
            'type': 'soil_ph',
            'level': 'low',
            'message': f'⚠️ Sol trop acide (pH {sensor_data.soil_ph}). Appliquer de la chaux agricole pour neutraliser.'
        })
    elif sensor_data.soil_ph > 8:
        advice_list.append({
            'type': 'soil_ph',
            'level': 'high',
            'message': f'⚠️ Sol trop alcalin (pH {sensor_data.soil_ph}). Appliquer du soufre agricole pour réduire le pH.'
        })
    else:
        advice_list.append({
            'type': 'soil_ph',
            'level': 'optimal',
            'message': f'✓ pH du sol optimal ({sensor_data.soil_ph}). Absorption nutriments correcte.'
        })
    
    # Analyse Humidité du sol
    if sensor_data.soil_moisture > 85:
        advice_list.append({
            'type': 'soil_moisture',
            'level': 'high',
            'message': f'⚠️ Sol gorgé d\'eau ({sensor_data.soil_moisture}%). Risque de pourriture racinaire. Réduire l\'irrigation immédiatement.'
        })
    elif sensor_data.soil_moisture < 20:
        advice_list.append({
            'type': 'soil_moisture',
            'level': 'low',
            'message': f'⚠️ Sol très sec ({sensor_data.soil_moisture}%). Plantes en stress hydrique. Augmenter l\'irrigation graduellement.'
        })
    else:
        advice_list.append({
            'type': 'soil_moisture',
            'level': 'optimal',
            'message': f'✓ Humidité du sol optimale ({sensor_data.soil_moisture}%). Disponibilité eau adéquate.'
        })
    
    # Analyse Azote
    if sensor_data.nitrogen_level < 30:
        advice_list.append({
            'type': 'nitrogen',
            'level': 'low',
            'message': f'⚠️ Azote insuffisant ({sensor_data.nitrogen_level} mg/kg). Appliquer engrais azoté NPK 15-10-10.'
        })
    elif sensor_data.nitrogen_level > 150:
        advice_list.append({
            'type': 'nitrogen',
            'level': 'high',
            'message': f'⚠️ Excès d\'azote ({sensor_data.nitrogen_level} mg/kg). Risque de croissance excessive. Réduire application engrais.'
        })
    else:
        advice_list.append({
            'type': 'nitrogen',
            'level': 'optimal',
            'message': f'✓ Niveau azote optimal ({sensor_data.nitrogen_level} mg/kg). Croissance équilibrée.'
        })
    
    return advice_list


@app.route('/send_ai_recommendation', methods=['POST'])
@admin_required
def send_ai_recommendation():
    """Envoie une recommandation générée par l'IA au planteur"""
    current_user = get_current_user()
    data = request.json or {}
    farmer_username = data.get('farmer_username', '').strip()
    advice_data = data.get('advice', [])
    
    if not farmer_username or not advice_data:
        return jsonify({'success': False, 'message': 'Données manquantes'}), 400
    
    user = User.query.filter_by(username=farmer_username).first()
    if not user:
        return jsonify({'success': False, 'message': 'Planteur introuvable'}), 404
    
    # Construire le message de recommandation
    recommendation_text = "📋 **RECOMMANDATIONS INTELLIGENTES**\n\n"
    for advice in advice_data:
        recommendation_text += f"{advice['message']}\n"
    
    # Sauvegarder la recommandation
    recommendation = AdminRecommendation(
        admin_username=current_user.username,
        farmer_username=farmer_username,
        content=recommendation_text,
        based_on_sensor_data=True
    )
    db.session.add(recommendation)
    
    # Envoyer aussi comme message
    msg = Message(
        expediteur=current_user.username,
        destinataire=farmer_username,
        contenu=recommendation_text
    )
    db.session.add(msg)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Recommandations envoyées au planteur'})


if __name__ == '__main__':
    init_db()
    # Start background news updater thread
    try:
        t = Thread(target=_news_updater, args=(60,), daemon=True)
        t.start()
    except Exception:
        pass
    app.run(debug=False)
