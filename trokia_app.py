import streamlit as st
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

# --- CONFIGURATION DU SITE ---
st.set_page_config(page_title="Trokia Cloud", page_icon="☁️", layout="wide")

# --- CONNEXION INTELLIGENTE A GOOGLE SHEETS ---
def connecter_sheets():
    try:
        # On lit le secret formaté proprement
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Ouvre le fichier
        sheet = client.open("Trokia_DB").sheet1
        return sheet
    except Exception as e:
        st.error(f"⚠️ Erreur de connexion au Cloud : {e}")
        st.info("Vérifiez que le fichier Google Sheets s'appelle bien 'Trokia_DB' et que le robot est éditeur.")
        return None

# --- IA & SCAN ---
def deviner_categorie(nom_produit):
    nom = str(nom_produit).lower()
    regles = {
        "🎮 Gaming": ["ps5", "ps4", "switch", "nintendo", "xbox", "jeu", "zelda", "mario", "manette", "console", "gameboy", "game boy", "pokemon", "sega"],
        "📱 Téléphonie": ["iphone", "samsung", "galaxy", "xiaomi", "redmi", "pixel", "huawei", "smartphone", "oppo", "nokia"],
        "💻 Informatique": ["macbook", "dell", "hp", "asus", "lenovo", "ordinateur", "pc", "laptop", "clavier", "souris", "usb", "ipad", "tablette", "geforce", "nvidia"],
        "📸 Photo/Vidéo": ["canon", "nikon", "sony alpha", "gopro", "camera", "objectif", "instax", "lumix", "kodak"],
        "📚 Livres/Culture": ["livre", "roman", "bd", "manga", "tome", "album", "cd", "dvd", "blu-ray", "vinyle", "collector"],
        "👟 Mode/Luxe": ["nike", "adidas", "jordan", "yeezy", "sac", "montre", "rolex", "seiko", "vêtement", "gucci", "vuitton"],
        "🏠 Maison/Électro": ["aspirateur", "dyson", "cafetière", "robot", "cuisine", "outil", "bricolage", "bosch", "makita"]
    }
    for categorie, mots_cles in regles.items():
        if any(mot in nom for mot in mots_cles): return categorie
    return "📦 Divers"

def configurer_navigateur():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options

def analyser_produit_ebay(driver, recherche):
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
            if 1 < val < 10000: prix_liste.append(val)
        except: continue
    
    prix_final = sum(prix_liste) / len(prix_liste) if prix_liste else 0
    return prix_final, image_url

# --- INTERFACE UTILISATEUR ---
st.title("💎 Trokia Cloud : Master System")

# 1. Connexion
sheet = connecter_sheets()
if not sheet: st.stop()

# 2. Récupération des données
try:
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # Initialisation si vide
    cols_requises = ["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"]
    if df.empty or not all(col in df.columns for col in cols_requises):
        df = pd.DataFrame(columns=cols_requises)
except:
    df = pd.DataFrame(columns=["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"])

col_scan, col_kpi = st.columns([1, 2])

# GAUCHE : SCANNER
with col_scan:
    st.markdown("### ☁️ Scanner Cloud")
    entree = st.text_input("Rechercher un produit", key="input_scan")
    
    if st.button("Lancer l'Analyse 🚀", use_container_width=True):
        if entree:
            with st.spinner("Analyse du marché en cours..."):
                try:
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=configurer_navigateur())
                    prix, img = analyser_produit_ebay(driver, entree)
                    driver.quit()
                    
                    st.session_state.temp_prix = prix
                    st.session_state.temp_img = img
                    st.session_state.temp_produit = entree
                except Exception as e:
                    st.error(f"Erreur technique : {e}")

    if 'temp_prix' in st.session_state and st.session_state.temp_prix > 0:
        valeur = round(st.session_state.temp_prix, 2)
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(st.session_state.temp_img, caption="Aperçu", width=120)
        with c2:
            st.success(f"Cote : **{valeur} €**")
            prix_achat = st.number_input("Prix d'achat (€)", min_value=0.0, step=1.0, key="achat_input")
            
        if st.button("💾 Sauvegarder (Google Sheets)", use_container_width=True):
            cat = deviner_categorie(st.session_state.temp_produit)
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Préparation de la ligne
            # Note : on force la conversion en float pour Google Sheets
            nouvelle_ligne = [
                date_now, 
                st.session_state.temp_produit, 
                str(valeur).replace('.', ','), 
                str(prix_achat).replace('.', ','), 
                cat, 
                st.session_state.temp_img
            ]
            
            # Si vide, on met les titres d'abord
            if df.empty:
                 sheet.append_row(["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"])
            
            sheet.append_row(nouvelle_ligne)
            
            st.toast("Produit ajouté à la base de données !", icon="☁️")
            del st.session_state.temp_prix
            time.sleep(1)
            st.rerun()

# DROITE : DASHBOARD
with col_kpi:
    st.markdown("### 📊 Données Temps Réel")
    
    if not df.empty and "Estimation" in df.columns:
        # Nettoyage des données pour les calculs (remplace virgules par points)
        try:
            df["Estimation_Calc"] = df["Estimation"].astype(str).str.replace(',', '.').astype(float)
            df["Achat_Calc"] = df["Prix Achat"].astype(str).str.replace(',', '.').astype(float)
        except:
            df["Estimation_Calc"] = 0.0
            df["Achat_Calc"] = 0.0
            
        total_valeur = df["Estimation_Calc"].sum()
        total_investi = df["Achat_Calc"].sum()
        profit = total_valeur - total_investi
        
        # KPI
        k1, k2, k3 = st.columns(3)
        k1.metric("Valeur Stock", f"{round(total_valeur, 2)} €")
        k2.metric("Investissement", f"{round(total_investi, 2)} €")
        k3.metric("PROFIT NET", f"{round(profit, 2)} €", delta=f"{round((profit/total_investi)*100) if total_investi>0 else 0}%")
        
        # Tableau avec Images
        st.markdown("---")
        st.dataframe(
            df[["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"]],
            column_config={
                "Image": st.column_config.ImageColumn("Aperçu", width="small"),
                "Estimation": st.column_config.NumberColumn("Cote (€)"),
                "Prix Achat": st.column_config.NumberColumn("Achat (€)"),
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("👋 Bienvenue ! Scannez votre premier objet pour initialiser la base de données.")
