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
from serpapi import GoogleSearch
import statistics

# --- CONFIGURATION (v17.8) ---
st.set_page_config(page_title="Trokia v17.8 : Visual Preview", page_icon="🧠", layout="wide")

# --- 1. FONCTION D'APERÇU VISUEL (NOUVEAU) ---

def get_visual_hint(query):
    """Cherche une petite image de référence pour le modèle suggéré"""
    try:
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_images",
            "q": query,
            "num": "1"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        return results.get("images_results", [])[0].get("thumbnail")
    except:
        return None

# --- 2. L'IA EN CASCADE (MULTI-IMAGES) ---

def analyser_image_multi_cascade(image_pil_list):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        CANDIDATS = [
            "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview", 
            "gemini-3-pro-preview", "gemini-2.0-flash", "gemini-2.0-flash-001",
            "gemini-2.0-flash-lite", "gemini-exp-1206", "gemini-2.5-flash-lite",
            "gemini-flash-latest", "gemini-pro-latest", "gemini-1.5-flash", 
            "gemini-1.5-pro", "gemini-1.0-pro"
        ]
        
        for nom in CANDIDATS:
            try:
                model = genai.GenerativeModel(nom)
                prompt = "Analyse ces images produit. Donne la CATÉGORIE et 4 modèles précis. Format:\n1. [Marque Modèle]\n2. [Marque Modèle]..."
                response = model.generate_content([prompt] + image_pil_list)
                text = response.text.strip()
                
                propositions = []
                for l in text.split('\n'):
                    l = l.strip()
                    if l and (l[0].isdigit() or l.startswith("-") or l.startswith("*")):
                        clean_l = re.sub(r"^[\d\.\-\)\*]+\s*", "", l)
                        propositions.append(clean_l)
                
                if propositions:
                    return propositions, nom
            except:
                continue 
        return [], "Échec IA"
    except Exception as e: return [], str(e)

# --- 3. MOTEUR DE RECHERCHE & PRIX (v17.8) ---

def identifier_ean_via_google(ean):
    try:
        params = {"api_key": st.secrets["SERPAPI_KEY"], "engine": "google", "q": ean, "gl": "fr", "hl": "fr"}
        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        if organic: return organic[0].get("title", "").split(" - ")[0].split(" | ")[0]
    except: pass
    return None

def scan_google_shopping_world(query):
    try:
        scan_query = query
        if query.isdigit() and len(query) > 8:
            nom_traduit = identifier_ean_via_google(query)
            if nom_traduit: scan_query = nom_traduit
        
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_shopping",
            "q": scan_query,
            "google_domain": "google.fr",
            "gl": "fr", "hl": "fr", "num": "20"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        shopping_results = results.get("shopping_results", [])
        
        prices = []; clean_results = []; main_image = ""
        for item in shopping_results:
            prix_txt = str(item.get("price", "0")).replace("\xa0€", "").replace("€", "").replace(",", ".").strip()
            try:
                found = re.findall(r"(\d+[\.,]?\d*)", prix_txt)
                p_float = float(found[0]) if found else 0
                if p_float > 1: prices.append(p_float)
            except: p_float = 0
            if not main_image and item.get("thumbnail"): main_image = item.get("thumbnail")
            clean_results.append({"source": item.get("source", "Web"), "prix": p_float, "lien": item.get("link", ""), "titre": item.get("title", "")})
            
        stats = {"min": min(prices) if prices else 0, "max": max(prices) if prices else 0, "med": statistics.median(prices) if prices else 0, "count": len(prices)}
        return stats, clean_results, main_image, scan_query
    except: return {"count":0}, [], "", query

# --- 4. BASE DE DONNÉES (v17.8) ---

def connecter_sheets():
    try:
        json_str = st.secrets["service_account_info"]
        creds_dict = json.loads(json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds"])
        return gspread.authorize(creds).open("Trokia_DB").sheet1
    except: return None

# --- UI STREAMLIT ---

sheet = connecter_sheets()

def reset_all():
    st.session_state.nom_final = ""; st.session_state.go_search = False
    st.session_state.props = []; st.session_state.current_img = None
    st.session_state.scan_results = None; st.session_state.nom_reel_produit = ""
    st.session_state.prop_images = {} # Stockage des aperçus

if 'nom_final' not in st.session_state: reset_all()

st.title("🧠 Trokia v17.8 : Multi-Images")

# Header
c1, c2 = st.columns([4,1])
c1.caption("Analyse multi-photos | Cascade des 30 modèles")
if c2.button("🔄 Nouveau"): reset_all(); st.rerun()

t_ia, t_man = st.tabs(["📸 SCAN IA", "⌨️ MANUEL / EAN"])

with t_ia:
    uploaded_files = st.file_uploader("Prendre 3 ou 4 photos du produit", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    
    if uploaded_files:
        imgs_pil = [Image.open(f) for f in uploaded_files]
        # MODIFICATION : Taille des images réduite (vignettes de 120px)
        st.write("##### Vos photos :")
        cols_v = st.columns(len(imgs_pil) if len(imgs_pil) < 6 else 6)
        for i, img in enumerate(imgs_pil):
            cols_v[i].image(img, width=120)

        if st.button("🧠 Lancer l'analyse", type="primary", use_container_width=True):
            with st.spinner("Recherche du modèle..."):
                p, _ = analyser_image_multi_cascade(imgs_pil)
                if p: 
                    st.session_state.props = p
                    # On va chercher les images de référence tout de suite
                    with st.spinner("Chargement des aperçus..."):
                        for item in p:
                            st.session_state.prop_images[item] = get_visual_hint(item)
                else: 
                    st.error("Rien trouvé.")

    # MODIFICATION : Suggestions avec Images
    if st.session_state.props:
        st.write("---")
        st.write("##### Cliquez sur le modèle identique :")
        cols_p = st.columns(4)
        for i, prop in enumerate(st.session_state.props):
            with cols_p[i]:
                # Affichage de l'image de référence si trouvée
                img_url = st.session_state.prop_images.get(prop)
                if img_url:
                    st.image(img_url, use_container_width=True)
                else:
                    st.caption("Pas d'image")
                
                if st.button(prop, key=f"btn_{i}", use_container_width=True):
                    st.session_state.nom_final = prop; st.session_state.go_search = True; st.rerun()

with t_man:
    with st.form("manuel"):
        q = st.text_input("Nom du produit ou Code-barre")
        if st.form_submit_button("Lancer l'analyse") and q:
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# RÉSULTATS (v17.8)
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    if not st.session_state.scan_results:
        with st.spinner("🌍 Scan mondial..."):
            stats, details, img_ref, nom_reel = scan_google_shopping_world(st.session_state.nom_final)
            st.session_state.scan_results = (stats, details, img_ref)
            st.session_state.nom_reel_produit = nom_reel
    
    if st.session_state.scan_results:
        stats, details, img_ref = st.session_state.scan_results
        if stats["count"] > 0:
            st.markdown(f"### 🎯 Produit : **{st.session_state.nom_reel_produit}**")
            ci, cs = st.columns([1, 3])
            if img_ref: ci.image(img_ref, width=150)
            with cs:
                k1, k2, k3 = st.columns(3)
                k1.metric("Prix Bas", f"{stats['min']:.0f} €")
                k2.metric("Médian", f"{stats['med']:.0f} €", f"{stats['count']} offres")
                k3.metric("Prix Haut", f"{stats['max']:.0f} €")
            
            st.write("---")
            c_offres = st.columns(5)
            for i, item in enumerate(details[:10]):
                with c_offres[i%5]:
                    st.metric(item["source"], f"{item['prix']:.0f} €")
                    if item["lien"]: st.link_button("Voir", item["lien"])
            
            st.write("---")
            calc1, calc2, calc3 = st.columns(3)
            pv = calc1.number_input("Vente (€)", value=float(stats['med']))
            pa = calc2.number_input("Achat (€)", 0.0)
            marge = pv - pa - (pv * 0.15)
            calc3.metric("Marge Nette", f"{marge:.2f} €")
            
            if st.button("💾 Enregistrer", use_container_width=True):
                if sheet:
                    sheet.append_row([datetime.now().strftime("%d/%m"), st.session_state.nom_reel_produit, pv, pa, f"{marge:.2f}", img_ref])
                    st.balloons(); st.success("OK"); time.sleep(1); reset_all(); st.rerun()
