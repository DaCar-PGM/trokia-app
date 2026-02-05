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
st.set_page_config(page_title="Trokia v13 : Visual Selector", page_icon="👁️", layout="wide")

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
            "Liste 4 propositions de modèles précis qui pourraient correspondre visuellement."
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

# --- 2. RECUPERATION VISUELLE ---
def get_thumbnail(query):
    """Récupère UNE image miniature pour illustrer une proposition"""
    try:
        clean = re.sub(r'[^\w\s]', '', query).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}"
        r = requests.get(url, headers=HEADERS, timeout=3)
        soup = BeautifulSoup(r.text, 'html.parser')
        img = soup.select_one('.s-item__image-wrapper img')
        if img:
            src = img.get('src')
            if "http" in src: return src
    except: pass
    return "https://via.placeholder.com/150?text=Pas+d'image"

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
    try:
        data = sheet.get_all_values()
        if len(data) > 1:
            headers = data[0]
            rows = data[-5:]
            rows.reverse()
            return pd.DataFrame(rows, columns=headers)
    except: pass
    return pd.DataFrame()

# --- UI ---
st.title("💼 Trokia v13 : Visual Selector")

if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

# STATE MANAGEMENT
if 'props' not in st.session_state: st.session_state.props = []
if 'props_imgs' not in st.session_state: st.session_state.props_imgs = [] # Pour stocker les images des choix
if 'cat' not in st.session_state: st.session_state.cat = ""
if 'current_img' not in st.session_state: st.session_state.current_img = None

# RESET
if st.button("🔄 Nouveau Scan"):
    st.session_state.props = []
    st.session_state.props_imgs = []
    st.session_state.cat = ""
    st.session_state.current_img = None
    st.rerun()

mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Image")

# LOGIQUE
if f:
    if st.session_state.current_img != f.name:
        st.session_state.current_img = f.name
        with st.spinner("🤖 L'IA identifie les modèles potentiels..."):
            p, c, e = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
            if p: 
                st.session_state.props = p
                st.session_state.cat = c
                
                # NOUVEAU : On récupère les images pour chaque proposition
                with st.spinner("📸 Récupération des visuels comparatifs..."):
                    imgs = []
                    for prop in p:
                        imgs.append(get_thumbnail(prop))
                    st.session_state.props_imgs = imgs
                st.rerun()

    # SECTION 1 : COMPARAISON VISUELLE
    st.write("### 1️⃣ Quel modèle correspond le mieux ?")
    
    if st.session_state.props:
        # On affiche les 4 choix en colonnes avec images
        cols = st.columns(len(st.session_state.props))
        
        # On crée un sélecteur propre
        choix_dict = {} # Pour lier le nom à l'index
        
        for i, col in enumerate(cols):
            with col:
                # Affichage de l'image de référence
                st.image(st.session_state.props_imgs[i], use_container_width=True)
                st.caption(f"**{st.session_state.props[i]}**")
        
        # Sélecteur
        option_choisie = st.radio(
            "Sélectionnez le modèle identique :", 
            st.session_state.props + ["Autre (Je saisis le nom)"],
            horizontal=False
        )
        
        if option_choisie == "Autre (Je saisis le nom)":
            nom_final = st.text_input("Saisissez le modèle exact :")
        else:
            nom_final = option_choisie
            
        go = st.button("✅ C'est celui-là -> ESTIMER", type="primary", use_container_width=True)

        # SECTION 2 : ESTIMATION
        if go and nom_final:
            st.write("---")
            with st.spinner(f"Calcul de la cote pour : {nom_final}..."):
                ep, en, ei, eu = scan_ebay(nom_final)
                lp, ln, lu = scan_bing(nom_final, "leboncoin.fr")
                rp, rn, ru = scan_bing(nom_final, "fr.shopping.rakuten.com")
                vp, vn, vu = 0, 0, generer_lien(nom_final, "vinted.fr")
                if "VETEMENT" in st.session_state.cat: vp, _, _ = scan_bing(nom_final, "vinted.fr")

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("eBay (Cote)", f"{ep:.2f} €" if ep else "-", f"{en} vtes"); k1.link_button("Voir", eu)
            k2.metric("LBC", f"{lp:.0f} €" if lp else "-"); k2.link_button("Voir", lu)
            k3.metric("Rakuten", f"{rp:.0f} €" if rp else "-"); k3.link_button("Voir", ru)
            k4.metric("Vinted", f"{vp:.0f} €" if vp else "-"); k4.link_button("Voir", vu)

            st.write("---")
            st.markdown("### 💰 Calculateur de Marge")
            sugg = ep if ep > 0 else (lp if lp > 0 else 0.0)
            
            col_c1, col_c2, col_c3 = st.columns(3)
            pv = col_c1.number_input("Vente (€)", value=float(sugg), step=1.0)
            pa = col_c2.number_input("Achat (€)", 0.0, step=1.0)
            marge = pv - pa - (pv * 0.15)
            
            col_c3.metric("Marge Nette (approx)", f"{marge:.2f} €", delta="Profit" if marge > 0 else "Perte")

            if st.button("💾 Sauvegarder", use_container_width=True):
                if sheet:
                    sheet.append_row([datetime.now().strftime("%d/%m %H:%M"), nom_final, pv, pa, f"{marge:.2f}", ei])
                    st.success("Stock mis à jour !")
                    time.sleep(1)
                    st.rerun()

    else:
        # Pas encore d'analyse
        st.info("Prenez une photo pour démarrer.")

# HISTORIQUE
st.write("---")
st.markdown("### 📋 Historique")
if sheet:
    df = get_historique(sheet)
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
