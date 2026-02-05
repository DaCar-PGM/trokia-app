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
import random

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v8.1 : Market Master", page_icon="🌐", layout="wide")

# --- LE DÉGUISEMENT (IMPORTÉ DE LA V6 QUI MARCHAIT) ---
HEADERS_FURTIFS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com/"
}

# --- 1. IA ---
def configurer_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        all_m = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        choix = next((m for m in all_m if "flash" in m.lower() and "1.5" in m), None)
        return choix if choix else all_m[0]
    except: return None

def analyser_image_complete(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        # Prompt optimisé pour la précision
        prompt = (
            "Analyse cette image pour eBay. Donne-moi :\n"
            "1. Le NOM EXACT (Marque + Modèle précis). Ex: 'Nitro Chase Boots'.\n"
            "2. La CATÉGORIE (VETEMENT, MEUBLE, TECH, AUTRE).\n"
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

# --- 2. LE MOTEUR "GOOGLE DORK" (CORRIGÉ) ---
def scan_via_google(query, site_url):
    try:
        google_query = f"site:{site_url} {query}"
        url = f"https://www.google.com/search?q={google_query.replace(' ', '+')}"
        
        # On utilise les headers furtifs ici aussi
        r = requests.get(url, headers=HEADERS_FURTIFS, timeout=8)
        
        # Pause aléatoire pour ne pas énerver Google
        time.sleep(random.uniform(0.5, 1.5))
        
        prices = []
        # Regex large pour capturer les prix dans les résultats de recherche
        raw = re.findall(r"(\d+[\.,]?\d*)\s?(?:€|EUR)", r.text)
        
        for p in raw:
            try:
                val = float(p.replace(",", ".").replace(" ", ""))
                if 2 < val < 8000: prices.append(val)
            except: continue
            
        moy = sum(prices)/len(prices) if prices else 0
        link = f"https://www.google.com/search?q={google_query.replace(' ', '+')}"
        return moy, len(prices), link
    except: return 0, 0, ""

# ROBOT EBAY (RETOUR À LA MÉTHODE V6)
def scan_ebay_direct(recherche):
    try:
        clean = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        
        # ICI : On remet les headers complets
        r = requests.get(url, headers=HEADERS_FURTIFS, timeout=8)
        
        prices = []
        # Méthode CSS (plus précise)
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select('.s-item__price')
        for item in items:
            txt = item.get_text()
            vals = re.findall(r"[\d\.,]+", txt)
            for v in vals:
                try:
                    v_clean = float(v.replace(".", "").replace(",", "."))
                    if 5 < v_clean < 5000: prices.append(v_clean)
                except: continue

        # Méthode Regex (Secours)
        if not prices:
            raw = re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text)
            for p in raw:
                v = p[0] if p[0] else p[1]
                try:
                    val = float(v.replace(" ", "").replace("\u202f", "").replace(",", "."))
                    if 2 < val < 5000: prices.append(val)
                except: continue
        
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
st.title("🌐 Trokia v8.1 : Market Master (Patché)")

if 'modele_ia' not in st.session_state:
    st.session_state.modele_ia = configurer_modele()

if not st.session_state.modele_ia:
    st.error("IA HS")
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
            
            # 1. eBay (Patché avec Headers v6)
            with st.spinner("1/4 Scan eBay..."):
                ebay_p, ebay_n, ebay_img, ebay_url = scan_ebay_direct(nom)
            
            # 2. Leboncoin
            with st.spinner("2/4 Scan Leboncoin..."):
                lbc_p, lbc_n, lbc_url = scan_via_google(nom, "leboncoin.fr")
                
            # 3. Rakuten
            with st.spinner("3/4 Scan Rakuten..."):
                rak_p, rak_n, rak_url = scan_via_google(nom, "fr.shopping.rakuten.com")
                
            # 4. Vinted
            vinted_p, vinted_n, vinted_url = 0, 0, ""
            if "VETEMENT" in cat:
                with st.spinner("4/4 Scan Vinted..."):
                    vinted_p, vinted_n, vinted_url = scan_via_google(nom, "vinted.fr")
            
            # --- DASHBOARD ---
            st.divider()
            col1, col2, col3, col4 = st.columns(4)
            
            # eBay
            with col1:
                st.markdown("#### 🔵 eBay")
                if ebay_p > 0:
                    st.metric("Vendu", f"{ebay_p:.2f} €", f"{ebay_n} ventes")
                    st.link_button("Voir", ebay_url)
                else: st.warning("Introuvable")
            
            # Leboncoin
            with col2:
                st.markdown("#### 🟠 Leboncoin")
                if lbc_p > 0:
                    st.metric("Offre", f"{lbc_p:.0f} €", f"~{lbc_n} annonces")
                    st.link_button("Voir", lbc_url)
                else: st.caption("Introuvable")
                
            # Rakuten
            with col3:
                st.markdown("#### 🟣 Rakuten")
                if rak_p > 0:
                    st.metric("Pro", f"{rak_p:.0f} €", f"~{rak_n} annonces")
                    st.link_button("Voir", rak_url)
                else: st.caption("Introuvable")
            
            # Vinted/Autre
            with col4:
                st.markdown(f"#### {'🔴 Vinted' if 'VETEMENT' in cat else '⚪ Autre'}")
                if vinted_p > 0:
                    st.metric("Fripe", f"{vinted_p:.0f} €", f"~{vinted_n} annonces")
                    st.link_button("Voir", vinted_url)
                else: st.caption("-")

            # Moyenne intelligente
            sources_active = [p for p in [ebay_p, lbc_p, rak_p, vinted_p] if p > 0]
            prix_final_estime = sum(sources_active) / len(sources_active) if sources_active else 0.0

            st.session_state.save_data = {
                'nom': nom, 'prix': prix_final_estime, 'img': ebay_img, 'sources': len(sources_active)
            }

        else: st.error(f"Erreur IA : {err}")

# SAUVEGARDE
if 'save_data' in st.session_state:
    d = st.session_state.save_data
    st.write("---")
    
    if d['prix'] > 0:
        st.success(f"💰 Cote Globale : **{d['prix']:.2f} €**")
    else:
        st.warning("⚠️ Aucun prix trouvé automatiquement. Les sites bloquent peut-être les robots.")
    
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
                "Trokia v8.1", 
                d['img']
            ])
            st.balloons()
            st.toast("✅ Sauvegardé !")
