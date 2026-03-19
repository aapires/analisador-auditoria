import io
import anthropic
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Lógica de negócio
# ---------------------------------------------------------------------------

SYSTEM = """\
Você é um auditor interno sênior especialista em análise de causa raiz.
Sua tarefa é aplicar a técnica dos 5 Porquês a achados de auditoria.

Regras da técnica:
- Parta do achado e pergunte "Por quê isso ocorre?" sucessivamente.
- Cada resposta torna-se o insumo da pergunta seguinte.
- Pare assim que chegar à causa raiz — pode ser antes do 5º passo.
- Deixe os campos POR_QUE_N com o valor literal VAZIO a partir do passo em que a causa raiz já foi identificada.
- A causa raiz é geralmente uma falha de processo, controle, gestão ou decisão — não um sintoma.
- A recomendação deve atacar diretamente a causa raiz, não o sintoma inicial.

Para cada POR_QUE_N ativo, forneça a pergunta e a resposta separadas por " || " (espaço, duas barras, espaço):
  POR_QUE_1: Por quê [pergunta derivada do achado]? || Porque [resposta que leva ao próximo porquê].

Responda SOMENTE no formato abaixo, sem texto adicional:
POR_QUE_1: Por quê [pergunta]? || Porque [resposta].
POR_QUE_2: Por quê [pergunta baseada na resposta anterior]? || Porque [resposta]. — ou VAZIO
POR_QUE_3: Por quê [pergunta]? || Porque [resposta]. — ou VAZIO
POR_QUE_4: Por quê [pergunta]? || Porque [resposta]. — ou VAZIO
POR_QUE_5: Por quê [pergunta]? || Porque [resposta]. — ou VAZIO
CAUSA_RAIZ: [descrição objetiva da causa raiz identificada]
RECOMENDACAO: [recomendação focada em eliminar a causa raiz, dirigida à autoridade competente]"""


def _parsear_resposta(texto: str) -> dict:
    campos = {k: "" for k in ["por_que_1", "por_que_2", "por_que_3", "por_que_4", "por_que_5", "causa_raiz", "recomendacao"]}
    mapa = {
        "POR_QUE_1:": "por_que_1", "POR_QUE_2:": "por_que_2",
        "POR_QUE_3:": "por_que_3", "POR_QUE_4:": "por_que_4",
        "POR_QUE_5:": "por_que_5", "CAUSA_RAIZ:": "causa_raiz",
        "RECOMENDACAO:": "recomendacao",
    }
    for linha in texto.strip().splitlines():
        linha = linha.strip()
        for prefixo, chave in mapa.items():
            if linha.upper().startswith(prefixo):
                valor = linha[len(prefixo):].strip()
                if valor.upper() == "VAZIO" or valor.upper().startswith("VAZIO"):
                    campos[chave] = ""
                elif chave.startswith("por_que") and " || " in valor:
                    pergunta, resposta = valor.split(" || ", 1)
                    campos[chave] = f"{pergunta.strip()}\n{resposta.strip()}"
                else:
                    campos[chave] = valor
                break
    return campos


def aplicar_5porques(achado: str, area: str) -> dict:
    resposta = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Área de auditoria: {area}\nAchado: {achado}"}],
    )
    return _parsear_resposta(resposta.content[0].text)


def processar_planilha(df: pd.DataFrame) -> pd.DataFrame:
    resultados = []
    total = len(df)
    barra = st.progress(0, text="Iniciando análise...")

    for i, row in df.iterrows():
        barra.progress((i + 1) / total, text=f"Analisando achado {i + 1} de {total}...")
        analise = aplicar_5porques(row["achado"], row["area"])
        resultados.append({"achado": row["achado"], "area": row["area"], **analise})

    barra.empty()
    return pd.DataFrame(resultados, columns=[
        "achado", "area",
        "por_que_1", "por_que_2", "por_que_3", "por_que_4", "por_que_5",
        "causa_raiz", "recomendacao",
    ])


# ---------------------------------------------------------------------------
# Interface Streamlit
# ---------------------------------------------------------------------------

st.set_page_config(page_title="5 Porquês — Auditoria", page_icon="🔎", layout="wide")

st.markdown(
    """
    <style>
        .stApp, [data-testid="stAppViewContainer"], section.main {
            background-color: #D8E4E8 !important;
        }
        .block-container, [data-testid="stVerticalBlock"] > div {
            background-color: #CCDCE0 !important;
        }
        .stButton > button[kind="primary"] {
            background-color: #154453;
            border-color: #154453;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #3C7A83;
            border-color: #3C7A83;
        }
        h1, h2, h3 { color: #154453 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔎 Análise de Causa Raiz — 5 Porquês")
st.markdown("Faça upload de uma planilha com colunas `achado` e `area` para identificar a causa raiz via técnica dos 5 Porquês.")

arquivo = st.file_uploader("Selecione a planilha (.xlsx)", type=["xlsx"])

if arquivo:
    df = pd.read_excel(arquivo)
    st.subheader("Achados carregados")
    st.dataframe(df, use_container_width=True)

    if st.button("Aplicar 5 Porquês", type="primary"):
        df_resultado = processar_planilha(df)

        st.subheader("Resultado da análise")
        st.dataframe(df_resultado, use_container_width=True)

        buffer = io.BytesIO()
        df_resultado.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            label="Baixar resultado em Excel",
            data=buffer,
            file_name="achados_5porques.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
