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

# --- 2. CONFIGURATION INTELLIGENCE ARTIFICIELLE (VISION) ---
try:
    # On récupère la clé API
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    # On utilise le modèle Flash (rapide et pas cher)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    st.warning("⚠️ L'IA n'est pas encore active. Vérifiez la clé API dans les Secrets.")

# --- 3. CONNEXION GOOGLE SHEETS (MÉMOIRE) ---
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

# --- 4. LE ROBOT CHERCHEUR DE PRIX (EBAY) ---
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
        
        # URL de recherche eBay (Ventes réussies uniquement)
        url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
        driver.get(url)
        time.sleep(2)
        
        # Récupération de l'image
        image_url = "https://via.placeholder.com/150?text=No+Image"
        try:
            img_element = driver.find_element(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            src = img_element.get_attribute("src")
            if src: image_url = src
        except: pass

        # Récupération des prix
        texte = driver.find_element(By.TAG_NAME, "body").text
        # Regex pour trouver les prix (format 12,50 ou 12.50)
        motifs = re.findall(r"(\d+[\.,]?\d*)\s*EUR", texte)
        
        prix_liste = []
        for p in motifs:
            try:
                # Nettoyage du prix (remplace virgule par point)
                val = float(p.replace(',', '.').strip())
                if 1 < val < 10000: # On ignore les erreurs bizarres (0€ ou 1M€)
                    prix_liste.append(val)
            except: continue
        
        driver.quit()
        
        # Calcul de la moyenne
        if prix_liste:
            prix_final = sum(prix_liste) / len(prix_liste)
        else:
            prix_final = 0
            
        return prix_final, image_url
        
    except Exception as e:
        print(f"Erreur Scraping: {e}")
        return 0, "https://via.placeholder.com/150?text=Erreur"

# --- 5. L'INTERFACE UTILISATEUR (Ce qu'on voit) ---
st.title("💎 Trokia Ultimate : Vision & Trader")

# Connexion à la base de données
sheet = connecter_sheets()
if not sheet: st.stop()

# Les Onglets
tab1, tab2 = st.tabs(["🔍 Scan Texte / Code-barres", "📸 Analyse Photo (IA)"])

# ONGLET 1 : RECHERCHE CLASSIQUE
with tab1:
    entree = st.text_input("Nom de l'objet ou Code-barres", placeholder="Ex: Game Boy Color")
    if st.button("Lancer l'Analyse 🚀", key="btn_text"):
        with st.spinner("Analyse du marché en cours..."):
            prix, img = analyser_prix_ebay(entree)
            st.session_state.prix = prix
            st.session_state.img = img
            st.session_state.nom = entree

# ONGLET 2 : VISION IA (CAMÉRA)
with tab2:
    st.info("Prenez une photo d'un objet sans code-barres (Chaussure, Meuble, Déco...).")
    photo = st.camera_input("Scanner l'objet")
    
    if photo:
        img_pil = Image.open(photo)
        with st.spinner("🧠 L'IA analyse l'image..."):
            try:
                # On demande à Gemini de décrire l'objet
                prompt = "Tu es un expert en brocante. Identifie précisément cet objet (Marque, Modèle exact, Couleur) pour que je puisse chercher son prix sur eBay. Réponds UNIQUEMENT avec le nom court de l'objet."
                response = model.generate_content([prompt, img_pil])
                description = response.text.strip()
                st.success(f"Objet identifié : **{description}**")
                
                # On lance la recherche de prix automatiquement
                with st.spinner(f"Recherche du prix pour : {description}"):
                    prix, img = analyser_prix_ebay(description)
                    st.session_state.prix = prix
                    # On garde la photo prise par l'utilisateur si possible, sinon celle d'eBay
                    st.session_state.img = img 
                    st.session_state.nom = description
            except Exception as e:
                st.error(f"L'IA n'a pas pu analyser l'image. Erreur : {e}")

# AFFICHAGE DU RÉSULTAT ET SAUVEGARDE
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
            # Enregistrement dans Google Sheets
            # Colonnes : Date | Produit | Estimation | Achat | Source | Image
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
                st.toast("✅ Sauvegardé dans le Cloud !", icon="☁️")
                time.sleep(2)
                # On efface pour le prochain scan
                del st.session_state.prix
                st.rerun()
            except Exception as e:
                st.error(f"Erreur de sauvegarde : {e}")
