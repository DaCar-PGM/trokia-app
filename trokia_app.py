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
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION GLOBALE ---
st.set_page_config(page_title="Trokia v5.0 : Mobile Stealth", page_icon="📱", layout="wide")

# --- 1. CERVEAU IA (AUTO-ADAPTATIF) ---
def configurer_et_trouver_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priorité : Flash > Pro > Vision
        choix = next((m for m in all_models if "flash" in m.lower() and "1.5" in m), None)
        if not choix: choix = next((m for m in all_models if "pro" in m.lower() and "1.5" in m), None)
        if not choix: choix = next((m for m in all_models if "vision" in m.lower()), None)
        if not choix and all_models: choix = all_models[0]  
        return choix
    except: return None

def analyser_image(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        # Prompt strict pour éviter les phrases
        prompt = "Analyse cette image pour eBay. Donne-moi UNIQUEMENT : Marque et Modèle. Ex: 'Burton Moto Boots'. Pas de couleur, pas de blabla."
        response = model.generate_content([prompt, image_pil])
        return response.text.strip(), None
    except Exception as e:
        if "429" in str(e): return None, "Quota IA saturé. Pause de 1 min requise."
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

# --- 3. NAVIGATEUR MOBILE (L'ARME SECRÈTE) ---
def get_driver():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # --- DÉGUISEMENT MOBILE ANDROID ---
    # eBay sert des pages plus simples aux mobiles, souvent moins protégées
    mobile_ua = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
    options.add_argument(f"user-agent={mobile_ua}")
    
    options.add_argument("--lang=fr-FR")
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def analyser_prix_ebay(recherche):
    driver = None
    try:
        driver = get_driver()
        # Nettoyage
        termes = re.sub(r'[^\w\s]', '', recherche).strip()
        
        # URL Mobile eBay
        url = f"https://www.ebay.fr/sch/i.html?_nkw={termes.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        
        driver.get(url)
        time.sleep(random.uniform(2.5, 4.0)) # Pause humaine
        
        # 1. TENTATIVE VIA CLASSE CSS (Plus précis)
        prix_collectes = []
        try:
            # Sur mobile/desktop, c'est souvent cette classe
            elements_prix = driver.find_elements(By.CLASS_NAME, "s-item__price")
            for el in elements_prix:
                txt = el.text
                # On nettoie le texte (Ex: "EUR 50,00" -> 50.0)
                vals = re.findall(r"[\d\.,]+", txt)
                for v in vals:
                    try:
                        v_clean = float(v.replace(".", "").replace(",", "."))
                        if 5 < v_clean < 5000: prix_collectes.append(v_clean)
                    except: continue
        except: pass

        # 2. TENTATIVE VIA REGEX (Si CSS échoue)
        if not prix_collectes:
            page_content = driver.find_element(By.TAG_NAME, "body").text
            pattern = r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)"
            raw_prices = re.findall(pattern, page_content)
            for p in raw_prices:
                val_text = p[0] if p[0] else p[1]
                try:
                    clean = val_text.replace(" ", "").replace("\u202f", "").replace(",", ".")
                    val = float(clean)
                    if 5 < val < 5000: prix_collectes.append(val)
                except: continue

        # Image
        img_url = ""
        try:
            imgs = driver.find_elements(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            if len(imgs) > 0: img_url = imgs[0].get_attribute("src")
        except: pass

        driver.quit()
        
        nb = len(prix_collectes)
        moyenne = sum(prix_collectes) / nb if nb > 0 else 0
        
        return moyenne, img_url, nb, url
        
    except Exception as e:
        return 0, "", 0, "https://www.ebay.fr"
    finally:
        if driver: 
            try: driver.quit()
            except: pass

# --- INTERFACE ---
st.title("💎 Trokia v5.0 : Mobile Stealth")

if 'modele_ia' not in st.session_state:
    with st.spinner("Démarrage Système..."):
        st.session_state.modele_ia = configurer_et_trouver_modele()

if not st.session_state.modele_ia:
    st.error("❌ Erreur IA Fatal")
    st.stop()
else:
    st.caption(f"🤖 Cerveau : {st.session_state.modele_ia}")

sheet = connecter_sheets()

tab1, tab2 = st.tabs(["🔎 Recherche", "📸 Scanner"])

with tab1:
    q = st.text_input("Objet")
    if st.button("Estimer"):
        with st.spinner("Scraping Mobile..."):
            p, i, n, u = analyser_prix_ebay(q)
            st.session_state.res = {'p': p, 'i': i, 'n': q, 'c': n, 'u': u}

with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f and st.button("Lancer 🚀"):
        img = Image.open(f)
        st.image(img, width=200)
        with st.spinner("Identification & Estimation..."):
            nom, err = analyser_image(img, st.session_state.modele_ia)
            if nom:
                st.success(f"Objet : {nom}")
                p, i, n, u = analyser_prix_ebay(nom)
                st.session_state.res = {'p': p, 'i': i, 'n': nom, 'c': n, 'u': u}
            else:
                st.error(f"Erreur IA: {err}")

# RÉSULTATS
if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    c1, c2 = st.columns([1, 2])
    with c1:
        if r.get('i') and r['i'].startswith("http"):
            try: st.image(r['i'], width=150)
            except: st.warning("Image protégée")
    with c2:
        st.markdown(f"### {r['n']}")
        
        # LOGIQUE D'AFFICHAGE ULTIME
        if r['p'] > 0:
            st.metric("Cote Moyenne", f"{r['p']:.2f} €", delta=f"{r['c']} ventes")
            st.link_button("Vérifier sur eBay", r['u'])
        else:
            st.warning("⚠️ Prix non détecté (Sécurité eBay active).")
            st.info("👇 Cliquez ci-dessous pour voir la cote réelle et saisir le prix.")
            st.link_button("🔎 Voir la cote sur eBay", r['u'])
        
        # SAISIE INTELLIGENTE
        # Si le prix est trouvé, on le met par défaut, sinon 0
        val_default = float(r['p']) if r['p'] > 0 else 0.0
        prix_estime_final = st.number_input("Cote Retenue (€)", value=val_default, step=1.0)
        
        achat = st.number_input("Prix Achat (€)", 0.0, step=1.0)
        
        if st.button("💾 Enregistrer"):
            if sheet:
                sheet.append_row([datetime.now().strftime("%d/%m/%Y"), r['n'], prix_estime_final, achat, "Mobile v5", r['i']])
                st.success("Sauvegardé !")
