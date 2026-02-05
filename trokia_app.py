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
st.set_page_config(page_title="Trokia v8.2 : Le Hub", page_icon="🎛️", layout="wide")

HEADERS_FURTIFS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
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
        prompt = "Analyse cette image pour un revendeur. Donne-moi STRICTEMENT : NOM: Marque Modèle | CAT: VETEMENT/MEUBLE/TECH/AUTRE"
        response = model.generate_content([prompt, image_pil])
        text = response.text.strip()
        nom, cat = "Inconnu", "AUTRE"
        if "NOM:" in text: nom = text.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in text: cat = text.split("CAT:")[1].strip()
        return nom, cat, None
    except Exception as e: return None, None, str(e)

# --- 2. GENERATEUR DE LIENS INTELLIGENTS ---
def generer_lien_recherche(nom, site):
    # On crée juste l'URL propre pour que l'utilisateur clique
    base_google = "https://www.google.com/search?q="
    query = f"site:{site} {nom}"
    return base_google + query.replace(" ", "+")

def scan_google_prix(nom, site):
    # Tente de récupérer le prix, mais renvoie TOUJOURS le lien
    url = generer_lien_recherche(nom, site)
    try:
        r = requests.get(url, headers=HEADERS_FURTIFS, timeout=4) # Timeout court pour aller vite
        prices = []
        raw = re.findall(r"(\d+[\.,]?\d*)\s?(?:€|EUR)", r.text)
        for p in raw:
            try:
                val = float(p.replace(",", ".").replace(" ", ""))
                if 2 < val < 5000: prices.append(val)
            except: continue
        moy = sum(prices)/len(prices) if prices else 0
        return moy, len(prices), url
    except: return 0, 0, url

# ROBOT EBAY (La Valeur Sûre)
def scan_ebay_direct(recherche):
    try:
        clean = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url, headers=HEADERS_FURTIFS, timeout=6)
        prices = []
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Extraction CSS
        items = soup.select('.s-item__price')
        for item in items:
            txt = item.get_text()
            vals = re.findall(r"[\d\.,]+", txt)
            for v in vals:
                try:
                    v_clean = float(v.replace(".", "").replace(",", "."))
                    if 5 < v_clean < 5000: prices.append(v_clean)
                except: continue
        
        img = ""
        try: img = soup.select_one('.s-item__image-wrapper img')['src']
        except: pass
        
        moy = sum(prices)/len(prices) if prices else 0
        return moy, len(prices), img, url
    except: return 0, 0, "", ""

# --- SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds"])
        return gspread.authorize(creds).open("Trokia_DB").sheet1
    except: return None

# --- UI ---
st.title("🎛️ Trokia : Le Command Center")

if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Image")

if f and st.button("Lancer l'Analyse 🚀"):
    img_pil = Image.open(f)
    c1, c2 = st.columns([1, 3])
    c1.image(img_pil, width=150)
    
    with c2:
        with st.spinner("🧠 Analyse IA..."):
            nom, cat, err = analyser_image_complete(img_pil, st.session_state.modele_ia)
        
        if nom:
            st.markdown(f"### 🔎 {nom}")
            
            # SCAN PARALLÈLE
            with st.spinner("Scraping des marchés..."):
                # eBay (Prioritaire)
                ebay_p, ebay_n, ebay_img, ebay_url = scan_ebay_direct(nom)
                
                # Autres (Via Google Light)
                lbc_p, lbc_n, lbc_url = scan_google_prix(nom, "leboncoin.fr")
                rak_p, rak_n, rak_url = scan_google_prix(nom, "fr.shopping.rakuten.com")
                vinted_url = generer_lien_recherche(nom, "vinted.fr")
                
            # DASHBOARD INTERACTIF
            st.divider()
            k1, k2, k3, k4 = st.columns(4)
            
            # 1. eBay (Le Juge de Paix)
            with k1:
                st.markdown("#### 🔵 eBay")
                if ebay_p > 0:
                    st.metric("Cote Vendu", f"{ebay_p:.2f} €", f"{ebay_n} ventes")
                    st.link_button("Voir Annonces", ebay_url)
                else:
                    st.caption("Pas de cote")
                    st.link_button("🔎 Vérifier", ebay_url)
            
            # 2. Leboncoin (L'Opportunité)
            with k2:
                st.markdown("#### 🟠 Leboncoin")
                if lbc_p > 0:
                    st.metric("Offre", f"{lbc_p:.0f} €")
                    st.link_button("Voir Annonces", lbc_url)
                else:
                    st.caption("Prix caché")
                    # LE BOUTON MAGIQUE EST LÀ MÊME SI PRIX = 0
                    st.link_button("🔎 Ouvrir LBC", lbc_url)

            # 3. Rakuten (Le Pro)
            with k3:
                st.markdown("#### 🟣 Rakuten")
                if rak_p > 0:
                    st.metric("Pro", f"{rak_p:.0f} €")
                    st.link_button("Voir Annonces", rak_url)
                else:
                    st.caption("Prix caché")
                    st.link_button("🔎 Ouvrir Rakuten", rak_url)

            # 4. Vinted (La Fripe)
            with k4:
                st.markdown("#### 🔴 Vinted")
                # Lien direct, simple et efficace
                st.link_button("👕 Ouvrir Vinted", vinted_url)

            # SAVE
            # On prend eBay par défaut, sinon 0
            prix_estim = ebay_p if ebay_p > 0 else 0.0
            st.session_state.sd = {'n': nom, 'p': prix_estim, 'i': ebay_img}

if 'sd' in st.session_state:
    d = st.session_state.sd
    st.write("---")
    c1, c2, c3 = st.columns([1,1,2])
    p_final = c1.number_input("Prix Revente", value=float(d['p']))
    achat = c2.number_input("Prix Achat", 0.0)
    if c3.button("💾 Sauvegarder", use_container_width=True):
        if sheet:
            sheet.append_row([datetime.now().strftime("%d/%m/%Y"), d['n'], p_final, achat, "Trokia v8.2", d['i']])
            st.success("Enregistré !")
