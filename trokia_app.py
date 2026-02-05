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

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v6.0 : Light & Fast", page_icon="⚡", layout="wide")

# --- 1. IA (AUTO-SÉLECTION) ---
def configurer_et_trouver_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Flash > Pro > Vision
        choix = next((m for m in all_models if "flash" in m.lower() and "1.5" in m), None)
        if not choix: choix = next((m for m in all_models if "pro" in m.lower() and "1.5" in m), None)
        if not choix: choix = next((m for m in all_models if "vision" in m.lower()), None)
        if not choix and all_models: choix = all_models[0]  
        return choix
    except: return None

def analyser_image(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        # Prompt strict
        prompt = "Analyse cette image pour eBay. Donne-moi UNIQUEMENT : Marque et Modèle. Ex: 'Burton Moto Boots'. Pas de couleur, pas de blabla."
        response = model.generate_content([prompt, image_pil])
        return response.text.strip(), None
    except Exception as e:
        if "429" in str(e): return None, "Quota IA saturé. Pause de 1 min requise."
        return None, str(e)

# --- 2. GOOGLE SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("Trokia_DB").sheet1
    except: return None

# --- 3. SCRAPING "REQUESTS" (LÉGER & DISCRET) ---
def analyser_prix_ebay(recherche):
    try:
        # Nettoyage
        termes = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={termes.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        
        # En-têtes pour ressembler à un navigateur normal
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
        }

        # Requête directe (pas de navigateur ouvert = moins détectable)
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return 0, "", 0, url

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extraction des prix
        prix_collectes = []
        
        # Méthode 1 : Classes CSS eBay
        items = soup.select('.s-item__price')
        for item in items:
            txt = item.get_text()
            # Nettoyage "120,50 EUR"
            vals = re.findall(r"[\d\.,]+", txt)
            for v in vals:
                try:
                    v_clean = float(v.replace(".", "").replace(",", "."))
                    if 5 < v_clean < 5000: prix_collectes.append(v_clean)
                except: continue
        
        # Méthode 2 : Regex brute sur tout le texte si CSS échoue
        if not prix_collectes:
            raw_prices = re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", response.text)
            for p in raw_prices:
                val_text = p[0] if p[0] else p[1]
                try:
                    clean = val_text.replace(" ", "").replace("\u202f", "").replace(",", ".")
                    val = float(clean)
                    if 5 < val < 5000: prix_collectes.append(val)
                except: continue

        # Image (Première image trouvée)
        img_url = ""
        try:
            img_tag = soup.select_one('.s-item__image-wrapper img')
            if img_tag: img_url = img_tag.get('src')
        except: pass

        nb = len(prix_collectes)
        moyenne = sum(prix_collectes) / nb if nb > 0 else 0
        
        return moyenne, img_url, nb, url

    except Exception as e:
        print(f"Erreur: {e}")
        return 0, "", 0, "https://www.ebay.fr"

# --- INTERFACE ---
st.title("💎 Trokia v6.0 : Light Mode")

if 'modele_ia' not in st.session_state:
    with st.spinner("Connexion IA..."):
        st.session_state.modele_ia = configurer_et_trouver_modele()

if not st.session_state.modele_ia:
    st.error("❌ Erreur IA")
    st.stop()
else:
    st.caption(f"🧠 Cerveau : {st.session_state.modele_ia}")

sheet = connecter_sheets()

tab1, tab2 = st.tabs(["🔎 Recherche", "📸 Scanner"])

with tab1:
    q = st.text_input("Objet")
    if st.button("Estimer"):
        with st.spinner("Recherche rapide..."):
            p, i, n, u = analyser_prix_ebay(q)
            st.session_state.res = {'p': p, 'i': i, 'n': q, 'c': n, 'u': u}

with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f and st.button("Lancer 🚀"):
        img = Image.open(f)
        st.image(img, width=200)
        with st.spinner("Analyse..."):
            nom, err = analyser_image(img, st.session_state.modele_ia)
            if nom:
                st.success(f"Objet : {nom}")
                p, i, n, u = analyser_prix_ebay(nom)
                st.session_state.res = {'p': p, 'i': i, 'n': nom, 'c': n, 'u': u}
            else:
                st.error(f"Erreur IA: {err}")

# RÉSULTATS
if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    c1, c2 = st.columns([1, 2])
    with c1:
        if r.get('i') and r['i'].startswith("http"):
            try: st.image(r['i'], width=150)
            except: st.warning("Image protégée")
    with c2:
        st.markdown(f"### {r['n']}")
        
        if r['p'] > 0:
            st.metric("Cote Moyenne", f"{r['p']:.2f} €", delta=f"{r['c']} résultats")
            st.link_button("Vérifier sur eBay", r['u'])
            val_default = float(r['p'])
        else:
            st.warning("⚠️ Prix non accessible automatiquement.")
            st.info("Le robot a été bloqué, mais l'IA a fait le travail d'identification.")
            st.link_button("🔎 Voir la cote manuellement", r['u'])
            val_default = 0.0
        
        # SAISIE MANUELLE OBLIGATOIRE SI 0€
        prix_estime_final = st.number_input("Cote Retenue (€)", value=val_default, step=1.0)
        achat = st.number_input("Prix Achat (€)", 0.0, step=1.0)
        
        if st.button("💾 Enregistrer"):
            if sheet:
                sheet.append_row([datetime.now().strftime("%d/%m/%Y"), r['n'], prix_estime_final, achat, "Trokia v6", r['i']])
                st.success("Sauvegardé !")
