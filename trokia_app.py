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
st.set_page_config(page_title="Trokia Diagnostic", page_icon="🔧", layout="wide")

# --- 1. FONCTION DIAGNOSTIC ---
def lister_modeles_dispos():
    """Demande à Google la liste EXACTE des modèles disponibles pour cette clé."""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        # On récupère tous les modèles qui supportent 'generateContent'
        liste = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                liste.append(m.name)
        return sorted(liste), None
    except Exception as e:
        return [], str(e)

# --- 2. IA ---
def analyser_image_avec_modele(image_pil, nom_modele):
    try:
        model = genai.GenerativeModel(nom_modele)
        response = model.generate_content(["Décris cet objet (Marque, Modèle) pour eBay. Nom court uniquement.", image_pil])
        return response.text.strip(), None
    except Exception as e:
        return None, str(e)

# --- 3. ROBOT EBAY ---
def analyser_prix_ebay(recherche):
    try:
        options = Options()
        options.add_argument("--headless=new") 
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.get("https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1")
        time.sleep(2)
        
        try: img = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img").get_attribute("src")
        except: img = "https://via.placeholder.com/150"

        txt = driver.find_element(By.TAG_NAME, "body").text
        prix = [float(p.replace(',', '.').strip()) for p in re.findall(r"(\d+[\.,]?\d*)\s*EUR", txt) if 1 < float(p.replace(',', '.')) < 5000]
        
        driver.quit()
        return (sum(prix) / len(prix) if prix else 0), img
    except: return 0, ""

# --- 4. CONNEXION SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("Trokia_DB").sheet1
    except: return None

# --- INTERFACE ---
st.title("🔧 Trokia : Mode Diagnostic & Réparation")

# Vérification immédiate des modèles
st.info("🔄 Connexion à Google pour vérifier votre compte...")
modeles_dispos, erreur_liste = lister_modeles_dispos()

if erreur_liste:
    st.error(f"❌ Impossible de lister les modèles : {erreur_liste}")
    choix_modele = None
else:
    st.success(f"✅ {len(modeles_dispos)} modèles trouvés et actifs !")
    # On laisse l'utilisateur choisir le modèle (fini de deviner !)
    choix_modele = st.selectbox("Quel cerveau utiliser ?", modeles_dispos, index=0)

st.divider()

sheet = connecter_sheets()
tab1, tab2 = st.tabs(["Scan Texte", "Scan Photo"])

with tab1:
    q = st.text_input("Objet")
    if st.button("Go 🚀"):
        p, i = analyser_prix_ebay(q)
        st.session_state.res = {'p': p, 'i': i, 'n': q}

with tab2:
    mode = st.radio("Mode", ["Caméra", "Galerie"], horizontal=True)
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f and st.button("Analyser IA ✨"):
        if not choix_modele:
            st.error("Aucun modèle disponible.")
        else:
            img = Image.open(f)
            st.image(img, width=150)
            with st.spinner(f"Analyse avec {choix_modele}..."):
                desc, err = analyser_image_avec_modele(img, choix_modele)
                if desc:
                    st.success(f"Trouvé : {desc}")
                    p, i = analyser_prix_ebay(desc)
                    st.session_state.res = {'p': p, 'i': i, 'n': desc}
                else:
                    st.error(f"Erreur IA : {err}")

if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    c1, c2 = st.columns([1,2])
    c1.image(r['i'])
    with c2:
        st.metric("Prix eBay", f"{r['p']:.2f} €")
        if st.button("Sauvegarder"):
            if sheet:
                sheet.append_row([datetime.now().str(), r['n'], r['p'], 0, "Diag", r['i']])
                st.success("Sauvegardé !")
