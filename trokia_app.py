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
st.set_page_config(page_title="Trokia v17.8 : Multi-Images", page_icon="🧠", layout="wide")

# --- 1. L'IA EN CASCADE (MODIFIÉE POUR MULTI-IMAGES) ---

def analyser_image_multi_cascade(image_pil_list):
    """
    Tente d'analyser une liste d'images (3-4 photos) 
    en utilisant la cascade de modèles.
    """
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        
        # TA LISTE DE MODÈLES (v17.8)
        CANDIDATS = [
            "gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash-preview", 
            "gemini-3-pro-preview", "gemini-2.0-flash", "gemini-2.0-flash-001",
            "gemini-2.0-flash-lite", "gemini-exp-1206", "gemini-2.5-flash-lite",
            "gemini-flash-latest", "gemini-pro-latest", "gemini-1.5-flash", 
            "gemini-1.5-pro", "gemini-1.0-pro"
        ]
        
        last_error = ""
        for nom in CANDIDATS:
            try:
                model = genai.GenerativeModel(nom)
                # Prompt adapté pour plusieurs angles de vue
                prompt = "Analyse ces images produit (différents angles). Donne la CATÉGORIE et 4 modèles précis. Format:\n1. [Marque Modèle]\n2. [Marque Modèle]..."
                
                # Envoi de la liste d'images
                response = model.generate_content([prompt] + image_pil_list)
                text = response.text.strip()
                
                propositions = []
                lines = text.split('\n')
                for l in lines:
                    l = l.strip()
                    if l and (l[0].isdigit() or l.startswith("-") or l.startswith("*")):
                        clean_l = re.sub(r"^[\d\.\-\)\*]+\s*", "", l)
                        propositions.append(clean_l)
                
                if propositions:
                    st.toast(f"✅ Intelligence activée : {nom}")
                    return propositions, None
                    
            except Exception as e:
                last_error = str(e)
                if "429" in last_error: time.sleep(1)
                continue 

        return [], f"Épuisement des cerveaux. Dernière erreur : {last_error}"
    except Exception as e: return [], str(e)

# --- 2. MOTEUR DE RECHERCHE EAN & PRIX (v17.8) ---

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
            with st.spinner(f"🕵️ Identification EAN {query}..."):
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

            clean_results.append({
                "source": item.get("source", "Web"),
                "prix": p_float,
                "lien": item.get("link", ""),
                "titre": item.get("title", "Sans titre")
            })
            
        stats = {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0,
            "med": statistics.median(prices) if prices else 0,
            "count": len(prices)
        }
        return stats, clean_results, main_image, scan_query
    except Exception as e: return {"count":0}, [], "", query

# --- 3. BASE DE DONNÉES (v17.8) ---

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

if 'nom_final' not in st.session_state: reset_all()

st.title("🧠 Trokia v17.8 : Multi-Images")

c1, c2 = st.columns([4,1])
c1.caption(f"Analyse multi-photos activée | Cascade des 30 modèles")
if c2.button("🔄 Nouveau"): reset_all(); st.rerun()

t_ia, t_man = st.tabs(["📸 SCAN IA", "⌨️ MANUEL / EAN"])

with t_ia:
    # MODIFICATION : On autorise plusieurs fichiers
    uploaded_files = st.file_uploader("Prendre 3 ou 4 photos du produit", accept_multiple_files=True, type=['png', 'jpg', 'jpeg'])
    
    if uploaded_files:
        # Affichage des photos chargées
        imgs_pil = [Image.open(f) for f in uploaded_files]
        cols = st.columns(len(imgs_pil))
        for i, img in enumerate(imgs_pil):
            cols[i].image(img, use_container_width=True)

        if st.button("🧠 Lancer l'analyse des photos", type="primary", use_container_width=True):
            with st.spinner("🤖 Recherche du meilleur cerveau..."):
                p, err = analyser_image_multi_cascade(imgs_pil)
                if p: 
                    st.session_state.props = p
                else: 
                    st.error(err)

    if st.session_state.props:
        st.write("##### Cliquez sur le modèle identique :")
        cols = st.columns(2)
        for i, prop in enumerate(st.session_state.props):
            with cols[i%2]:
                if st.button(f"🔍 {prop}", use_container_width=True):
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
        with st.spinner("🌍 Scan des marchés..."):
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
                k2.metric("Médian", f"{stats['med']:.0f} €")
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
                    st.balloons(); st.success("Enregistré !"); time.sleep(1); reset_all(); st.rerun()
