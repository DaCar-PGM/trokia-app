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
st.set_page_config(page_title="Trokia v12 : Business Pro", page_icon="💼", layout="wide")

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

def analyser_image_multi(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        prompt = (
            "Analyse cette image. Donne-moi la CATÉGORIE (VETEMENT, MEUBLE, TECH, AUTRE)."
            "Liste 4 propositions de modèles précis."
            "Format:\nCAT: ...\n1. ...\n2. ...\n3. ...\n4. ..."
        )
        response = model.generate_content([prompt, image_pil])
        text = response.text.strip()
        cat = "AUTRE"
        propositions = []
        lines = text.split('\n')
        for l in lines:
            if l.startswith("CAT:"): cat = l.replace("CAT:", "").strip()
            elif l[0].isdigit() and "." in l: propositions.append(l.split(".", 1)[1].strip())
        return propositions, cat, None
    except Exception as e: return [], "AUTRE", str(e)

# --- 2. OUTILS ---
def recuperer_images_exemples(query):
    try:
        clean = re.sub(r'[^\w\s]', '', query).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}"
        r = requests.get(url, headers=HEADERS, timeout=4)
        soup = BeautifulSoup(r.text, 'html.parser')
        images = []
        imgs = soup.select('.s-item__image-wrapper img')
        for img in imgs:
            src = img.get('src')
            if src and "http" in src: images.append(src)
            if len(images) >= 3: break
        return images
    except: return []

def generer_lien(nom, site): return f"https://www.google.com/search?q=site:{site}+{nom.replace(' ', '+')}"

def scan_bing(nom, site):
    try:
        url = f"https://www.bing.com/search?q=site:{site}+{nom.replace(' ', '+')}"
        r = requests.get(url, headers=HEADERS, timeout=5)
        prices = [float(p.replace(",", ".").replace(" ", "")) for p in re.findall(r"(\d+[\.,]?\d*)\s?(?:€|EUR)", r.text) if 2 < float(p.replace(",", ".").replace(" ", "")) < 5000]
        return (sum(prices)/len(prices) if prices else 0), len(prices), generer_lien(nom, site)
    except: return 0, 0, generer_lien(nom, site)

def scan_ebay(recherche):
    try:
        clean = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url, headers=HEADERS, timeout=6)
        prices = [float(p.replace(",", ".").replace(" ", "")) for p in re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text) for x in p if x and 2 < float(x.replace(",", ".").replace(" ", "")) < 5000]
        soup = BeautifulSoup(r.text, 'html.parser')
        img = soup.select_one('.s-item__image-wrapper img')['src'] if soup.select_one('.s-item__image-wrapper img') else ""
        return (sum(prices)/len(prices) if prices else 0), len(prices), img, url
    except: return 0, 0, "", ""

# --- SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds"])
        client = gspread.authorize(creds)
        return client.open("Trokia_DB").sheet1
    except: return None

def get_historique(sheet):
    """Récupère les 5 dernières lignes pour l'affichage"""
    try:
        data = sheet.get_all_values()
        if len(data) > 1:
            headers = data[0]
            rows = data[-5:] # Les 5 derniers
            rows.reverse() # Du plus récent au plus vieux
            return pd.DataFrame(rows, columns=headers)
    except: pass
    return pd.DataFrame()

# --- UI ---
st.title("💼 Trokia v12 : Business Pro")

if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

if 'props' not in st.session_state: st.session_state.props = []
if 'cat' not in st.session_state: st.session_state.cat = ""
if 'current_img' not in st.session_state: st.session_state.current_img = None
if 'reset_trigger' not in st.session_state: st.session_state.reset_trigger = False

# BOUTON RESET EN HAUT
if st.button("🔄 Nouveau Scan (Reset)"):
    st.session_state.props = []
    st.session_state.cat = ""
    st.session_state.current_img = None
    st.rerun()

mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Image")

# LOGIQUE PRINCIPALE
if f:
    if st.session_state.current_img != f.name:
        st.session_state.current_img = f.name
        with st.spinner("Analyse IA..."):
            p, c, e = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
            if p: st.session_state.props = p; st.session_state.cat = c; st.rerun()

    c1, c2 = st.columns([1, 2])
    c1.image(f, width=150)
    
    with c2:
        st.caption(f"Catégorie : {st.session_state.cat}")
        opts = st.session_state.props + ["Autre"]
        choix = st.radio("Modèle ?", opts, label_visibility="collapsed")
        nom_final = st.text_input("Nom exact", value=(choix if choix != "Autre" else ""))

        if nom_final:
            refs = recuperer_images_exemples(nom_final)
            if refs:
                k1, k2, k3 = st.columns(3)
                try: k1.image(refs[0]) 
                except: pass
                try: k2.image(refs[1]) 
                except: pass
                try: k3.image(refs[2]) 
                except: pass
        
        go = st.button("✅ Valider & Estimer", type="primary", use_container_width=True)

    if go and nom_final:
        st.divider()
        with st.spinner("Scraping..."):
            ep, en, ei, eu = scan_ebay(nom_final)
            lp, ln, lu = scan_bing(nom_final, "leboncoin.fr")
            rp, rn, ru = scan_bing(nom_final, "fr.shopping.rakuten.com")
            vp, vn, vu = 0, 0, generer_lien(nom_final, "vinted.fr")
            if "VETEMENT" in st.session_state.cat: vp, _, _ = scan_bing(nom_final, "vinted.fr")

        # DASHBOARD PRIX
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("eBay (Cote)", f"{ep:.2f} €" if ep else "-", f"{en} vtes"); k1.link_button("Voir", eu)
        k2.metric("LBC", f"{lp:.0f} €" if lp else "-"); k2.link_button("Voir", lu)
        k3.metric("Rakuten", f"{rp:.0f} €" if rp else "-"); k3.link_button("Voir", ru)
        k4.metric("Vinted", f"{vp:.0f} €" if vp else "-"); k4.link_button("Voir", vu)

        # CALCULATEUR DE PROFIT (NOUVEAU !)
        st.write("---")
        st.markdown("### 💰 Calculateur de Profit")
        
        # On suggère un prix de vente (eBay ou moyenne)
        sugg = ep if ep > 0 else (lp if lp > 0 else 0.0)
        
        col_calc1, col_calc2, col_calc3 = st.columns(3)
        prix_vente = col_calc1.number_input("Prix Vente Espéré (€)", value=float(sugg), step=1.0)
        prix_achat = col_calc2.number_input("Prix Achat (€)", 0.0, step=1.0)
        
        # Estimation frais (ex: 13% eBay + Port) -> On simplifie à 15% de frais plateforme
        frais_estimes = prix_vente * 0.15
        marge_nette = prix_vente - prix_achat - frais_estimes
        
        col_calc3.metric(
            label="Marge Nette Estimée (approx)", 
            value=f"{marge_nette:.2f} €", 
            delta="Profit" if marge_nette > 0 else "Perte",
            delta_color="normal"
        )
        st.caption(f"*Inclut une estimation de 15% de frais de plateforme ({frais_estimes:.2f}€).")

        if st.button("💾 Sauvegarder dans le Stock", use_container_width=True):
            if sheet:
                sheet.append_row([datetime.now().strftime("%d/%m/%Y %H:%M"), nom_final, prix_vente, prix_achat, f"Marge: {marge_nette:.2f}€", ei])
                st.success("Sauvegardé !")
                time.sleep(1) # Petit temps pour laisser Sheets écrire
                st.rerun() # Rafraîchir pour mettre à jour l'historique

# --- SECTION HISTORIQUE (NOUVEAU !) ---
st.write("---")
st.markdown("### 📋 Derniers Objets Scannés")
if sheet:
    df_hist = get_historique(sheet)
    if not df_hist.empty:
        # On affiche juste les colonnes utiles
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.info("Historique vide pour le moment.")
