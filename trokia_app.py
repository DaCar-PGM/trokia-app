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

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Trokia Ultimate v2.1", page_icon="💎", layout="wide")

# --- 2. INTELLIGENCE ARTIFICIELLE ---
def configurer_ia():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        return False

def analyser_image_detective(image_pil):
    """Tente un modèle et renvoie l'erreur exacte si ça échoue."""
    # On tente le modèle le plus robuste d'abord
    nom_modele = 'gemini-pro-vision'
    prompt = "Tu es un expert brocanteur. Analyse cette image et donne-moi UNIQUEMENT : la Marque, le Modèle et le type d'objet. Sois précis pour une recherche eBay."

    try:
        model = genai.GenerativeModel(nom_modele)
        response = model.generate_content([prompt, image_pil])
        return response.text.strip(), None # Succès, pas d'erreur
    except Exception as e:
        # On renvoie l'erreur exacte pour l'afficher
        return None, str(e)

# --- 3. CONNEXION GOOGLE SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Trokia_DB").sheet1
        return sheet
    except:
        return None

# --- 4. ROBOT PRIX ---
def get_driver():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def analyser_prix_ebay(recherche):
    driver = None
    try:
        driver = get_driver()
        url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
        driver.get(url)
        time.sleep(2)
        
        image_url = "https://via.placeholder.com/150?text=No+Image"
        try:
            img_element = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            src = img_element.get_attribute("src")
            if src: image_url = src
        except: pass

        texte = driver.find_element(By.TAG_NAME, "body").text
        motifs = re.findall(r"(\d+[\.,]?\d*)\s*EUR", texte)
        
        prix_liste = []
        for p in motifs:
            try:
                val = float(p.replace(',', '.').strip())
                if 1 < val < 5000: prix_liste.append(val)
            except: continue
        
        prix_final = sum(prix_liste) / len(prix_liste) if prix_liste else 0
        return prix_final, image_url
    except:
        return 0, "https://via.placeholder.com/150"
    finally:
        if driver: driver.quit()

# --- 5. INTERFACE ---
st.title("💎 Trokia : Mode Détective 🕵️‍♂️")

sheet = connecter_sheets()
ia_ok = configurer_ia()

tab1, tab2 = st.tabs(["TEXTE", "PHOTO (IA)"])

with tab1:
    q = st.text_input("Recherche manuelle")
    if st.button("Chercher 🔎") and q:
        with st.spinner("Scraping eBay..."):
            p, i = analyser_prix_ebay(q)
            st.session_state.res = {'prix': p, 'img': i, 'nom': q}

with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    if mode == "Caméra":
        img_file = st.camera_input("Photo")
    else:
        img_file = st.file_uploader("Upload", type=['jpg','png','jpeg'])
    
    if img_file and st.button("Lancer l'Analyse IA ✨"):
        if not ia_ok:
            st.error("Clé API manquante dans les Secrets !")
        else:
            pil_img = Image.open(img_file)
            st.image(pil_img, width=150)
            with st.spinner("🤖 L'IA interroge Google..."):
                # On récupère le résultat OU l'erreur
                description, erreur_exacte = analyser_image_detective(pil_img)
                
                if description:
                    st.success(f"✅ Trouvé : {description}")
                    with st.spinner("Estimation du prix..."):
                        p, i = analyser_prix_ebay(description)
                        st.session_state.res = {'prix': p, 'img': i, 'nom': description}
                else:
                    # On affiche le vrai message d'erreur de Google
                    st.error(f"❌ Google a refusé l'image. Raison exacte : {erreur_exacte}")

# RÉSULTATS
if 'res' in st.session_state:
    st.divider()
    r = st.session_state.res
    c1, c2 = st.columns([1,2])
    c1.image(r['img'])
    with c2:
        st.metric("Cote eBay", f"{r['prix']:.2f} €")
        achat = st.number_input("Prix Achat", 0.0)
        if st.button("Sauvegarder"):
            if sheet:
                sheet.append_row([datetime.now().str(), r['nom'], r['prix'], achat, "Trokia v2.1", r['img']])
                st.success("Sauvegardé !")
