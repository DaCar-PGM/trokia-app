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

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v18.4 : Anti-Blocage", page_icon="💎", layout="wide")

# Liste de User-Agents pour simuler différents navigateurs et éviter le blocage
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

# --- 1. MOTEUR IA FURTIF ---
def obtenir_meilleur_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        for m in ["models/gemini-1.5-pro", "models/gemini-1.5-flash"]:
            if m in models: return m
        return models[0]
    except: return "gemini-1.5-flash"

def analyser_objet_expert(image_pil):
    default_res = {"nom": "Objet Inconnu", "cat": "AUTRE", "mat": "N/A", "etat": "3", "score": "5"}
    try:
        model = genai.GenerativeModel(obtenir_meilleur_modele())
        prompt = (
            "En tant qu'expert, analyse cette image. Identifie la marque et le modèle exacts. "
            "Sois précis sur les matériaux. Format STRICT : NOM: ... | CAT: ... | MAT: ... | ETAT: ... | SCORE: ..."
        )
        response = model.generate_content([prompt, image_pil])
        t = response.text.strip()
        res = default_res.copy()
        if "NOM:" in t: res["nom"] = t.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in t: res["cat"] = t.split("CAT:")[1].split("|")[0].strip()
        if "MAT:" in t: res["mat"] = t.split("MAT:")[1].split("|")[0].strip()
        return res
    except: return default_res

# --- 2. MOTEUR DE PRIX RENFORCÉ (CIBLE LES CLASSES CSS) ---
def clean_price(val_str):
    if not val_str: return None
    # Enlève tout sauf les chiffres, les points et les virgules
    val_str = re.sub(r'[^\d,\.]', '', val_str)
    try:
        return float(val_str.replace(",", "."))
    except: return None

def scan_global_cote(nom):
    prices = []
    try:
        clean_name = re.sub(r'[^\w\s]', '', nom).strip()
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        
        # --- TEST EBAY VENTES TERMINÉES ---
        url_ebay = f"https://www.ebay.fr/sch/i.html?_nkw={clean_name.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url_ebay, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # On cherche les balises de prix spécifiques d'eBay
        ebay_tags = soup.select('.s-item__price')
        for tag in ebay_tags:
            p = clean_price(tag.get_text())
            if p and 1 < p < 10000: prices.append(p)

        # --- TEST WEB (DUCKDUCKGO) ---
        with DDGS() as ddgs:
            results = list(ddgs.text(f"prix vendu {nom} leboncoin vinted", max_results=15))
            for res in results:
                # Cherche des motifs de prix dans le texte (ex: 45€, 45,00 EUR)
                found = re.findall(r"(\d+[\s\.,]?\d*)\s?(?:€|eur)", res.get('body', '').lower())
                for f in found:
                    p = clean_price(f)
                    if p and 1 < p < 10000: prices.append(p)

        cote = statistics.median(prices) if prices else 0
        liq = "🔥 Élevée" if len(prices) > 10 else ("❄️ Faible" if len(prices) < 3 else "Moyenne")
        return cote, liq, url_ebay
    except Exception as e:
        return 0, f"Erreur: {str(e)[:20]}", ""

def get_thumbnail(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(keywords=query, region="fr-fr", max_results=1))
            return results[0]['image'] if results else "https://via.placeholder.com/150"
    except: return "https://via.placeholder.com/150"

# --- 3. LOGIQUE APP & RESET ---
if 'objet_a' not in st.session_state: st.session_state.objet_a = None
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

def reset_all():
    st.session_state.objet_a = None
    st.session_state.last_scan = None
    st.rerun()

# --- 4. INTERFACE ---
st.title("💎 Trokia : L'Argus Universel")

if st.button("🔄 Remise à zéro complète", use_container_width=True):
    reset_all()

tab_photo, tab_manuel, tab_troc = st.tabs(["📸 Scan Photo", "⌨️ Clavier / EAN", "⚖️ Balance d'Échange"])

# --- TAB 1 : PHOTO ---
with tab_photo:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        f = st.camera_input("Scanner un produit")
        if not f: f = st.file_uploader("Ou importer", type=['jpg', 'png', 'jpeg'])
    
    if f:
        with st.spinner("Analyse et recherche de prix..."):
            data = analyser_objet_expert(Image.open(f))
            cote, liq, url = scan_global_cote(data['nom'])
            
            # Stockage
            st.session_state.last_scan = {
                "nom": data['nom'], 
                "prix": cote, 
                "img": get_thumbnail(data['nom']),
                "mat": data['mat']
            }
            
            with col_r:
                st.header(f"{data['nom']}")
                if cote > 0:
                    st.metric("Valeur Estimée", f"{cote:.0f} €", delta=f"Liquidité: {liq}")
                else:
                    st.warning("⚠️ Prix non trouvé automatiquement. Essayez l'onglet 'Clavier' avec un nom plus simple.")
                
                st.write(f"**Matériaux :** {data['mat']}")
                
                if st.button("⚖️ Ajouter au TROC (Slot A)", key="add_photo"):
                    st.session_state.objet_a = st.session_state.last_scan
                    st.success("C'est mémorisé !")

# --- TAB 2 : MANUEL ---
with tab_manuel:
    with st.form("manual_form"):
        q_in = st.text_input("Saisir nom ou Code-Barre", placeholder="Ex: Nitro Anthem 2023")
        btn_search = st.form_submit_button("🔎 Estimer la valeur")
    
    if btn_search and q_in:
        with st.spinner("Recherche sur le web..."):
            cote, liq, url = scan_global_cote(q_in)
            img = get_thumbnail(q_in)
            st.session_state.last_scan = {"nom": q_in, "prix": cote, "img": img, "mat": "Manuel"}
            
            c1, c2 = st.columns([1, 2])
            c1.image(img, width=150)
            with c2:
                st.subheader(q_in)
                if cote > 0:
                    st.metric("Valeur Marché", f"{cote:.0f} €", delta=liq)
                else:
                    st.error("Aucun prix trouvé pour cette recherche.")
                
                if st.button("⚖️ Ajouter au TROC (Slot A)", key="add_manual"):
                    st.session_state.objet_a = st.session_state.last_scan
                    st.success("Mémorisé !")

# --- TAB 3 : TROC ---
with tab_troc:
    if st.session_state.objet_a:
        obj_a = st.session_state.objet_a
        col_a, col_vs, col_b = st.columns([2, 1, 2])
        with col_a:
            st.image(obj_a['img'], width=150)
            st.subheader(obj_a['nom'])
            st.title(f"{obj_a['prix']:.0f} €")
        with col_vs: st.title(" 🆚 ")
        with col_b:
            if st.session_state.last_scan and st.session_state.last_scan['nom'] != obj_a['nom']:
                obj_b = st.session_state.last_scan
                st.image(obj_b['img'], width=150)
                st.subheader(obj_b['nom'])
                st.title(f"{obj_b['prix']:.0f} €")
                
                diff = obj_a['prix'] - obj_b['prix']
                if diff > 0: st.error(f"L'autre doit rajouter {abs(diff):.0f}€")
                elif diff < 0: st.success(f"Vous gagnez {abs(diff):.0f}€")
                else: st.info("Échange équitable")
            else: st.write("Scannez un second objet.")
