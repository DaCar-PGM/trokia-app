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
st.set_page_config(page_title="Trokia Ultimate v4.0", page_icon="💎", layout="wide")

# --- 1. CERVEAU IA (AUTO-ADAPTATIF) ---
def configurer_et_trouver_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        # On récupère la liste réelle des modèles dispos pour ton compte
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Stratégie de sélection : Le plus rapide (Flash), sinon le plus fort (Pro)
        # On cherche 'flash' et '1.5'
        choix = next((m for m in all_models if "flash" in m.lower() and "1.5" in m), None)
        # Sinon 'pro' et '1.5'
        if not choix: choix = next((m for m in all_models if "pro" in m.lower() and "1.5" in m), None)
        # Sinon n'importe quel vision
        if not choix: choix = next((m for m in all_models if "vision" in m.lower()), None)
        # Sinon le premier qui vient
        if not choix and all_models: choix = all_models[0]
            
        return choix
    except Exception as e:
        st.error(f"❌ Erreur critique IA : {e}")
        return None

def analyser_image(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        # Prompt optimisé pour éviter le blabla qui perd le moteur de recherche
        prompt = (
            "Analyse cette image pour un expert revendeur. "
            "Donne-moi UNIQUEMENT la Marque et le Modèle principal. "
            "Exemple: 'Nitro Snowboard Boots'. "
            "Ne mets pas de ponctuation, pas de couleur, pas de détails inutiles."
        )
        response = model.generate_content([prompt, image_pil])
        return response.text.strip(), None
    except Exception as e:
        if "429" in str(e): return None, "Quota IA dépassé. Attends 1 min."
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

# --- 3. NAVIGATEUR FANTÔME (STEALTH MODE) ---
def get_driver():
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # --- LE DÉGUISEMENT ULTIME ---
    # On fait croire qu'on est un vrai utilisateur sur Windows 10
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    # On ajoute la langue française pour eBay FR
    options.add_argument("--lang=fr-FR")
    # On désactive les traces d'automatisation
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def analyser_prix_ebay(recherche):
    driver = None
    try:
        driver = get_driver()
        
        # Nettoyage agressif des termes de recherche
        # On enlève virgules, points, et caractères bizarres qui cassent l'URL
        termes_propres = re.sub(r'[^\w\s]', '', recherche) 
        
        # URL eBay : Ventes réussies (Sold) + Terminées (Complete)
        url = f"https://www.ebay.fr/sch/i.html?_nkw={termes_propres.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        
        driver.get(url)
        # Pause aléatoire pour ne pas avoir l'air d'un robot (entre 2 et 4 secondes)
        time.sleep(random.uniform(2.0, 4.0))
        
        # Récupération de l'image (si possible)
        img_url = ""
        try: 
            imgs = driver.find_elements(By.CSS_SELECTOR, "div.s-item__image-wrapper img")
            # On prend la 2ème image car la 1ère est souvent une pub invisible sur eBay
            if len(imgs) > 1: img_url = imgs[1].get_attribute("src")
            elif len(imgs) == 1: img_url = imgs[0].get_attribute("src")
        except: pass

        # Extraction du texte complet de la page
        page_content = driver.find_element(By.TAG_NAME, "body").text
        
        # --- DÉTECTION DE BLOCAGE ---
        if "captcha" in page_content.lower() or "vérification" in page_content.lower():
            return -1, "", 0, url # Code -1 pour dire "Bloqué par eBay"

        # --- REGEX UNIVERSELLE ---
        # Capture : "12,50 EUR", "EUR 12.50", "1 200 €", etc.
        pattern = r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)"
        raw_prices = re.findall(pattern, page_content)
        
        prix_propres = []
        for p in raw_prices:
            # p est un tuple ('', '12,50') ou ('12,50', '')
            val_text = p[0] if p[0] else p[1]
            try:
                # On nettoie : espaces, insécables, virgules -> points
                clean = val_text.replace(" ", "").replace("\u202f", "").replace("\u00a0", "").replace(",", ".")
                val = float(clean)
                # Filtre de cohérence (on ignore les accessoires à 1€ ou les erreurs à 10000€)
                if 5 < val < 5000: 
                    prix_propres.append(val)
            except: continue
        
        nb_res = len(prix_propres)
        moyenne = sum(prix_propres) / nb_res if nb_res > 0 else 0
        
        return moyenne, img_url, nb_res, url
        
    except Exception as e:
        print(f"Erreur scraping: {e}")
        return 0, "", 0, "https://www.ebay.fr"
    finally:
        if driver: driver.quit()

# --- INTERFACE UTILISATEUR ---
st.title("💎 Trokia Ultimate v4.0 : Mode Fantôme 👻")

# Init IA au démarrage
if 'modele_ia' not in st.session_state:
    with st.spinner("Initialisation du système..."):
        st.session_state.modele_ia = configurer_et_trouver_modele()

if not st.session_state.modele_ia:
    st.error("❌ IA indisponible. Vérifiez les Secrets.")
    st.stop()
else:
    st.caption(f"✅ Cerveau actif : `{st.session_state.modele_ia}`")

sheet = connecter_sheets()

tab1, tab2 = st.tabs(["🔎 Recherche Manuelle", "📸 Analyse Photo"])

# TAB 1 : RECHERCHE MANUELLE
with tab1:
    q = st.text_input("Nom de l'objet", placeholder="Ex: Game Boy Color")
    if st.button("Lancer l'estimation 🚀"):
        with st.spinner("Le robot scanne eBay..."):
            p, i, n, u = analyser_prix_ebay(q)
            st.session_state.res = {'p': p, 'i': i, 'n': q, 'c': n, 'u': u}

# TAB 2 : PHOTO
with tab2:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Importer Image")
    
    if f and st.button("Identifier & Estimer ✨"):
        img = Image.open(f)
        st.image(img, width=200)
        
        with st.spinner("🕵️‍♂️ Identification de l'objet..."):
            nom_objet, err = analyser_image(img, st.session_state.modele_ia)
            
            if nom_objet:
                st.success(f"Objet identifié : **{nom_objet}**")
                with st.spinner(f"Scraping des prix pour : {nom_objet}..."):
                    p, i, n, u = analyser_prix_ebay(nom_objet)
                    st.session_state.res = {'p': p, 'i': i, 'n': nom_objet, 'c': n, 'u': u}
            else:
                st.error(f"L'IA n'a pas reconnu l'objet : {err}")

# AFFICHAGE DES RÉSULTATS (Commun aux deux onglets)
if 'res' in st.session_state:
    r = st.session_state.res
    st.divider()
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Gestion des erreurs d'image
        if r.get('i') and r['i'].startswith("http"):
            try: st.image(r['i'], caption="Réf. eBay")
            except: st.warning("Image eBay protégée")
        else:
            st.info("Pas d'image de référence")

    with col2:
        st.markdown(f"### 🏷️ {r['n']}")
        
        # Logique d'affichage du prix
        if r['p'] == -1:
            st.error("🤖 eBay a détecté le robot (Sécurité anti-bot).")
            st.link_button("Ouvrir la recherche manuellement", r['u'])
        elif r['p'] > 0:
            st.metric("Cote Moyenne (Ventes réussies)", f"{r['p']:.2f} €", delta=f"Basé sur {r['c']} ventes")
            st.link_button("Vérifier les annonces sur eBay", r['u'])
        else:
            st.warning("⚠️ Aucun prix trouvé (0.00 €).")
            st.markdown("*Causes possibles : Objet trop rare, mots-clés trop précis, ou pas de ventes récentes.*")
            st.link_button("Voir pourquoi sur eBay", r['u'])

        # Formulaire de sauvegarde
        st.write("---")
        achat = st.number_input("Prix d'achat (€)", 0.0, step=1.0)
        if st.button("💾 Enregistrer dans le Stock"):
            if sheet:
                try:
                    sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), r['n'], r['p'], achat, "Trokia v4", r['i']])
                    st.balloons()
                    st.success("Sauvegardé dans Google Sheets !")
                except Exception as e:
                    st.error(f"Erreur Sheets : {e}")
            else:
                st.error("Erreur de connexion Database")
