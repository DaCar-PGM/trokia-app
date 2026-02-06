import streamlit as st
import google.generativeai as genai

st.title("🧪 Testeur de modèles Trokia")

# Configuration via tes secrets
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    st.write("### 🧠 Modèles disponibles pour ta clé :")
    
    # On interroge Google pour avoir la liste
    available_models = genai.list_models()
    
    for m in available_models:
        # On filtre pour ne voir que les modèles qui peuvent analyser du texte/images
        if 'generateContent' in m.supported_generation_methods:
            col1, col2 = st.columns([1, 2])
            col1.code(m.name)
            col2.caption(m.description)
            st.divider()

except Exception as e:
    st.error(f"Erreur de connexion : {e}")
