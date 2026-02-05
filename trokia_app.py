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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia Ultimate v3.3", page_icon="💎", layout="wide")

# --- 1. IA (AUTO-SÉLECTION) ---
def configurer_et_trouver_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        # On demande la liste officielle
        liste_modeles = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                liste_modeles.append(m.name)
        
        # Logique de sélection : Flash > Pro > Vision
        modele_choisi = next((m for m in liste_modeles if "flash" in m.lower() and "1.5" in m), None)
        if not modele_choisi:
            modele_choisi = next((m for m in liste_modeles if "pro" in m.lower() and "1.5" in m), None)
        if not modele_choisi:
            modele_choisi = next((m for m in liste_modeles if "vision" in m.lower()), None)
        if not modele_choisi and liste_modeles:
            modele_choisi = liste_modeles[0]
            
        return modele_choisi
    except Exception as e:
        st.error(f"Erreur connexion Google : {e}")
        return None

def analyser_image(image_pil, nom_modele_exact):
    try:
        model = genai.GenerativeModel(nom_modele_exact)
        prompt = "Tu es un expert eBay. Analyse cette photo. Donne-moi UNIQUEMENT le titre court (Marque, Modèle) pour la vente. Pas de phrase."
        response = model.generate_content([prompt, image_pil])
        return response.text.strip(), None
    except Exception as e:
        if "429" in str(e): return None, "Quota dépassé (Attendre 1 min)"
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

# --- 3. SCRAPING PRIX (AMÉLIORÉ) ---
def get_driver():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def analyser_prix_ebay(recherche):
    try:
        driver = get_driver()
        # Recherche précise : Ventes réussies uniquement
        url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
        driver.get(url)
        time.sleep(2)
        
        # Récupération image miniature
        img_url = ""
        try: 
            element = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            img_url = element.get_attribute("src")
        except: pass

        # --- NOUVEAU SYSTÈME DE PRIX ---
        txt = driver.find_element(By.TAG_NAME, "body").text
        
        # Regex qui capture "120,50 EUR" ET "EUR 120,50" ET "120,50 €"
        # On cherche tous les nombres autour des mots clés monétaires
        raw_prices = re.findall(r"(?:EUR|€)\s*([\d\.,]+)|([\d\.,]+)\s*(?:EUR|€)", txt)
        
        prix_propres = []
        for p in raw_prices:
            # raw_prices renvoie des tuples ('', '120,50') ou ('120,50', '')
            val_str = p[0] if p[0] else p[1]
            try:
                # On remplace la virgule par un point pour le calcul
                val = float(val_str.replace(',', '.').strip())
                # Filtre anti-bug (pas de prix à 0€ ou 1 million)
                if 5 < val < 3000: 
                    prix_propres.append(val)
            except: continue
        
        driver.quit()
        
        # Calcul de la moyenne
        nb_trouves = len(prix_propres)
        moyenne = sum(prix_propres) / nb_trouves if nb_trouves > 0 else 0
        
        return moyenne, img_url, nb_trouves
        
    except: return 0, "", 0

# --- INTERFACE ---
st.title("💎 Trokia : Automatique")

if 'modele_ia' not in st.session_state:
    with st.spinner("Connexion au cerveau IA..."):
        st.session_state.modele_ia = configurer_et_trouver_modele()

if st.session_state.modele_ia:
    st.caption(f"✅ IA Connectée : `{st.session_state.modele_ia}`")
else:
    st.error("❌ Erreur IA. Relancez l'app.")
    st.stop()

sheet = connecter_sheets()

tab1, tab2 = st.tabs(["🔎 Recherche", "📸 Scan Photo"])

with tab1:
    q = st.text_input("Objet")
    if st.button("Estimer"):
        with st.spinner("Analyse..."):
            p, i, n = analyser_prix_ebay(q)
            st.session_state.res = {'p': p, 'i': i, 'n': q, 'count': n}

with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f and st.button("Analyser IA ✨"):
        img = Image.open(f)
        st.image(img, width=200)
        with st.spinner("Identification & Estimation..."):
            nom, err = analyser_image(img, st.session_state.modele_ia)
            if nom:
                st.success(f"Trouvé : {nom}")
                p, i, n = analyser_prix_ebay(nom)
                st.session_state.res = {'p': p, 'i': i, 'n': nom, 'count': n}
            else:
                st.error(f"Erreur : {err}")

# RÉSULTATS
if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    c1, c2 = st.columns([1, 2])
    with c1:
        if r.get('i') and r['i'].startswith("http"):
            try: st.image(r['i'], caption="Réf eBay")
            except: st.warning("Img indispo")
    with c2:
        st.markdown(f"### {r['n']}")
        if r['p'] > 0:
            st.metric("Cote Moyenne", f"{r['p']:.2f} €", delta=f"{r['count']} ventes analysées")
        else:
            st.warning("⚠️ Aucun prix trouvé (Objet trop rare ou mal nommé ?)")
            st.metric("Cote", "0.00 €")
            
        achat = st.number_input("Achat (€)", 0.0)
        if st.button("Sauvegarder"):
            if sheet:
                sheet.append_row([datetime.now().strftime("%Y-%m-%d"), r['n'], r['p'], achat, "Auto V3.3", r['i']])
                st.success("Sauvegardé !")
