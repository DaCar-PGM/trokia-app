import streamlit as st
import pandas as pd
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import re
import google.generativeai as genai
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia Vision", page_icon="💎", layout="wide")

# Configuration IA Vision
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')
except:
    st.error("Clé API Gemini manquante dans les Secrets !")

# --- CONNEXION GOOGLE SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Trokia_DB").sheet1
        return sheet
    except Exception as e:
        st.error(f"Erreur Cloud : {e}")
        return None

# --- SCRAPER & TOOLS ---
def configurer_navigateur():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options

def analyser_prix_ebay(recherche):
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=configurer_navigateur())
        url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
        driver.get(url)
        time.sleep(2)
        
        # Image
        image_url = "https://via.placeholder.com/150"
        try:
            img_element = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            image_url = img_element.get_attribute("src")
        except: pass

        # Prix
        texte = driver.find_element(By.TAG_NAME, "body").text
        motifs = re.findall(r"(\d+[\.,]?\d*)\s*EUR", texte)
        prix_liste = [float(p.replace(',', '.')) for p in motifs if 1 < float(p.replace(',', '.')) < 10000]
        driver.quit()
        
        prix_final = sum(prix_liste) / len(prix_liste) if prix_liste else 0
        return prix_final, image_url
    except:
        return 0, "https://via.placeholder.com/150"

# --- INTERFACE ---
st.title("💎 Trokia Ultimate : Vision & Trader")

sheet = connecter_sheets()
if not sheet: st.stop()

tab1, tab2 = st.tabs(["🔍 Scan Texte / Code-barres", "📸 Analyse Photo (IA)"])

# ONGLET 1 : CLASSIQUE
with tab1:
    entree = st.text_input("Nom de l'objet ou Code-barres")
    if st.button("Lancer l'Analyse 🚀"):
        prix, img = analyser_prix_ebay(entree)
        st.session_state.prix = prix
        st.session_state.img = img
        st.session_state.nom = entree

# ONGLET 2 : VISION IA
with tab2:
    st.info("Prenez une photo d'un objet (meuble, déco, vêtement) sans code-barres.")
    photo = st.camera_input("Scanner l'objet")
    
    if photo:
        img_pil = Image.open(photo)
        with st.spinner("L'IA analyse l'objet..."):
            prompt = "Décris cet objet de manière précise pour une recherche de prix sur eBay (marque, modèle, état visible). Réponds uniquement avec le nom de l'objet."
            response = model.generate_content([prompt, img_pil])
            description = response.text
            st.write(f"**IA détecte :** {description}")
            
            with st.spinner("Recherche de la cote..."):
                prix, img = analyser_prix_ebay(description)
                st.session_state.prix = prix
                st.session_state.img = img
                st.session_state.nom = description

# AFFICHAGE DU RESULTAT & SAUVEGARDE
if 'prix' in st.session_state and st.session_state.prix > 0:
    st.divider()
    res1, res2 = st.columns(2)
    with res1:
        st.image(st.session_state.img, width=200)
    with res2:
        st.success(f"Cote Estimée : **{round(st.session_state.prix, 2)} €**")
        p_achat = st.number_input("Prix d'achat (€)", min_value=0.0)
        
        if st.button("💾 Enregistrer dans mon Empire"):
            date = datetime.now().strftime("%d/%m/%Y %H:%M")
            # Sauvegarde Cloud
            sheet.append_row([date, st.session_state.nom, st.session_state.prix, p_achat, "Auto", st.session_state.img])
            st.balloons()
            st.success("Données sécurisées dans Google Sheets !")
