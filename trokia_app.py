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

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v17.5 : Safe Mode", page_icon="🛡️", layout="wide")

# --- 1. FONCTIONS IA (Avec Anti-Erreur 429) ---
def configurer_modele():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        # CORRECTION : On force le modèle 1.5 Flash qui a de meilleurs quotas
        # Au lieu de prendre le premier venu qui peut être le 2.5 limité
        return "gemini-1.5-flash"
    except: return "gemini-1.5-flash"

def analyser_image_multi(image_pil, modele_nom):
    # SYSTÈME DE RETRY (3 tentatives)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(modele_nom)
            prompt = "Analyse l'image. Donne la CATÉGORIE et 4 modèles précis. Format:\n1. [Marque Modèle]\n2. [Marque Modèle]..."
            
            # On lance l'appel
            response = model.generate_content([prompt, image_pil])
            text = response.text.strip()
            
            propositions = []
            lines = text.split('\n')
            for l in lines:
                l = l.strip()
                if l and (l[0].isdigit() or l.startswith("-") or l.startswith("*")):
                    clean_l = re.sub(r"^[\d\.\-\)\*]+\s*", "", l)
                    propositions.append(clean_l)
            return propositions, None
            
        except Exception as e:
            error_str = str(e)
            # Si c'est l'erreur 429 (Quota), on attend un peu et on recommence
            if "429" in error_str or "quota" in error_str.lower():
                time.sleep(2) # On fait une pause de 2 secondes
                continue # On réessaie
            else:
                # Si c'est une autre erreur, on arrête
                return [], error_str
    
    return [], "Serveur IA saturé (Trop de demandes rapides). Attendez 1 min."

# --- 2. FONCTIONS DE RECHERCHE ---

def identifier_ean_via_google(ean):
    try:
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google",
            "q": ean,
            "google_domain": "google.fr",
            "gl": "fr",
            "hl": "fr"
        }
        search = GoogleSearch(params)
        results = search.get_dict()
        organic = results.get("organic_results", [])
        if organic:
            titre_brut = organic[0].get("title", "")
            titre_propre = titre_brut.split(" - ")[0].split(" | ")[0]
            return titre_propre
    except: pass
    return None

def scan_google_shopping_world(query):
    try:
        scan_query = query
        is_ean = query.isdigit() and len(query) > 8
        
        if is_ean:
            with st.spinner(f"🕵️ Identification EAN {query}..."):
                nom_traduit = identifier_ean_via_google(query)
                if nom_traduit:
                    st.toast(f"Identifié : {nom_traduit}")
                    scan_query = nom_traduit
        
        params = {
            "api_key": st.secrets["SERPAPI_KEY"],
            "engine": "google_shopping",
            "q": scan_query,
            "google_domain": "google.fr",
            "gl": "fr",
            "hl": "fr",
            "num": "20"
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        
        # Gestion erreur SerpApi (ex: clé invalide ou quota épuisé)
        if "error" in results:
             return {"count":0, "error": results["error"]}, [], "", query

        shopping_results = results.get("shopping_results", [])
        
        prices = []
        clean_results = []
        main_image = ""
        
        for item in shopping_results:
            prix_txt = str(item.get("price", "0")).replace("\xa0€", "").replace("€", "").replace(",", ".").strip()
            try:
                found = re.findall(r"(\d+[\.,]?\d*)", prix_txt)
                if found:
                    p_float = float(found[0])
                    if p_float > 1: prices.append(p_float)
                else: p_float = 0
            except: p_float = 0
            
            if not main_image and item.get("thumbnail"): main_image = item.get("thumbnail")

            link_final = item.get("link")
            if not link_final: link_final = item.get("product_link", "")

            clean_results.append({
                "source": item.get("source", "Web"),
                "prix": p_float,
                "lien": link_final,
                "titre": item.get("title", "Sans titre")
            })
            
        stats = {
            "min": min(prices) if prices else 0,
            "max": max(prices) if prices else 0,
            "med": statistics.median(prices) if prices else 0,
            "count": len(prices)
        }
        return stats, clean_results, main_image, scan_query

    except Exception as e:
        return {"count":0}, [], "", query

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
            headers = data[0]; rows = data[-5:]; rows.reverse()
            return pd.DataFrame(rows, columns=headers)
    except: pass
    return pd.DataFrame()

# --- UI ---
st.title("🛡️ Trokia v17.5 : Safe Mode")
if 'modele_ia' not in st.session_state: st.session_state.modele_ia = configurer_modele()
sheet = connecter_sheets()

def reset_all():
    st.session_state.nom_final = ""; st.session_state.go_search = False
    st.session_state.props = []; st.session_state.current_img = None
    st.session_state.scan_results = None
    st.session_state.nom_reel_produit = ""

if 'nom_final' not in st.session_state: reset_all()

# Header
c_logo, c_btn = st.columns([4,1])
c_logo.caption("Scan Mondial + Anti-Crash")
if c_btn.button("🔄 Reset Total"): reset_all(); st.rerun()

# Onglets
tab_photo, tab_manuel = st.tabs(["📸 IA VISUELLE", "⌨️ MANUEL / EAN"])

with tab_photo:
    mode = st.radio("Source", ["Caméra", "Galerie"], horizontal=True, label_visibility="collapsed")
    f = st.camera_input("Photo") if mode == "Caméra" else st.file_uploader("Image")
    
    if f:
        # Bouton Secours
        if st.button("⚡ Forcer (si bloqué)", type="secondary"):
            st.session_state.current_img = None; st.rerun()

    if f and st.session_state.current_img != f.name:
        st.session_state.current_img = f.name
        st.session_state.go_search = False 
        st.session_state.scan_results = None
        
        with st.spinner("🤖 Identification IA (Tentative auto)..."):
            # On appelle la fonction blindée
            p, err = analyser_image_multi(Image.open(f), st.session_state.modele_ia)
            if p: 
                st.session_state.props = p; st.rerun()
            else:
                st.error(f"⚠️ Erreur IA : {err}")

    if st.session_state.props:
        st.write("##### 👇 Cliquez sur le bon modèle :")
        c1, c2 = st.columns(2)
        for i, prop in enumerate(st.session_state.props):
            col = c1 if i % 2 == 0 else c2
            if col.button(f"🔍 {prop}", use_container_width=True):
                st.session_state.nom_final = prop
                st.session_state.go_search = True
                st.rerun()
        if st.button("Autre (Saisie Manuelle)"): st.warning("Utilisez l'onglet Manuel.")

with tab_manuel:
    with st.form("man"):
        q = st.text_input("Recherche ou EAN", placeholder="Ex: 339189199222")
        if st.form_submit_button("🔎 Scanner") and q:
            st.session_state.nom_final = q; st.session_state.go_search = True; st.rerun()

# RÉSULTATS
if st.session_state.go_search and st.session_state.nom_final:
    st.divider()
    
    if not st.session_state.scan_results:
        with st.spinner("🌍 Scan Mondial en cours..."):
            stats, details, img_ref, nom_reel = scan_google_shopping_world(st.session_state.nom_final)
            st.session_state.scan_results = (stats, details, img_ref)
            st.session_state.nom_reel_produit = nom_reel
    
    if st.session_state.scan_results:
        stats, details, img_ref = st.session_state.scan_results
        
        # Gestion cas erreur API SERPAPI
        if "error" in stats:
             st.error(f"Erreur Scan Mondial : {stats['error']}")
             st.info("Vérifiez votre clé SerpApi ou votre quota.")
        
        elif stats["count"] > 0:
            st.markdown(f"### 🎯 Résultat : **{st.session_state.nom_reel_produit}**")
            
            c_img, c_stats = st.columns([1, 3])
            if img_ref: c_img.image(img_ref, width=150)
            with c_stats:
                k1, k2, k3 = st.columns(3)
                k1.metric("Min", f"{stats['min']:.0f} €")
                k2.metric("Médian", f"{stats['med']:.0f} €", f"{stats['count']} offres")
                k3.metric("Max", f"{stats['max']:.0f} €")
            
            st.write("---")
            cols = st.columns(5)
            for i, item in enumerate(details[:10]):
                with cols[i%5]:
                    st.metric(item["source"], f"{item['prix']:.0f} €")
                    st.caption(item["titre"][:20]+"..")
                    if item["lien"]: st.link_button("Voir", item["lien"])
                    else: st.button("X", disabled=True, key=f"n{i}")
                    st.divider()

            st.write("---")
            cc1, cc2, cc3 = st.columns(3)
            pv = cc1.number_input("Vente (€)", value=float(stats['med'])); pa = cc2.number_input("Achat (€)", 0.0)
            marge = pv - pa - (pv*0.15)
            cc3.metric("Marge Nette", f"{marge:.2f} €", delta="Gain" if marge>0 else "Perte")
            
            if st.button("💾 Sauvegarder"):
                if sheet:
                    sheet.append_row([datetime.now().strftime("%d/%m"), st.session_state.nom_reel_produit, pv, pa, f"{marge:.2f}", img_ref])
                    st.balloons(); st.success("OK"); time.sleep(1); reset_all(); st.rerun()
        else:
            st.warning("Aucun résultat. Vérifiez la clé SerpApi.")

if sheet:
    df = get_historique(sheet)
    if not df.empty: st.write("---"); st.dataframe(df, use_container_width=True, hide_index=True)
