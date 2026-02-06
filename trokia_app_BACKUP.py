import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import statistics
import random

# --- CONFIGURATION ---
st.set_page_config(page_title="Trokia v19 : L'Argus Universel", page_icon="⚖️", layout="wide")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]

# --- 1. MOTEUR IA (MULTI-PHOTOS & IDENTIFICATION) ---
def identifier_objet_ia(images_pil):
    """Analyse jusqu'à 5 images pour identifier le modèle exact"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        prompt = (
            "Analyse ces images (plusieurs angles du même objet). "
            "Identifie précisément l'objet. Propose les 4 modèles les plus probables. "
            "Pour chaque modèle, donne son nom commercial complet. "
            "Format de sortie STRICT :\n1. Nom Complet Modèle 1\n2. Nom Complet Modèle 2\n3. Nom Complet Modèle 3\n4. Nom Complet Modèle 4"
        )
        
        # On envoie la liste des images à l'IA
        response = model.generate_content([prompt] + images_pil)
        lines = response.text.strip().split('\n')
        propositions = [re.sub(r'^\d+\.\s*', '', l).strip() for l in lines if l and l[0].isdigit()]
        return propositions[:4]
    except Exception as e:
        return [f"Erreur IA: {str(e)[:30]}"]

# --- 2. RÉCUPÉRATION VISUELLE ---
def get_ref_image(query):
    """Trouve une image de référence pour aider l'utilisateur à choisir"""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(keywords=query, region="fr-fr", max_results=1))
            return results[0]['image'] if results else "https://via.placeholder.com/150"
    except: return "https://via.placeholder.com/150"

# --- 3. MOTEUR DE PRIX (VENDUS + WEB) ---
def clean_price(val_str):
    if not val_str: return None
    val_str = re.sub(r'[^\d,\.]', '', val_str)
    try: return float(val_str.replace(",", "."))
    except: return None

def estimer_prix_final(nom_exact):
    """Calcule la cote une fois le modèle validé"""
    prices = []
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    
    # eBay Vendus
    try:
        clean_name = re.sub(r'[^\w\s]', '', nom_exact).strip()
        url_ebay = f"https://www.ebay.fr/sch/i.html?_nkw={clean_name.replace(' ', '+')}&LH_Sold=1&LH_Complete=1"
        r = requests.get(url_ebay, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup.select('.s-item__price'):
            p = clean_price(tag.get_text())
            if p and 1 < p < 15000: prices.append(p)
    except: pass

    # Web Global
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(f"prix vendu {nom_exact} leboncoin", max_results=10))
            for res in results:
                found = re.findall(r"(\d+[\s\.,]?\d*)\s?(?:€|eur)", res.get('body', '').lower())
                for f in found:
                    p = clean_price(f)
                    if p and 1 < p < 15000: prices.append(p)
    except: pass

    if not prices: return 0, "Indéterminée"
    
    cote = statistics.median(prices)
    fiabilite = "Élevée" if len(prices) > 8 else "Moyenne"
    return cote, fiabilite

# --- 4. INTERFACE ---
st.title("⚖️ Trokia v19 : L'Argus Universel")

# Session State
if 'step' not in st.session_state: st.session_state.step = "input"
if 'propositions' not in st.session_state: st.session_state.propositions = []
if 'images_ref' not in st.session_state: st.session_state.images_ref = []

def reset():
    for key in st.session_state.keys(): del st.session_state[key]
    st.rerun()

# --- ETAPE 1 : ENTREE DES DONNÉES ---
if st.session_state.step == "input":
    st.write("### 1. Identifiez votre objet")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**🔍 Par Photos (Max 5)**")
        uploaded_files = st.file_uploader("Prenez plusieurs angles ou importez depuis votre bibliothèque", type=['jpg','png','jpeg'], accept_multiple_files=True)
        if uploaded_files and len(uploaded_files) > 5:
            st.error("Maximum 5 photos svp.")
            uploaded_files = uploaded_files[:5]
            
        if st.button("Lancer l'Analyse IA 🤖", type="primary") and uploaded_files:
            with st.spinner("Analyse approfondie des photos..."):
                imgs = [Image.open(f) for f in uploaded_files]
                props = identifier_objet_ia(imgs)
                st.session_state.propositions = props
                # Récupération immédiate des photos de référence
                st.session_state.images_ref = [get_ref_image(p) for p in props]
                st.session_state.step = "selection"
                st.rerun()

    with col2:
        st.markdown("**⌨️ Par Nom ou Code-Barre**")
        q_in = st.text_input("Tapez le modèle ou scannez l'EAN")
        if st.button("Rechercher 🔎") and q_in:
            with st.spinner("Recherche..."):
                st.session_state.nom_valide = q_in
                st.session_state.step = "resultat"
                st.rerun()

# --- ETAPE 2 : SELECTION VISUELLE ---
elif st.session_state.step == "selection":
    st.write("### 2. Confirmez le modèle exact")
    st.info("Cliquez sur le bouton sous l'image qui correspond à votre objet.")
    
    cols = st.columns(len(st.session_state.propositions))
    for i, col in enumerate(cols):
        with col:
            st.image(st.session_state.images_ref[i], use_container_width=True)
            st.markdown(f"**{st.session_state.propositions[i]}**")
            if st.button("C'est celui-ci ✅", key=f"btn_{i}"):
                st.session_state.nom_valide = st.session_state.propositions[i]
                st.session_state.step = "resultat"
                st.rerun()
    
    if st.button("🔙 Retour"): st.session_state.step = "input"; st.rerun()

# --- ETAPE 3 : RESULTAT FINAL ---
elif st.session_state.step == "resultat":
    st.write(f"### ⚖️ Argus pour : {st.session_state.nom_valide}")
    
    with st.spinner("Calcul de la cote mondiale en temps réel..."):
        cote, fiab = estimer_prix_final(st.session_state.nom_valide)
        img_finale = get_ref_image(st.session_state.nom_valide)

    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.image(img_finale, use_container_width=True)
    
    with col_b:
        if cote > 0:
            st.metric("VALEUR ESTIMÉE", f"{cote:.2f} €", help="Prix médian basé sur les ventes réelles")
            st.write(f"**Indice de confiance :** {fiab}")
            
            st.divider()
            st.markdown("#### 💡 Conseils Trokia")
            if fiab == "Élevée":
                st.success("Produit très liquide. Se vendra rapidement au prix indiqué.")
            else:
                st.warning("Peu de transactions récentes. Prévoyez une marge de négociation de 15%.")
        else:
            st.error("Aucune transaction trouvée pour ce modèle précis. Il est peut-être très rare ou mal orthographié.")

    if st.button("🔄 Nouvelle estimation"): reset()

st.divider()
st.caption("Trokia v19.0 - L'Argus Universel de l'objet d'occasion.")
