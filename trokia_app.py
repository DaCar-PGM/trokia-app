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
st.set_page_config(page_title="Trokia Ultimate v8.4", page_icon="🕵️", layout="wide")

# HEADERS (Pour ne pas être détecté comme un script python de base)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
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
        # Prompt optimisé pour la précision
        prompt = (
            "Tu es un expert revendeur. Analyse cette image."
            "Donne-moi le NOM LE PLUS PRÉCIS POSSIBLE (Marque + Modèle)."
            "Exemple: 'Nitro Staxx Snowboard Boots'."
            "Format: NOM: ... | CAT: VETEMENT/MEUBLE/TECH/AUTRE"
        )
        response = model.generate_content([prompt, image_pil])
        text = response.text.strip()
        nom, cat = "Inconnu", "AUTRE"
        if "NOM:" in text: nom = text.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in text: cat = text.split("CAT:")[1].strip()
        return nom, cat, None
    except Exception as e: return None, None, str(e)

# --- 2. MOTEUR DE RECHERCHE "OPEN SOURCE" (DuckDuckGo) ---
def generer_lien_google(nom, site):
    return f"https://www.google.com/search?q=site:{site}+{nom.replace(' ', '+')}"

def scan_moteur_flexible(nom, site):
    """
    Utilise DuckDuckGo (version HTML) pour contourner les blocages Google.
    C'est beaucoup plus fiable pour récupérer le texte des annonces.
    """
    try:
        # On interroge DuckDuckGo HTML (version légère)
        query = f"site:{site} {nom}"
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        
        r = requests.get(url, headers=HEADERS, timeout=8)
        
        # On analyse le texte brut des résultats
        soup = BeautifulSoup(r.text, 'html.parser')
        text_content = soup.get_text()
        
        prices = []
        # Regex qui cherche "50 €", "50€", "50 EUR"
        # On cherche spécifiquement des petits prix réalistes (pas des codes postaux)
        raw = re.findall(r"(\d+[\.,]?\d*)\s?(?:€|EUR)", text_content)
        
        for p in raw:
            try:
                val = float(p.replace(",", ".").replace(" ", ""))
                # Filtre intelligent : Leboncoin a souvent des prix ronds, Rakuten des prix à virgule
                if 2 < val < 5000: 
                    prices.append(val)
            except: continue
            
        moy = sum(prices)/len(prices) if prices else 0
        
        # On renvoie le prix trouvé MAIS le lien vers Google (plus agréable pour l'utilisateur)
        return moy, len(prices), generer_lien_google(nom, site)
        
    except Exception as e:
        # En cas d'erreur, on renvoie 0 mais avec le lien Google fonctionnel
        return 0, 0, generer_lien_google(nom, site)

# ROBOT EBAY (Direct & Solide)
def scan_ebay_direct(recherche):
    try:
        clean = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url, headers=HEADERS, timeout=6)
        prices = []
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
        
        if not prices: # Fallback Regex
            raw = re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text)
            for p in raw:
                v = p[0] if p[0] else p[1]
                try:
                    v_clean = float(v.replace(" ", "").replace("\u202f", "").replace(",", "."))
                    if 2 < v_clean < 5000: prices.append(v_clean)
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
st.title("🎛️ Trokia v8.4 : Le Moteur Libre")

if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Image")

if f and st.button("Lancer l'Analyse Totale 🚀"):
    img_pil = Image.open(f)
    c1, c2 = st.columns([1, 3])
    c1.image(img_pil, width=150)
    
    with c2:
        with st.spinner("🧠 Analyse IA..."):
            nom, cat, err = analyser_image_complete(img_pil, st.session_state.modele_ia)
        
        if nom:
            st.markdown(f"### 🔎 {nom}")
            
            with st.spinner("Scraping Multi-Plateforme..."):
                # 1. eBay (Prix de référence)
                ebay_p, ebay_n, ebay_img, ebay_url = scan_ebay_direct(nom)
                
                # 2. Leboncoin (Via DuckDuckGo)
                lbc_p, lbc_n, lbc_url = scan_moteur_flexible(nom, "leboncoin.fr")
                
                # 3. Rakuten (Via DuckDuckGo)
                rak_p, rak_n, rak_url = scan_moteur_flexible(nom, "fr.shopping.rakuten.com")
                
                # 4. Vinted (Via DuckDuckGo)
                vinted_p, vinted_n, vinted_url = 0, 0, generer_lien_google(nom, "vinted.fr")
                if "VETEMENT" in cat:
                    vinted_p, vinted_n, _ = scan_moteur_flexible(nom, "vinted.fr")
                
            st.divider()
            k1, k2, k3, k4 = st.columns(4)
            
            # Affichage Intelligent
            with k1:
                st.markdown("#### 🔵 eBay")
                if ebay_p > 0:
                    st.metric("Vendu", f"{ebay_p:.2f} €", f"{ebay_n} ref")
                    st.link_button("Voir", ebay_url)
                else: st.info("Pas de ref"); st.link_button("Chercher", ebay_url)
            
            with k2:
                st.markdown("#### 🟠 Leboncoin")
                if lbc_p > 0:
                    st.metric("Offre", f"{lbc_p:.0f} €", f"~{lbc_n} annonces")
                    st.link_button("Voir", lbc_url)
                else: st.info("Pas de ref"); st.link_button("Chercher", lbc_url)

            with k3:
                st.markdown("#### 🟣 Rakuten")
                if rak_p > 0:
                    st.metric("Pro", f"{rak_p:.0f} €", f"~{rak_n} annonces")
                    st.link_button("Voir", rak_url)
                else: st.info("Pas de ref"); st.link_button("Chercher", rak_url)

            with k4:
                st.markdown("#### 🔴 Vinted")
                if vinted_p > 0:
                    st.metric("Fripe", f"{vinted_p:.0f} €")
                    st.link_button("Voir", vinted_url)
                else: 
                    # Lien direct pour Vinted, souvent plus pertinent à l'œil humain
                    st.link_button("Ouvrir Vinted", vinted_url)

            # --- CALCUL DU PRIX GLOBAL ---
            # On ne prend que les prix > 0
            prix_trouves = [p for p in [ebay_p, lbc_p, rak_p, vinted_p] if p > 0]
            if prix_trouves:
                prix_moyen = sum(prix_trouves) / len(prix_trouves)
            else:
                prix_moyen = 0.0

            st.session_state.sd = {'n': nom, 'p': prix_moyen, 'i': ebay_img}

if 'sd' in st.session_state:
    d = st.session_state.sd
    st.write("---")
    
    if d['p'] > 0:
        st.success(f"💰 Cote Globale Estimée : **{d['p']:.2f} €**")
    else:
        st.warning("⚠️ Aucun prix automatique. À vous de jouer !")

    c1, c2, c3 = st.columns([1,1,2])
    p_final = c1.number_input("Prix Revente", value=float(d['p']))
    achat = c2.number_input("Prix Achat", 0.0)
    if c3.button("💾 Sauvegarder", use_container_width=True):
        if sheet:
            sheet.append_row([datetime.now().strftime("%d/%m/%Y"), d['n'], p_final, achat, "Trokia v8.4", d['i']])
            st.success("Enregistré !")
