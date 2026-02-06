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

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v18.2 : Stealth Intelligence", page_icon="💎", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- 1. MOTEUR IA INVISIBLE (MULTI-MODÈLES) ---
def obtenir_meilleur_modele():
    """Détermine en arrière-plan le meilleur modèle disponible pour la précision"""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Priorité au modèle Pro pour la précision 'Pico Bello'
        for m in ["models/gemini-1.5-pro", "models/gemini-1.5-flash", "models/gemini-pro"]:
            if m in models:
                return m
        return models[0]
    except:
        return "gemini-1.5-flash"

def analyser_objet_expert(image_pil):
    """Analyse profonde en arrière-plan croisant visuel et expertise"""
    default_res = {"nom": "Objet Inconnu", "cat": "AUTRE", "mat": "N/A", "etat": "3", "score": "5"}
    try:
        target_model = obtenir_meilleur_modele()
        model = genai.GenerativeModel(target_model)
        
        # Le prompt est maintenant ultra-directif pour forcer l'IA à croiser ses connaissances
        prompt = (
            "En tant qu'expert en expertise d'objets, analyse cette image. "
            "Identifie précisément la marque, le modèle et les matériaux (ex: chêne massif vs plaqué). "
            "Évalue l'état d'usage et la rareté sur le marché."
            "\nFormat de sortie STRICT : NOM: ... | CAT: ... | MAT: ... | ETAT: ... | SCORE: ..."
        )
        
        response = model.generate_content([prompt, image_pil])
        t = response.text.strip()
        
        res = default_res.copy()
        if "NOM:" in t: res["nom"] = t.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in t: res["cat"] = t.split("CAT:")[1].split("|")[0].strip()
        if "MAT:" in t: res["mat"] = t.split("MAT:")[1].split("|")[0].strip()
        if "ETAT:" in t: res["etat"] = t.split("ETAT:")[1].split("|")[0].strip()
        if "SCORE:" in t: res["score"] = t.split("SCORE:")[1].strip()
        return res
    except:
        return default_res

# --- 2. VISUELS & RECHERCHE ---
def get_thumbnail(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(keywords=query, region="fr-fr", max_results=1))
            return results[0]['image'] if results else "https://via.placeholder.com/150"
    except: return "https://via.placeholder.com/150"

def scan_global_cote(nom):
    try:
        clean = re.sub(r'[^\w\s]', '', nom).strip()
        # eBay (Ventes terminées)
        url_ebay = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url_ebay, headers=HEADERS, timeout=5)
        prices = [float(p.replace(",", ".").replace(" ", "")) for p in re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text) if p]
        
        # Web (LBC/Vinted)
        web_prices = []
        with DDGS() as ddgs:
            results_web = list(ddgs.text(f"site:leboncoin.fr OR site:vinted.fr {nom}", max_results=8))
            for res in results_web:
                p = re.findall(r"(\d+[\.,]?\d*)\s?(?:€|eur)", res.get('body', '').lower())
                if p: web_prices.append(float(p[0].replace(",", ".")))

        total = [p for p in prices + web_prices if 1 < p < 8000]
        cote = statistics.median(total) if total else 0
        liq = "🔥 Très Fluide" if len(total) > 12 else ("❄️ Difficile" if len(total) < 3 else "Moyenne")
        return cote, liq, url_ebay
    except: return 0, "Inconnue", ""

# --- 3. DATA & CONFIG ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(json_str), ["https://spreadsheets.google.com/feeds"])
        return gspread.authorize(creds).open("Trokia_DB").sheet1
    except: return None

# --- 4. INTERFACE ---
if 'objet_a' not in st.session_state: st.session_state.objet_a = None
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

sheet = connecter_sheets()

st.title("💎 Trokia : L'Argus Universel")

tab_photo, tab_manuel, tab_troc = st.tabs(["📸 Scan Photo", "⌨️ Clavier / EAN", "⚖️ Balance d'Échange"])

# --- TAB 1 : PHOTO (IA EXPERTISE SILENCIEUSE) ---
with tab_photo:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        f = st.camera_input("Scanner un produit")
        if not f: f = st.file_uploader("Ou importer", type=['jpg', 'png'])
    
    if f:
        with st.spinner("Analyse approfondie en cours..."):
            data = analyser_objet_expert(Image.open(f))
            cote, liq, url = scan_global_cote(data['nom'])
            st.session_state.last_scan = {"nom": data['nom'], "prix": cote, "img": get_thumbnail(data['nom']), "cat": data['cat']}
            
            with col_r:
                st.header(f"{data['nom']}")
                st.metric("Valeur Marché", f"{cote:.0f} €", delta=liq)
                st.write(f"**Matériaux :** {data['mat']} | **Désirabilité :** {data['score']}/10")
                
                if st.button("⚖️ Utiliser pour un TROC (Slot A)", key="add_a_photo"):
                    st.session_state.objet_a = st.session_state.last_scan
                    st.success("Objet mémorisé.")

# --- TAB 2 : MANUEL ---
with tab_manuel:
    with st.form("manual_search"):
        q_in = st.text_input("Saisir nom ou EAN", placeholder="Ex: Montre Omega ou 314589123456")
        btn_search = st.form_submit_button("🔎 Estimer")
    
    if btn_search and q_in:
        with st.spinner("Calcul de la cote..."):
            cote, liq, url = scan_global_cote(q_in)
            img = get_thumbnail(q_in)
            st.session_state.last_scan = {"nom": q_in, "prix": cote, "img": img, "cat": "MANUEL"}
            
            c1, c2 = st.columns([1, 2])
            c1.image(img, width=150)
            with c2:
                st.subheader(q_in)
                st.metric("Prix Estimé", f"{cote:.0f} €", delta=liq)
                if st.button("⚖️ Utiliser pour un TROC (Slot A)", key="add_a_manual"):
                    st.session_state.objet_a = st.session_state.last_scan
                    st.success("Objet mémorisé.")

# --- TAB 3 : TROC ---
with tab_troc:
    if st.session_state.objet_a:
        obj_a = st.session_state.objet_a
        col_a, col_vs, col_b = st.columns([2, 1, 2])
        
        with col_a:
            st.image(obj_a['img'], width=150)
            st.subheader(obj_a['nom'])
            st.title(f"{obj_a['prix']:.0f} €")
            st.caption("OBJET A")
            
        with col_vs:
            st.title(" 🆚 ")
            
        with col_b:
            if st.session_state.last_scan and st.session_state.last_scan['nom'] != obj_a['nom']:
                obj_b = st.session_state.last_scan
                st.image(obj_b['img'], width=150)
                st.subheader(obj_b['nom'])
                st.title(f"{obj_b['prix']:.0f} €")
                st.caption("OBJET B")
                
                diff = obj_a['prix'] - obj_b['prix']
                if diff > 0: st.error(f"Défavorable : B doit rajouter {abs(diff):.0f}€")
                elif diff < 0: st.success(f"Favorable : Vous gagnez {abs(diff):.0f}€")
                else: st.info("Équitable")
            else:
                st.write("Scannez un second objet.")
        
        if st.button("🗑️ Reset Troc"):
            st.session_state.objet_a = None
            st.rerun()
    else:
        st.info("Sélectionnez un premier objet pour la balance.")

# --- SAUVEGARDE ---
st.divider()
if st.session_state.last_scan:
    if st.button("💾 Enregistrer dans le Cloud"):
        if sheet:
            ls = st.session_state.last_scan
            sheet.append_row([datetime.now().strftime("%d/%m %H:%M"), ls['nom'], ls['prix'], ls['cat'], ls['img']])
            st.success("Synchronisé !")
