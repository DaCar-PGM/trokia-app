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
st.set_page_config(page_title="Trokia v14 : Ultimate Hybrid", page_icon="💎", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
}

# --- 1. IA & VISUEL ---
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
            "Analyse cette image. Donne la CATÉGORIE (VETEMENT, MEUBLE, TECH, AUTRE)."
            "Liste 4 modèles précis. Format:\nCAT: ...\n1. ...\n2. ...\n3. ...\n4. ..."
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

def get_thumbnail(query):
    """Récupère une image de référence pour valider le produit"""
    try:
        clean = re.sub(r'[^\w\s]', '', query).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}"
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select('.s-item')
        for item in items:
            img_tag = item.select_one('.s-item__image-img')
            if not img_tag: img_tag = item.select_one('img')
            if img_tag:
                cand = img_tag.get('data-src') or img_tag.get('src')
                if cand and 'ebayimg.com' in cand: return cand
    except: pass
    return "https://via.placeholder.com/300x200.png?text=Pas+d'image"

# --- 2. MOTEURS DE PRIX ---
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
        
        img_url = ""
        items = soup.select('.s-item')
        for item in items:
             img_tag = item.select_one('.s-item__image-img')
             if img_tag:
                 cand = img_tag.get('data-src') or img_tag.get('src')
                 if cand and 'ebayimg.com' in cand:
                     img_url = cand
                     break
        return (sum(prices)/len(prices) if prices else 0), len(prices), img_url, url
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
st.title("💎 Trokia v14 : L'Hybride")

if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

# VARIABLES GLOBALES ET STATE
if 'nom_final' not in st.session_state: st.session_state.nom_final = ""
if 'go_search' not in st.session_state: st.session_state.go_search = False
if 'props' not in st.session_state: st.session_state.props = []
if 'props_imgs' not in st.session_state: st.session_state.props_imgs = []
if 'current_img' not in st.session_state: st.session_state.current_img = None

# FONCTION DE RESET GLOBAL
def reset_all():
    st.session_state.nom_final = ""
    st.session_state.go_search = False
    st.session_state.props = []
    st.session_state.props_imgs = []
    st.session_state.current_img = None

if st.button("🔄 Nouveau Scan / Reset"):
    reset_all()
    st.rerun()

# --- ONGLETS PRINCIPAUX ---
tab_photo, tab_manuel = st.tabs(["📸 Scan Photo (IA)", "⌨️ Recherche Manuelle / EAN"])

# --- ONGLET 1 : IA PHOTO ---
with tab_photo:
    mode = st.radio("Mode", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Scanner") if mode == "Caméra" else st.file_uploader("Image")

    if f:
        if st.session_state.current_img != f.name:
            st.session_state.current_img = f.name
            with st.spinner("🤖 Analyse IA..."):
                p, c, e = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
                if p: 
                    st.session_state.props = p
                    imgs = [get_thumbnail(prop) for prop in p]
                    st.session_state.props_imgs = imgs
                    st.rerun()

        if st.session_state.props:
            st.write("#### Choisissez le bon modèle :")
            cols = st.columns(len(st.session_state.props))
            for i, col in enumerate(cols):
                with col:
                    if i < len(st.session_state.props_imgs):
                        st.image(st.session_state.props_imgs[i], use_container_width=True)
                    st.caption(f"**{st.session_state.props[i]}**")
            
            choix = st.radio("Votre choix :", st.session_state.props + ["Autre"], horizontal=False)
            if st.button("Valider ce modèle", type="primary"):
                if choix == "Autre":
                    st.warning("Passez en mode 'Recherche Manuelle' pour taper le nom.")
                else:
                    st.session_state.nom_final = choix
                    st.session_state.go_search = True
                    st.rerun()

# --- ONGLET 2 : MANUEL / CODE BARRE ---
with tab_manuel:
    st.info("💡 Scannez un code-barre ici ou tapez un nom (ex: 'PlayStation 5').")
    
    # Formulaire pour gérer la touche "Entrée"
    with st.form(key='search_form'):
        query_input = st.text_input("Recherche (Nom ou EAN)")
        submit_button = st.form_submit_button(label='🔎 Lancer la recherche')
        
    if submit_button and query_input:
        st.session_state.nom_final = query_input
        st.session_state.go_search = True
        st.rerun()

# --- SECTION COMMUNE : RÉSULTATS & PRIX ---
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    st.markdown(f"### 🎯 Résultat pour : **{st.session_state.nom_final}**")
    
    # Image de référence (si pas déjà chargée via IA)
    if not st.session_state.props_imgs:
        ref_img = get_thumbnail(st.session_state.nom_final)
        c_img, _ = st.columns([1,3])
        c_img.image(ref_img, width=150, caption="Réf. Marché")
    
    with st.spinner("Scraping des prix..."):
        ep, en, ei, eu = scan_ebay(st.session_state.nom_final)
        lp, ln, lu = scan_bing(st.session_state.nom_final, "leboncoin.fr")
        rp, rn, ru = scan_bing(st.session_state.nom_final, "fr.shopping.rakuten.com")
        vp, vn, vu = 0, 0, generer_lien(st.session_state.nom_final, "vinted.fr")
        # On tente Vinted si le nom contient des mots clés de vêtements (simplifié)
        if any(x in st.session_state.nom_final.lower() for x in ['shirt', 'pantalon', 'veste', 'nike', 'adidas', 'zara']):
            vp, _, _ = scan_bing(st.session_state.nom_final, "vinted.fr")

    # DASHBOARD
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("eBay (Cote)", f"{ep:.2f} €" if ep else "-", f"{en} vtes"); k1.link_button("Voir", eu)
    k2.metric("LBC", f"{lp:.0f} €" if lp else "-"); k2.link_button("Voir", lu)
    k3.metric("Rakuten", f"{rp:.0f} €" if rp else "-"); k3.link_button("Voir", ru)
    k4.metric("Vinted", f"{vp:.0f} €" if vp else "-"); k4.link_button("Voir", vu)

    # CALCULATRICE
    st.write("---")
    st.markdown("#### 💰 Calculateur de Marge")
    sugg = ep if ep > 0 else (lp if lp > 0 else 0.0)
    
    cc1, cc2, cc3 = st.columns(3)
    pv = cc1.number_input("Vente (€)", value=float(sugg), step=1.0)
    pa = cc2.number_input("Achat (€)", 0.0, step=1.0)
    marge = pv - pa - (pv * 0.15)
    cc3.metric("Marge Nette", f"{marge:.2f} €", delta="Profit" if marge > 0 else "Perte")

    if st.button("💾 Sauvegarder", use_container_width=True):
        if sheet:
            img_save = ei if ei else (st.session_state.props_imgs[0] if st.session_state.props_imgs else "")
            sheet.append_row([datetime.now().strftime("%d/%m %H:%M"), st.session_state.nom_final, pv, pa, f"{marge:.2f}", img_save])
            st.success("Enregistré !")
            time.sleep(1)
            # Reset partiel pour enchainer
            st.session_state.go_search = False
            st.rerun()

# HISTORIQUE
st.write("---")
st.markdown("### 📋 Historique")
if sheet:
    df = get_historique(sheet)
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
