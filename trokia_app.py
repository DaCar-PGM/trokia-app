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

# --- 1. CONFIGURATION DU SITE ---
st.set_page_config(page_title="Trokia Ultimate", page_icon="💎", layout="wide")

# --- 2. CONFIGURATION IA (VISION) ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-pro')
except Exception as e:
    st.warning("⚠️ L'IA n'est pas encore active. Vérifiez la clé API dans les Secrets.")

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
    except Exception as e:
        st.error(f"Erreur de connexion Cloud : {e}")
        return None

# --- 4. ROBOT RECHERCHE PRIX ---
def configurer_navigateur():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return options

def analyser_prix_ebay(recherche):
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=configurer_navigateur())
        
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
                if 1 < val < 10000: 
                    prix_liste.append(val)
            except: continue
        
        driver.quit()
        
        if prix_liste:
            prix_final = sum(prix_liste) / len(prix_liste)
        else:
            prix_final = 0
            
        return prix_final, image_url
        
    except Exception as e:
        return 0, "https://via.placeholder.com/150?text=Erreur"

# --- 5. INTERFACE ---
st.title("💎 Trokia Ultimate : Vision & Trader")

sheet = connecter_sheets()
if not sheet: st.stop()

tab1, tab2 = st.tabs(["🔍 Scan Texte", "📸 Analyse Photo (IA)"])

# ONGLET 1 : TEXTE
with tab1:
    entree = st.text_input("Nom de l'objet ou Code-barres", placeholder="Ex: Game Boy Color")
    if st.button("Lancer l'Analyse 🚀", key="btn_text"):
        with st.spinner("Analyse du marché en cours..."):
            prix, img = analyser_prix_ebay(entree)
            st.session_state.prix = prix
            st.session_state.img = img
            st.session_state.nom = entree

# ONGLET 2 : VISION IA (CAMÉRA OU UPLOAD)
with tab2:
    st.info("Analysez une photo prise maintenant ou depuis votre galerie.")
    
    # Le choix magique
    mode_photo = st.radio("Source de l'image :", ["📸 Caméra", "📂 Importer depuis la Galerie"], horizontal=True)
    
    image_data = None
    
    if mode_photo == "📸 Caméra":
        image_data = st.camera_input("Prendre une photo")
    else:
        image_data = st.file_uploader("Choisir une image", type=['jpg', 'png', 'jpeg'])
    
    # Traitement de l'image (peu importe la source)
    if image_data:
        img_pil = Image.open(image_data)
        st.image(img_pil, caption="Image à analyser", width=200)
        
        if st.button("🔍 Analyser cette image"):
            with st.spinner("🧠 L'IA analyse l'image..."):
                try:
                    prompt = "Tu es un expert en brocante. Identifie précisément cet objet (Marque, Modèle exact, Couleur) pour que je puisse chercher son prix sur eBay. Réponds UNIQUEMENT avec le nom court de l'objet."
                    response = model.generate_content([prompt, img_pil])
                    description = response.text.strip()
                    st.success(f"Objet identifié : **{description}**")
                    
                    with st.spinner(f"Recherche du prix pour : {description}"):
                        prix, img = analyser_prix_ebay(description)
                        st.session_state.prix = prix
                        st.session_state.img = img 
                        st.session_state.nom = description
                except Exception as e:
                    st.error(f"L'IA n'a pas pu analyser l'image. Erreur : {e}")

# RÉSULTAT ET SAUVEGARDE
if 'prix' in st.session_state and st.session_state.prix > 0:
    st.divider()
    st.markdown("### 💰 Résultat de l'estimation")
    
    col_res1, col_res2 = st.columns([1, 2])
    
    with col_res1:
        st.image(st.session_state.img, width=150, caption="Produit trouvé")
    
    with col_res2:
        valeur = round(st.session_state.prix, 2)
        st.metric(label="Cote Moyenne eBay", value=f"{valeur} €")
        
        prix_achat = st.number_input("Prix d'achat négocié (€)", min_value=0.0, step=1.0)
        
        if st.button("💾 Ajouter à mon Stock", use_container_width=True):
            date_now = datetime.now().strftime("%d/%m/%Y %H:%M")
            try:
                sheet.append_row([
                    date_now, 
                    st.session_state.nom, 
                    str(valeur).replace('.', ','), 
                    str(prix_achat).replace('.', ','), 
                    "App Mobile", 
                    st.session_state.img
                ])
                st.balloons()
                st.toast("✅ Sauvegardé !", icon="☁️")
                time.sleep(2)
                del st.session_state.prix
                st.rerun()
            except Exception as e:
                st.error(f"Erreur de sauvegarde : {e}")

