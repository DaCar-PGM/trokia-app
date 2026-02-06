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

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia Cloud", page_icon="☁️", layout="wide")

# --- CONNEXION GOOGLE SHEETS ---
def connecter_sheets():
    # On récupère le JSON depuis les secrets Streamlit
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # Ouvre le fichier par son nom (Doit être EXACTEMENT "Trokia_DB")
        sheet = client.open("Trokia_DB").sheet1
        return sheet
    except Exception as e:
        st.error(f"Erreur de connexion Google Sheets : {e}")
        return None

# --- FONCTIONS MÉTIER ---
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
    options.add_argument("--no-sandbox") # Important pour le Cloud
    options.add_argument("--disable-dev-shm-usage") # Important pour le Cloud
    return options

def analyser_produit_ebay(driver, recherche):
    url = "https://www.ebay.fr/sch/i.html?_nkw=" + recherche.replace(" ", "+") + "&LH_Sold=1&LH_Complete=1"
    driver.get(url)
    time.sleep(2)
    
    image_url = "https://via.placeholder.com/150"
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

# --- INTERFACE ---
st.title("💎 Trokia Cloud : Master System")

# Connexion DB
sheet = connecter_sheets()
if not sheet:
    st.stop()

# Lecture des données existantes
try:
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # Si le fichier est vide, on initialise les colonnes
    if df.empty:
        df = pd.DataFrame(columns=["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"])
except:
    df = pd.DataFrame(columns=["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"])

col_scan, col_kpi = st.columns([1, 2])

# ZONE DE SCAN
with col_scan:
    st.markdown("### ☁️ Scanner Cloud")
    entree = st.text_input("Produit à scanner", key="input_scan")
    
    if st.button("Analyser 🚀", use_container_width=True):
        if entree:
            with st.spinner("Recherche mondiale..."):
                service = Service(ChromeDriverManager().install())
                options = configurer_navigateur()
                driver = webdriver.Chrome(service=service, options=options)
                try:
                    prix, img = analyser_produit_ebay(driver, entree)
                    st.session_state.temp_prix = prix
                    st.session_state.temp_img = img
                    st.session_state.temp_produit = entree
                except Exception as e:
                    st.error(f"Erreur: {e}")
                finally:
                    driver.quit()

    if 'temp_prix' in st.session_state and st.session_state.temp_prix > 0:
        valeur = round(st.session_state.temp_prix, 2)
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(st.session_state.temp_img, width=100)
        with c2:
            st.success(f"Cote : **{valeur} €**")
            prix_achat = st.number_input("Prix d'achat (€)", min_value=0.0, step=1.0, key="achat_input")
            
        if st.button("💾 Enregistrer dans le Cloud", use_container_width=True):
            cat = deviner_categorie(st.session_state.temp_produit)
            date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # Ajout Google Sheets
            nouvelle_ligne = [date_now, st.session_state.temp_produit, valeur, prix_achat, cat, st.session_state.temp_img]
            
            # Si c'est la première ligne et qu'il n'y a pas d'en-tête, on ajoute l'en-tête d'abord
            if df.empty:
                 sheet.append_row(["Date", "Produit", "Estimation", "Prix Achat", "Catégorie", "Image"])
            
            sheet.append_row(nouvelle_ligne)
            
            st.toast("Sauvegardé sur Google Drive !", icon="☁️")
            # Reset
            del st.session_state.temp_prix
            time.sleep(1)
            st.rerun()

# DASHBOARD
with col_kpi:
    st.markdown("### 📊 Données Temps Réel (Google Sheets)")
    
    if not df.empty and "Estimation" in df.columns:
        # Nettoyage des données numériques (parfois Google envoie des strings)
        df["Estimation"] = pd.to_numeric(df["Estimation"], errors='coerce').fillna(0)
        df["Prix Achat"] = pd.to_numeric(df["Prix Achat"], errors='coerce').fillna(0)
        
        total_valeur = df["Estimation"].sum()
        total_investi = df["Prix Achat"].sum()
        profit = total_valeur - total_investi
        
        k1, k2, k3 = st.columns(3)
        k1.metric("Stock Cloud", f"{round(total_valeur, 2)} €")
        k2.metric("Investi", f"{round(total_investi, 2)} €")
        k3.metric("PROFIT", f"{round(profit, 2)} €")
        
        # Graphique
        if "Catégorie" in df.columns:
            chart_data = df.groupby("Catégorie")["Estimation"].sum()
            st.bar_chart(chart_data, color="#3498DB")
            
        # Tableau
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("La base de données est vide. Scannez votre premier objet !")
