import os
import subprocess
import requests
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Buscador de Brechós B2B", page_icon="🛍️", layout="wide")
st.title("🛍️ Buscador de Brechós B2B")
st.caption("Encontre novos clientes e parceiros diretamente no Google Maps")

BINARY_NAME = "google_maps_scraper"
RELEASE_URL = "https://github.com/gosom/google-maps-scraper/releases/download/v1.18.1/google_maps_scraper-1.18.1-linux-amd64"

# --- FUNÇÃO PARA INSTALAR O EXECUTÁVEL ---
def setup_scraper_binary():
    if not os.path.exists(BINARY_NAME):
        with st.spinner("Instalando o motor de busca no servidor..."):
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(RELEASE_URL, headers=headers, stream=True)
            
            if response.status_code == 200:
                with open(BINARY_NAME, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                os.chmod(BINARY_NAME, 0o755)
            else:
                st.error(f"Erro ao baixar executável. Código HTTP: {response.status_code}")
                return False
    return True

# --- FUNÇÃO DE ENVIO PARA O GOOGLE SHEETS (OPCIONAL) ---
def salvar_no_google_sheets(df):
    try:
        if "GOOGLE_CREDENTIALS" in st.secrets:
            creds_dict = dict(st.secrets["GOOGLE_CREDENTIALS"])
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            
            sheet_name = st.secrets.get("SPREADSHEET_NAME", "Prospecção de Brechós")
            sheet = client.open(sheet_name).sheet1
            sheet.append_rows(df.astype(str).values.tolist())
            return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")
        return False
    return False

# --- INTERFACE E FLUXO PRINCIPAL ---
if setup_scraper_binary():
    termo_busca = st.text_input("Digite o termo de busca:", placeholder="Ex: brechó Caxias do Sul")
    profundidade = st.slider("Quantidade de resultados (Profundidade):", min_value=1, max_value=5, value=1)

    if st.button("🚀 Iniciar Busca", type="primary"):
        if not termo_busca:
            st.warning("Por favor, digite um termo de busca.")
        else:
            input_file = "input_queries.txt"
            temp_results_file = "temp_results.json"
            
            with open(input_file, "w", encoding="utf-8") as f:
                f.write(termo_busca + "\n")

            if os.path.exists(temp_results_file):
                os.remove(temp_results_file)

            # Executa com xvfb-run para ambiente gráfico no Linux
            cmd = [
                "xvfb-run",
                "--auto-servernum",
                f"./{BINARY_NAME}",
                "-input", input_file,
                "-results", temp_results_file,
                "-depth", str(profundidade),
                "-lang", "pt",
                "-json",
                "-disable-page-reuse"
            ]

            with st.spinner("Varrendo o Google Maps... Isso pode levar de 1 a 2 minutos."):
                process = subprocess.run(cmd, capture_output=True, text=True)

            if os.path.exists(input_file):
                os.remove(input_file)

            if os.path.exists(temp_results_file) and os.path.getsize(temp_results_file) > 0:
                try:
                    # Leitura corrigida para o formato JSON Lines (NDJSON)
                    df_bruto = pd.read_json(temp_results_file, lines=True)
                    
                    if os.path.exists(temp_results_file):
                        os.remove(temp_results_file)
                    
                    if not df_bruto.empty:
                        colunas_desejadas = ["title", "phone", "website", "address", "rating", "reviews_total"]
                        colunas_existentes = [col for col in colunas_desejadas if col in df_bruto.columns]
                        
                        df_limpo = df_bruto[colunas_existentes].copy()
                        
                        if "phone" in df_limpo.columns:
                            df_limpo = df_limpo.dropna(subset=["phone"])
                        
                        renomear = {
                            "title": "Nome do Brechó",
                            "phone": "Telefone/WhatsApp",
                            "website": "Site/Instagram",
                            "address": "Endereço",
                            "rating": "Nota",
                            "reviews_total": "Total Avaliações"
                        }
                        df_limpo = df_limpo.rename(columns=renomear)

                        st.success(f"Busca finalizada! {len(df_limpo)} brechós encontrados.")
                        
                        st.subheader("📋 Lista de Brechós Encontrados")
                        st.data_editor(
                            df_limpo,
                            use_container_width=True,
                            hide_index=True,
                            disabled=True
                        )

                        if salvar_no_google_sheets(df_limpo):
                            st.toast("Contatos sincronizados com o Google Sheets!", icon="✅")

                    else:
                        st.info("Nenhum resultado retornado para essa busca.")
                except Exception as err:
                    st.error(f"Erro ao processar os dados da busca: {err}")
            else:
                st.error("O scraper não retornou dados para este termo. Veja os logs abaixo:")
                if process.stderr or process.stdout:
                    with st.expander("Ver detalhes técnicos do log"):
                        st.code(process.stderr if process.stderr else process.stdout)
