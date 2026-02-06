import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import re
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import statistics
import random

# --- CONFIGURATION PRO ---
st.set_page_config(page_title="Trokia v18.5 : Argus Pro", page_icon="⚖️", layout="wide")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]

# --- 1. MOTEUR IA FURTIF (MULTI-MODÈLES) ---
def obtenir_meilleur_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Priorité au modèle Pro pour une expertise chirurgicale
        for m in ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]:
            if m in models: return m
        return models[0]
    except: return "gemini-1.5-flash"

def analyser_objet_expert(image_pil):
    default_res = {"nom": "Objet Inconnu", "cat": "AUTRE", "mat": "N/A", "etat": "3", "score": "5"}
    try:
        model = genai.GenerativeModel(obtenir_meilleur_modele())
        prompt = (
            "En tant qu'expert d'Argus, analyse cette image. Identifie marque et modèle exact. "
            "Détaille les matériaux (ex: bois massif, métal brossé). Évalue l'état d'usage (1-5)."
            "\nFormat STRICT : NOM: ... | CAT: ... | MAT: ... | ETAT: ... | SCORE: ..."
        )
        response = model.generate_content([prompt, image_pil])
        t = response.text.strip()
        res = default_res.copy()
        if "NOM:" in t: res["nom"] = t.split("NOM:")[1].split("|")[0].strip()
        if "MAT:" in t: res["mat"] = t.split("MAT:")[1].split("|")[0].strip()
        if "ETAT:" in t: res["etat"] = t.split("ETAT:")[1].split("|")[0].strip()
        return res
    except: return default_res

# --- 2. MOTEUR DE PRIX (VENDUS + WEB) ---
def clean_price(val_str):
    if not val_str: return None
    val_str = re.sub(r'[^\d,\.]', '', val_str)
    try: return float(val_str.replace(",", "."))
    except: return None

def scan_global_cote(nom):
    prices = []
    try:
        clean_name = re.sub(r'[^\w\s]', '', nom).strip()
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        
        # EBAY VENDUS (La base de la cote)
        url_ebay = f"https://www.ebay.fr/sch/i.html?_nkw={clean_name.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url_ebay, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup.select('.s-item__price'):
            p = clean_price(tag.get_text())
            if p and 1 < p < 10000: prices.append(p)

        # WEB GLOBAL (Tendances)
        with DDGS() as ddgs:
            results = list(ddgs.text(f"prix vendu {nom} leboncoin vinted", max_results=10))
            for res in results:
                found = re.findall(r"(\d+[\s\.,]?\d*)\s?(?:€|eur)", res.get('body', '').lower())
                for f in found:
                    p = clean_price(f)
                    if p and 1 < p < 10000: prices.append(p)

        cote = statistics.median(prices) if prices else 0
        liq = "🔥 Élevée" if len(prices) > 12 else "Moyenne"
        return cote, liq
    except: return 0, "Inconnue"

def get_thumbnail(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(keywords=query, region="fr-fr", max_results=1))
            return results[0]['image'] if results else "https://via.placeholder.com/150"
    except: return "https://via.placeholder.com/150"

# --- 3. UI & LOGIQUE ---
if 'objet_a' not in st.session_state: st.session_state.objet_a = None
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

st.title("⚖️ Trokia Pro : L'Argus Universel")

if st.button("🔄 Remise à zéro complète", use_container_width=True):
    st.session_state.objet_a = None
    st.session_state.last_scan = None
    st.rerun()

tab_photo, tab_manuel, tab_troc = st.tabs(["📸 Scan Photo", "⌨️ Clavier / EAN", "⚖️ Balance d'Échange"])

with tab_photo:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        f = st.camera_input("Scanner")
        if not f: f = st.file_uploader("Importer", type=['jpg', 'png', 'jpeg'])
    
    if f:
        with st.spinner("Analyse experte en cours..."):
            data = analyser_objet_expert(Image.open(f))
            cote, liq = scan_global_cote(data['nom'])
            st.session_state.last_scan = {"nom": data['nom'], "prix": cote, "img": get_thumbnail(data['nom']), "mat": data['mat']}
            
            with col_r:
                st.header(data['nom'])
                st.metric("Valeur Argus", f"{cote:.0f} €", delta=f"Liquidité: {liq}")
                st.write(f"**Matériaux :** {data['mat']}")
                if st.button("⚖️ Ajouter au TROC (Slot A)", key="a_ph"):
                    st.session_state.objet_a = st.session_state.last_scan
                    st.success("Mémorisé !")

with tab_manuel:
    with st.form("man"):
        q_in = st.text_input("Nom ou Code-Barre")
        if st.form_submit_button("🔎 Estimer"):
            with st.spinner("Calcul..."):
                cote, liq = scan_global_cote(q_in)
                st.session_state.last_scan = {"nom": q_in, "prix": cote, "img": get_thumbnail(q_in), "mat": "Manuel"}
                st.metric("Prix Marché", f"{cote:.0f} €")
                if st.button("⚖️ Ajouter au TROC (Slot A)", key="a_man"):
                    st.session_state.objet_a = st.session_state.last_scan

with tab_troc:
    if st.session_state.objet_a:
        obj_a = st.session_state.objet_a
        col_a, col_vs, col_b = st.columns([2, 1, 2])
        with col_a:
            st.image(obj_a['img'], width=150)
            st.subheader(obj_a['nom']); st.title(f"{obj_a['prix']:.0f} €")
        with col_vs: st.title(" 🆚 ")
        with col_b:
            if st.session_state.last_scan and st.session_state.last_scan['nom'] != obj_a['nom']:
                obj_b = st.session_state.last_scan
                st.image(obj_b['img'], width=150)
                st.subheader(obj_b['nom']); st.title(f"{obj_b['prix']:.0f} €")
                diff = obj_a['prix'] - obj_b['prix']
                if diff > 0: st.error(f"Rajout de {abs(diff):.0f}€ pour B")
                else: st.success(f"Gain de {abs(diff):.0f}€")
            else: st.write("Scannez le second objet.")
