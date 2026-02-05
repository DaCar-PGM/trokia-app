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
st.set_page_config(page_title="Trokia Ultimate Auto", page_icon="💎", layout="wide")

# --- 1. INTELLIGENCE ARTIFICIELLE (AUTO-SÉLECTION) ---
def configurer_et_trouver_modele():
    """Configure l'API et trouve le meilleur modèle DISPONIBLE dans la liste."""
    try:
        # 1. Configuration
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        # 2. On demande la liste officielle à Google (comme dans le mode diagnostic)
        liste_modeles = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                liste_modeles.append(m.name)
        
        # 3. On cherche le meilleur modèle automatiquement
        # On préfère le Flash (rapide/gratuit), sinon le Pro, sinon le premier qui vient
        modele_choisi = None
        
        # Recherche prioritaire : Flash
        for m in liste_modeles:
            if "flash" in m.lower() and "1.5" in m:
                modele_choisi = m
                break
        
        # Si pas trouvé, recherche : Pro 1.5
        if not modele_choisi:
            for m in liste_modeles:
                if "pro" in m.lower() and "1.5" in m:
                    modele_choisi = m
                    break
                    
        # Si toujours rien, on prend le vision (vieux mais fiable)
        if not modele_choisi:
            for m in liste_modeles:
                if "vision" in m.lower():
                    modele_choisi = m
                    break
        
        # Secours ultime : le premier de la liste
        if not modele_choisi and liste_modeles:
            modele_choisi = liste_modeles[0]
            
        return modele_choisi
        
    except Exception as e:
        st.error(f"Erreur de connexion Google : {e}")
        return None

def analyser_image(image_pil, nom_modele_exact):
    try:
        # On utilise le nom EXACT fourni par la liste de Google
        model = genai.GenerativeModel(nom_modele_exact)
        
        prompt = "Tu es un expert eBay. Analyse cette photo. Donne-moi UNIQUEMENT le titre parfait pour l'annonce (Marque, Modèle exact). Sois précis."
        response = model.generate_content([prompt, image_pil])
        return response.text.strip(), None
    except Exception as e:
        if "429" in str(e):
            return None, "Quota dépassé (Trop de demandes). Attends 1 minute."
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

# --- 3. SCRAPING PRIX ---
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
        url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
        driver.get(url)
        time.sleep(2)
        
        img_url = ""
        try: 
            element = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            img_url = element.get_attribute("src")
        except: pass

        txt = driver.find_element(By.TAG_NAME, "body").text
        prix = []
        for p in re.findall(r"(\d+[\.,]?\d*)\s*EUR", txt):
            val = float(p.replace(',', '.').strip())
            if 1 < val < 5000: prix.append(val)
        
        driver.quit()
        return (sum(prix) / len(prix) if prix else 0), img_url
    except: return 0, ""

# --- INTERFACE ---
st.title("💎 Trokia : Automatique")

# Initialisation intelligente
if 'modele_ia' not in st.session_state:
    with st.spinner("Configuration de l'IA..."):
        st.session_state.modele_ia = configurer_et_trouver_modele()

if st.session_state.modele_ia:
    st.caption(f"✅ Connecté au cerveau : `{st.session_state.modele_ia}`")
else:
    st.error("❌ Impossible de trouver un modèle IA disponible.")
    st.stop()

sheet = connecter_sheets()

tab1, tab2 = st.tabs(["🔎 Recherche", "📸 Scan Photo"])

with tab1:
    q = st.text_input("Objet")
    if st.button("Estimer"):
        with st.spinner("Analyse..."):
            p, i = analyser_prix_ebay(q)
            st.session_state.res = {'p': p, 'i': i, 'n': q}

with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True)
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f and st.button("Analyser IA ✨"):
        img = Image.open(f)
        st.image(img, width=200)
        with st.spinner("Identification..."):
            # On passe le modèle qui a été trouvé automatiquement
            nom, err = analyser_image(img, st.session_state.modele_ia)
            if nom:
                st.success(f"Trouvé : {nom}")
                p, i = analyser_prix_ebay(nom)
                st.session_state.res = {'p': p, 'i': i, 'n': nom}
            else:
                st.error(f"Erreur : {err}")

# RÉSULTATS (AVEC PROTECTION IMAGE)
if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    c1, c2 = st.columns([1, 2])
    with c1:
        # Protection contre l'erreur d'image qui t'a bloqué
        if r.get('i') and r['i'].startswith("http"):
            try: st.image(r['i'], caption="Réf eBay")
            except: st.warning("Img non dispo")
    with c2:
        st.markdown(f"### {r['n']}")
        st.metric("Cote Moyenne", f"{r['p']:.2f} €")
        if st.button("Sauvegarder"):
            if sheet:
                sheet.append_row([datetime.now().strftime("%Y-%m-%d"), r['n'], r['p'], 0, "Auto", r['i']])
                st.success("Sauvegardé !")
