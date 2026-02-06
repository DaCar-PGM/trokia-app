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
st.set_page_config(page_title="Trokia v17 : Argus Universel", page_icon="⚖️", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# --- 1. IA EXPERT MULTI-CRITÈRES ---
def analyser_objet_expert(image_pil, modele):
    try:
        model = genai.GenerativeModel(modele)
        # Prompt enrichi pour les meubles et la qualité
        prompt = (
            "Analyse cet objet d'occasion. Donne :\n"
            "1. NOM PRÉCIS : Marque et Modèle.\n"
            "2. CATÉGORIE : MEUBLE, TECH, VETEMENT, JEU, ou AUTRE.\n"
            "3. MATÉRIAUX : (ex: Bois massif, Cuir, Plastique).\n"
            "4. ÉTAT VISUEL : (Échelle 1-5).\n"
            "5. SCORE DÉSIRABILITÉ : (Échelle 1-10).\n"
            "Format : NOM: ... | CAT: ... | MAT: ... | ETAT: ... | SCORE: ..."
        )
        response = model.generate_content([prompt, image_pil])
        t = response.text.strip()
        
        res = {"nom": "Inconnu", "cat": "AUTRE", "mat": "N/A", "etat": "3", "score": "5"}
        if "NOM:" in t: res["nom"] = t.split("NOM:")[1].split("|")[0].strip()
        if "CAT:" in t: res["cat"] = t.split("CAT:")[1].split("|")[0].strip()
        if "MAT:" in t: res["mat"] = t.split("MAT:")[1].split("|")[0].strip()
        if "ETAT:" in t: res["etat"] = t.split("ETAT:")[1].split("|")[0].strip()
        if "SCORE:" in t: res["score"] = t.split("SCORE:")[1].strip()
        return res
    except: return None

def get_thumbnail(query):
    try:
        results = DDGS().images(keywords=query, region="fr-fr", max_results=1)
        return results[0]['image'] if results else "https://via.placeholder.com/150"
    except: return "https://via.placeholder.com/150"

# --- 2. MOTEURS DE PRIX & LIQUIDITÉ ---
def scan_global_cote(nom, cat):
    """Analyse multicritère pour sortir une cote béton"""
    try:
        # eBay pour la cote historique
        clean = re.sub(r'[^\w\s]', '', nom).strip()
        url_ebay = f"https://www.ebay.fr/sch/i.html?_nkw={clean.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url_ebay, headers=HEADERS, timeout=5)
        prices = [float(p.replace(",", ".").replace(" ", "")) for p in re.findall(r"(?:EUR|€)\s*([\d\s\.,]+)|([\d\s\.,]+)\s*(?:EUR|€)", r.text) for x in p if x and 2 < float(x.replace(",", ".").replace(" ", "")) < 8000]
        
        # DDG pour l'offre actuelle (Leboncoin/Vinted)
        results_web = DDGS().text(f"site:leboncoin.fr OR site:vinted.fr {nom}", max_results=10)
        web_prices = []
        if results_web:
            for res in results_web:
                p = re.findall(r"(\d+[\.,]?\d*)\s?(?:€|eur)", res.get('body', '').lower())
                if p: web_prices.append(float(p[0].replace(",", ".")))

        total_prices = prices + web_prices
        cote = statistics.median(total_prices) if total_prices else 0
        
        # Calcul Liquidité (Volume de vente vs Volume d'offre)
        liquidite = "Moyenne"
        if len(prices) > 15: liquidite = "🔥 Très Fluide"
        elif len(prices) < 3: liquidite = "❄️ Difficile"
        
        return cote, liquidite, url_ebay
    except: return 0, "Inconnue", ""

# --- 3. UI & GESTION ÉCHANGE ---
if 'objet_a' not in st.session_state: st.session_state.objet_a = None
if 'last_scan' not in st.session_state: st.session_state.last_scan = None

def configurer_modele():
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        return "gemini-1.5-flash"
    except: return None

st.title("⚖️ Trokia v17 : L'Argus Universel")

tab_scan, tab_troc = st.tabs(["🔍 Analyse & Expertise", "⚖️ Simulateur d'Échange"])

with tab_scan:
    col_l, col_r = st.columns([1, 2])
    with col_l:
        f = st.camera_input("Scanner un objet")
        if not f: f = st.file_uploader("Ou charger une image", type=['jpg', 'png'])

    if f:
        with st.spinner("Analyse Expertise en cours..."):
            model = configurer_modele()
            data = analyser_objet_expert(Image.open(f), model)
            cote, liq, url = scan_global_cote(data['nom'], data['cat'])
            st.session_state.last_scan = {"nom": data['nom'], "prix": cote, "img": get_thumbnail(data['nom'])}

        with col_r:
            st.header(f"{data['nom']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Cote Estimée", f"{cote:.0f} €")
            c2.metric("Liquidité", liq)
            c3.metric("État Visuel", f"{data['etat']}/5")
            
            with st.expander("📝 Détails de l'Expertise"):
                st.write(f"**Catégorie :** {data['cat']}")
                st.write(f"**Matériaux détectés :** {data['mat']}")
                st.write(f"**Score Désirabilité :** {data['score']}/10")
                if data['cat'] == "MEUBLE":
                    st.warning("💡 Note Meuble : La valeur dépend fortement du transport. Prix hors livraison.")
            
            if st.button("⚖️ Utiliser pour un ÉCHANGE", use_container_width=True):
                st.session_state.objet_a = st.session_state.last_scan
                st.success(f"{data['nom']} ajouté comme 'Objet A' dans le Troc !")

with tab_troc:
    st.header("Simulateur de Troc Intelligent")
    if st.session_state.objet_a:
        obj_a = st.session_state.objet_a
        col_a, col_vs, col_b = st.columns([2, 1, 2])
        
        with col_a:
            st.image(obj_a['img'], width=150)
            st.subheader(obj_a['nom'])
            st.title(f"{obj_a['prix']:.0f} €")
            st.caption("Votre objet (Slot A)")
            
        with col_vs:
            st.write("")
            st.write("")
            st.title(" 🆚 ")
            
        with col_b:
            if st.session_state.last_scan and st.session_state.last_scan['nom'] != obj_a['nom']:
                obj_b = st.session_state.last_scan
                st.image(obj_b['img'], width=150)
                st.subheader(obj_b['nom'])
                st.title(f"{obj_b['prix']:.0f} €")
                st.caption("Objet proposé (Slot B)")
                
                st.divider()
                diff = obj_a['prix'] - obj_b['prix']
                if diff > 0:
                    st.error(f"⚠️ Échange défavorable.\n\nDemandez un rajout de **{abs(diff):.0f} €**")
                elif diff < 0:
                    st.success(f"✅ Très bon deal !\n\nVous gagnez **{abs(diff):.0f} €** de valeur.")
                else:
                    st.info("🤝 Échange équitable (Perfect Match).")
            else:
                st.info("Scannez le second objet dans l'onglet 'Analyse' pour comparer.")
    else:
        st.warning("Commencez par scanner un premier objet.")

st.divider()
st.caption("Trokia v17 - IA & Data Market en temps réel.")
