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
from duckduckgo_search import DDGS
import statistics

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v16.1 : Stable", page_icon="🚀", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
}

# --- 1. FONCTIONS UTILITAIRES ---
def clean_price(text):
    try:
        found = re.findall(r"(\d+[\.,]?\d*)", text)
        for f in found:
            val = float(f.replace(",", "."))
            if 1 < val < 10000: return val
    except: pass
    return None

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
            "Analyse l'image. Donne la CATÉGORIE (VETEMENT, MEUBLE, TECH, AUTRE)."
            "Donne 4 modèles précis. Format:\nCAT: ...\n1. ...\n2. ...\n3. ...\n4. ..."
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

# --- LE CHANGEMENT MAJEUR EST ICI ---
def get_thumbnail(query):
    """
    Récupère une image via DuckDuckGo Images (Beaucoup plus stable qu'eBay)
    """
    try:
        # On cherche une image du produit
        results = DDGS().images(
            keywords=query,
            region="fr-fr",
            safesearch="off",
            max_results=1
        )
        if results:
            # On renvoie l'URL de la première image trouvée
            return results[0]['image']
    except Exception as e:
        print(f"Erreur Image: {e}")
    
    # Image par défaut propre
    return "https://via.placeholder.com/300x200.png?text=Image+Non+Dispo"

# --- 2. MOTEURS DE RECHERCHE PRIX ---
def generer_lien_google(nom, site):
    return f"https://www.google.com/search?q=site:{site}+{nom.replace(' ', '+')}"

def scan_smart_ddg(nom, site):
    try:
        query = f"site:{site} {nom}"
        results = DDGS().text(query, region='fr-fr', max_results=10)
        prices = []
        if results:
            for r in results:
                txt = (r.get('title', '') + " " + r.get('body', '')).lower()
                if '€' in txt or 'eur' in txt:
                    p = clean_price(txt)
                    if p: prices.append(p)
        if not prices: return 0, 0, generer_lien_google(nom, site)
        return statistics.median(prices), len(prices), generer_lien_google(nom, site)
    except: return 0, 0, generer_lien_google(nom, site)

def scan_ebay_ean_or_text(recherche):
    try:
        clean = re.sub(r'[^\w\s]', '', recherche).strip()
        url = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url, headers=HEADERS, timeout=5)
        prices = []
        raw_prices = re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text)
        for p in raw_prices:
            val_str = p[0] if p[0] else p[1]
            val = clean_price(val_str)
            if val: prices.append(val)
        
        # Pour l'image finale (stock), on tente quand même eBay car c'est le produit exact vendu
        img_url = ""
        soup = BeautifulSoup(r.text, 'html.parser')
        items = soup.select('.s-item')
        for item in items:
             img_tag = item.select_one('.s-item__image-img')
             if img_tag:
                 cand = img_tag.get('data-src') or img_tag.get('src')
                 if cand and 'ebayimg.com' in cand:
                     img_url = cand
                     break
        
        med = statistics.median(prices) if prices else 0
        return med, len(prices), img_url, url
    except: return 0, 0, "", ""

# --- SHEETS ---
def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds"])
        return gspread.authorize(creds).open("Trokia_DB").sheet1
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
st.title("🏆 Trokia v16.1 : Gold Edition")

if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

def reset_all():
    st.session_state.nom_final = ""
    st.session_state.go_search = False
    st.session_state.props = []
    st.session_state.props_imgs = []
    st.session_state.current_img = None
    st.toast("Mémoire effacée ! Prêt.")

if 'nom_final' not in st.session_state: reset_all()

# HEADER
col_logo, col_btn = st.columns([4, 1])
with col_logo: st.caption("L'outil de revente intelligent")
with col_btn:
    if st.button("🔄 Nouveau"):
        reset_all()
        st.rerun()

# ONGLETS
tab_photo, tab_manuel = st.tabs(["📸 SCANNER IA", "🔢 CODE BARRE / MANUEL"])

# TAB 1 : IA
with tab_photo:
    mode = st.radio("Source Image", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Prendre photo") if mode == "Caméra" else st.file_uploader("Upload Image")

    if f:
        if st.session_state.current_img != f.name:
            st.session_state.current_img = f.name
            with st.spinner("🤖 L'IA analyse l'objet..."):
                p, c, e = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
                if p: 
                    st.session_state.props = p
                    # On utilise la nouvelle fonction get_thumbnail (DuckDuckGo)
                    with st.spinner("🖼️ Récupération des images de référence..."):
                        st.session_state.props_imgs = [get_thumbnail(prop) for prop in p]
                    st.rerun()

        if st.session_state.props:
            st.markdown("##### 👀 Ça ressemble à quoi ?")
            cols = st.columns(len(st.session_state.props))
            for i, col in enumerate(cols):
                with col:
                    if i < len(st.session_state.props_imgs):
                        st.image(st.session_state.props_imgs[i], use_container_width=True)
                    st.caption(f"**{st.session_state.props[i]}**")
            
            choix = st.radio("Sélectionnez le modèle :", st.session_state.props + ["Autre"], horizontal=False)
            if st.button("✅ Valider ce modèle", type="primary", use_container_width=True):
                if choix == "Autre":
                    st.warning("Passez dans l'onglet 'Code Barre / Manuel' pour taper le nom exact.")
                else:
                    st.session_state.nom_final = choix
                    st.session_state.go_search = True
                    st.rerun()

# TAB 2 : MANUEL
with tab_manuel:
    st.info("💡 Scannez un Code Barre (EAN) pour une précision 100%.")
    with st.form(key='manual_search'):
        q_in = st.text_input("Recherche (Nom ou EAN)", placeholder="ex: 339189199222 ou iPhone 11")
        submit = st.form_submit_button("🔎 Lancer la recherche")
    
    if submit and q_in:
        st.session_state.nom_final = q_in
        st.session_state.go_search = True
        st.rerun()

# RESULTATS
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    is_ean = st.session_state.nom_final.isdigit() and len(st.session_state.nom_final) > 8
    titre_obj = f"Code EAN : {st.session_state.nom_final}" if is_ean else st.session_state.nom_final
    st.markdown(f"### 🎯 Analyse de : **{titre_obj}**")
    
    my_bar = st.progress(0, text="Connexion aux marchés...")
    
    # Scans
    ep, en, ei, eu = scan_ebay_ean_or_text(st.session_state.nom_final)
    my_bar.progress(40, text="Analyse Leboncoin & Rakuten...")
    
    lp, ln, lu = scan_smart_ddg(st.session_state.nom_final, "leboncoin.fr")
    rp, rn, ru = scan_smart_ddg(st.session_state.nom_final, "fr.shopping.rakuten.com")
    my_bar.progress(80, text="Vérification Vinted...")
    
    vp, vn, vu = 0, 0, generer_lien_google(st.session_state.nom_final, "vinted.fr")
    keywords_vinted = ['shirt', 'pantalon', 'veste', 'nike', 'adidas', 'sac', 'chaussure', 'parfum', 'lego']
    if is_ean or any(x in st.session_state.nom_final.lower() for x in keywords_vinted):
        vp, _, _ = scan_smart_ddg(st.session_state.nom_final, "vinted.fr")
    
    my_bar.progress(100, text="Terminé !")
    time.sleep(0.5)
    my_bar.empty()

    # Affichage Image Résultat (Si pas trouvée sur eBay, on prend celle de l'IA)
    img_display = ei if ei else (st.session_state.props_imgs[0] if st.session_state.props_imgs else "")
    if img_display:
        col_i1, col_i2 = st.columns([1, 4])
        col_i1.image(img_display, width=150, caption="Produit identifié")

    # Dashboard
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("eBay (Vendu)", f"{ep:.2f} €" if ep else "-", f"{en} vtes"); k1.link_button("Voir", eu)
    k2.metric("LBC (Offre)", f"{lp:.0f} €" if lp else "-"); k2.link_button("Voir", lu)
    k3.metric("Rakuten (Pro)", f"{rp:.0f} €" if rp else "-"); k3.link_button("Voir", ru)
    k4.metric("Vinted", f"{vp:.0f} €" if vp else "-"); k4.link_button("Voir", vu)

    # Calculateur
    st.write("---")
    st.markdown("#### 💰 Calculateur de Profit")
    valid_prices = [x for x in [ep, lp, rp, vp] if x > 0]
    sugg = statistics.median(valid_prices) if valid_prices else 0.0
    
    c1, c2, c3 = st.columns(3)
    vente = c1.number_input("Prix Vente Est. (€)", value=float(sugg), step=1.0)
    achat = c2.number_input("Prix Achat (€)", 0.0, step=1.0)
    marge = vente - achat - (vente * 0.15)
    c3.metric("Marge Nette", f"{marge:.2f} €", delta="Gagnant" if marge > 0 else "Perdant")

    if st.button("💾 Enregistrer dans le Stock", use_container_width=True):
        if sheet:
            img_save = img_display if img_display else "https://via.placeholder.com/150"
            sheet.append_row([datetime.now().strftime("%d/%m %H:%M"), st.session_state.nom_final, vente, achat, f"{marge:.2f}", img_save])
            st.balloons()
            st.success("✅ Stock mis à jour !")
            time.sleep(2)
            st.session_state.go_search = False
            st.rerun()

# Historique
if sheet:
    df = get_historique(sheet)
    if not df.empty:
        st.write("---")
        st.markdown("### 📋 Historique de la Session")
        st.dataframe(df, use_container_width=True, hide_index=True)
