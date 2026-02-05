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
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v8 : Market Master", page_icon="🌐", layout="wide")

# --- 1. IA ---
def configurer_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        all_m = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Priorité Flash > Pro
        choix = next((m for m in all_m if "flash" in m.lower() and "1.5" in m), None)
        if not choix: choix = next((m for m in all_m if "pro" in m.lower() and "1.5" in m), None)
        return choix if choix else all_m[0]
    except: return None

def analyser_image_complete(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        prompt = (
            "Analyse cette image pour un revendeur pro. "
            "Donne-moi :\n"
            "1. Le NOM exact pour la recherche (Marque Modèle).\n"
            "2. La CATÉGORIE (LIVRE, JEU_VIDEO, VETEMENT, MEUBLE, TECH, AUTRE).\n"
            "Réponds strictement : NOM: ... | CAT: ..."
        )
        response = model.generate_content([prompt, image_pil])
        text = response.text.strip()
        
        nom = "Inconnu"
        cat = "AUTRE"
        
        if "NOM:" in text: nom = text.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in text: cat = text.split("CAT:")[1].strip()
        
        return nom, cat, None
    except Exception as e: return None, None, str(e)

# --- 2. LE MOTEUR "GOOGLE DORK" (Le secret pour tout scanner) ---
def scan_via_google(query, site_url):
    """Cherche sur un site spécifique via Google pour contourner les blocages."""
    try:
        # Recherche ciblée : site:leboncoin.fr "playstation 5"
        google_query = f"site:{site_url} {query}"
        url = f"https://www.google.com/search?q={google_query.replace(' ', '+')}"
        
        # User-Agent standard pour passer pour un humain
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        
        r = requests.get(url, headers=headers, timeout=6)
        
        prices = []
        # Regex qui cherche les prix dans les titres/descriptions Google (ex: 50€, 50,00 EUR)
        raw = re.findall(r"(\d+[\.,]?\d*)\s?(?:€|EUR)", r.text)
        
        for p in raw:
            try:
                val = float(p.replace(",", ".").replace(" ", ""))
                # Filtre de cohérence prix (pour éviter les fausses detections)
                if 2 < val < 8000: prices.append(val)
            except: continue
            
        moy = sum(prices)/len(prices) if prices else 0
        link = f"https://www.google.com/search?q={google_query.replace(' ', '+')}" # Lien vers la recherche
        return moy, len(prices), link
    except: return 0, 0, ""

# ROBOT EBAY (Direct - Pour avoir les vrais ventes réussies)
def scan_ebay_direct(recherche):
    try:
        clean = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        
        prices = []
        raw = re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text)
        for p in raw:
            v = p[0] if p[0] else p[1]
            try:
                val = float(v.replace(" ", "").replace("\u202f", "").replace(",", "."))
                if 2 < val < 8000: prices.append(val)
            except: continue
        
        soup = BeautifulSoup(r.text, 'html.parser')
        img = ""
        try: img = soup.select_one('.s-item__image-wrapper img')['src']
        except: pass
        
        moy = sum(prices)/len(prices) if prices else 0
        return moy, len(prices), img, url
    except: return 0, 0, "", ""

# --- 3. SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        scope = ["https://spreadsheets.google.com/feeds"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("Trokia_DB").sheet1
    except: return None

# --- INTERFACE ---
st.title("🌐 Trokia Ultimate : Le Scanner 360°")

if 'modele_ia' not in st.session_state:
    st.session_state.modele_ia = configurer_modele()

if not st.session_state.modele_ia:
    st.error("IA Indisponible")
    st.stop()

sheet = connecter_sheets()

# INPUT
mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Image")

if f and st.button("Lancer l'Analyse Totale 🚀"):
    img_pil = Image.open(f)
    c1, c2 = st.columns([1, 3])
    c1.image(img_pil, width=150)
    
    with c2:
        with st.spinner("🤖 Identification IA..."):
            nom, cat, err = analyser_image_complete(img_pil, st.session_state.modele_ia)
        
        if nom:
            st.markdown(f"### 🔎 {nom}")
            st.caption(f"Catégorie : {cat}")
            
            # --- LE MULTI-SCAN ---
            # 1. eBay (La base : Prix vendus)
            with st.spinner("1/4 Scan eBay (Historique Ventes)..."):
                ebay_p, ebay_n, ebay_img, ebay_url = scan_ebay_direct(nom)
            
            # 2. Leboncoin (Le local)
            with st.spinner("2/4 Scan Leboncoin (Annonces)..."):
                lbc_p, lbc_n, lbc_url = scan_via_google(nom, "leboncoin.fr")
                
            # 3. Rakuten (Les pros)
            with st.spinner("3/4 Scan Rakuten (Shopping)..."):
                rak_p, rak_n, rak_url = scan_via_google(nom, "fr.shopping.rakuten.com")
                
            # 4. Vinted (Si vêtement) ou Selency (Si meuble)
            vinted_p, vinted_n, vinted_url = 0, 0, ""
            if "VETEMENT" in cat:
                with st.spinner("4/4 Scan Vinted..."):
                    vinted_p, vinted_n, vinted_url = scan_via_google(nom, "vinted.fr")
            
            # --- AFFICHAGE DASHBOARD ---
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            
            # eBay
            with col1:
                st.markdown("#### 🔵 eBay")
                if ebay_p > 0:
                    st.metric("Vendu", f"{ebay_p:.0f} €", f"{ebay_n} ventes")
                    st.link_button("Voir", ebay_url)
                else: st.caption("Rien trouvé")
            
            # Leboncoin
            with col2:
                st.markdown("#### 🟠 Leboncoin")
                if lbc_p > 0:
                    st.metric("Offre", f"{lbc_p:.0f} €", f"~{lbc_n} annonces")
                    st.link_button("Voir", lbc_url)
                else: st.caption("Rien trouvé")
                
            # Rakuten
            with col3:
                st.markdown("#### 🟣 Rakuten")
                if rak_p > 0:
                    st.metric("Pro", f"{rak_p:.0f} €", f"~{rak_n} annonces")
                    st.link_button("Voir", rak_url)
                else: st.caption("Rien trouvé")
            
            # Bonus (Vinted/Autre)
            with col4:
                st.markdown(f"#### {'🔴 Vinted' if 'VETEMENT' in cat else '⚪ Autre'}")
                if vinted_p > 0:
                    st.metric("Fripe", f"{vinted_p:.0f} €", f"~{vinted_n} annonces")
                    st.link_button("Voir", vinted_url)
                else: st.caption("-")

            # --- CALCUL INTELLIGENT ---
            # On fait une moyenne pondérée des sources trouvées
            sources_active = [p for p in [ebay_p, lbc_p, rak_p, vinted_p] if p > 0]
            if sources_active:
                prix_final_estime = sum(sources_active) / len(sources_active)
            else:
                prix_final_estime = 0.0

            st.session_state.save_data = {
                'nom': nom, 'prix': prix_final_estime, 'img': ebay_img, 'sources': len(sources_active)
            }

        else: st.error(f"Erreur IA : {err}")

# SAUVEGARDE
if 'save_data' in st.session_state:
    d = st.session_state.save_data
    st.write("---")
    st.success(f"💰 Cote Globale Estimée : **{d['prix']:.2f} €** (Basé sur {d['sources']} plateformes)")
    
    col_s1, col_s2, col_s3 = st.columns([1,1,2])
    prix_retenu = col_s1.number_input("Prix Revente Prévu", value=float(d['prix']))
    achat = col_s2.number_input("Prix Achat", 0.0)
    
    if col_s3.button("💾 Enregistrer dans le Cloud", use_container_width=True):
        if sheet:
            sheet.append_row([
                datetime.now().strftime("%d/%m/%Y"), 
                d['nom'], 
                prix_retenu, 
                achat, 
                "Trokia v8 (Multi)", 
                d['img']
            ])
            st.balloons()
            st.toast("✅ Base de données mise à jour !")
