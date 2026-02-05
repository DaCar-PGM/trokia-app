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
st.set_page_config(page_title="Trokia Ultimate", page_icon="💎", layout="wide")

# --- 1. IA ---
def configurer_ia():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
    except:
        st.error("Manque la clé API !")

def analyser_image(image_pil):
    # Modèles gratuits
    modeles_gratuits = ['gemini-1.5-flash', 'gemini-1.5-flash-latest']
    
    last_error = ""
    for nom_modele in modeles_gratuits:
        try:
            model = genai.GenerativeModel(nom_modele)
            prompt = "Tu es un expert eBay. Analyse cette photo. Donne-moi UNIQUEMENT le titre parfait pour l'annonce (Marque, Modèle exact). Sois précis."
            response = model.generate_content([prompt, image_pil])
            return response.text.strip(), None
        except Exception as e:
            last_error = str(e)
            if "429" in str(e):
                time.sleep(2)
                continue
            continue
            
    return None, f"Erreur IA : {last_error}"

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
        
        # Récupération image (avec sécurité)
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
        
        moyenne = sum(prix) / len(prix) if prix else 0
        return moyenne, img_url
    except: return 0, ""

# --- INTERFACE ---
st.title("💎 Trokia : Prêt à l'emploi")
configurer_ia()
sheet = connecter_sheets()

tab1, tab2 = st.tabs(["🔎 Recherche Manuelle", "📸 Scan Automatique"])

with tab1:
    q = st.text_input("Nom de l'objet")
    if st.button("Estimer 📊"):
        with st.spinner("Analyse du marché..."):
            p, i = analyser_prix_ebay(q)
            st.session_state.res = {'p': p, 'i': i, 'n': q}

with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True)
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f and st.button("Lancer l'IA ✨"):
        img_pil = Image.open(f)
        st.image(img_pil, width=200, caption="Votre photo")
        with st.spinner("🔍 Identification de l'objet..."):
            nom_objet, erreur = analyser_image(img_pil)
            
            if nom_objet:
                st.success(f"Trouvé : {nom_objet}")
                with st.spinner(f"Recherche du prix pour : {nom_objet}"):
                    p, i = analyser_prix_ebay(nom_objet)
                    st.session_state.res = {'p': p, 'i': i, 'n': nom_objet}
            else:
                st.error(f"Erreur IA : {erreur}")

# SECTION RÉSULTAT (Corrigée avec 'Airbag')
if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        # AIRBAG ANTI-PLANTAGE
        if r.get('i') and r['i'].startswith("http"):
            try:
                st.image(r['i'], caption="Référence eBay")
            except:
                st.warning("Image eBay non affichable")
        else:
            st.info("Pas d'image de référence")
    
    with col2:
        st.markdown(f"### 🏷️ {r['n']}")
        st.metric(label="Cote Moyenne (Ventes Réussies)", value=f"{r['p']:.2f} €")
        
        achat = st.number_input("Prix d'achat proposé (€)", min_value=0.0, step=1.0)
        profit = r['p'] - achat
        
        if profit > 0:
            st.success(f"Marge Potentielle : +{profit:.2f} €")
        else:
            st.error(f"Perte Potentielle : {profit:.2f} €")
            
        if st.button("💾 Sauvegarder dans Trokia_DB"):
            if sheet:
                try:
                    sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), r['n'], r['p'], achat, "App V3", r['i']])
                    st.balloons()
                    st.success("Enregistré !")
                except Exception as e:
                    st.error(f"Erreur Sheets : {e}")
            else:
                st.error("Erreur de connexion Google Sheets")
