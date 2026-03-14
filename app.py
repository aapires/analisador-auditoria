import anthropic
import pandas as pd
import streamlit as st
import io

client = anthropic.Anthropic()

def analisar_achado(texto, area):
    mensagem = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": f"""Analise o seguinte achado de auditoria da área {area}.
Retorne exatamente neste formato:
RISCO: [Alto/Médio/Baixo]
JUSTIFICATIVA: [uma frase]
CONSEQUENCIAS: [uma frase]
RECOMENDAÇÃO: [uma frase]

Achado: {texto}"""}
        ]
    )
    return mensagem.content[0].text

def processar_planilha(df):
    resultados = []
    total = len(df)
    barra = st.progress(0, text="Iniciando análise...")

    for i, row in df.iterrows():
        barra.progress((i + 1) / total, text=f"Analisando achado {i+1} de {total}...")
        analise = analisar_achado(row["achado"], row["area"])

        linhas = analise.strip().split("\n")
        risco, justificativa, consequencias, recomendacao = "", "", "", ""
        for linha in linhas:
            if linha.startswith("RISCO:"):
                risco = linha.replace("RISCO:", "").strip()
            elif linha.startswith("JUSTIFICATIVA:"):
                justificativa = linha.replace("JUSTIFICATIVA:", "").strip()
            elif linha.startswith("CONSEQUENCIAS:"):
                consequencias = linha.replace("CONSEQUENCIAS:", "").strip()
            elif linha.startswith("RECOMENDAÇÃO:"):
                recomendacao = linha.replace("RECOMENDAÇÃO:", "").strip()

        resultados.append({
            "achado": row["achado"],
            "area": row["area"],
            "risco": risco,
            "justificativa": justificativa,
            "consequencias": consequencias,
            "recomendacao": recomendacao
        })

    barra.empty()
    df_resultado = pd.DataFrame(resultados)

    ordem = {"Alto": 1, "Médio": 2, "Baixo": 3}
    df_resultado["prioridade"] = df_resultado["risco"].map(ordem).fillna(9).astype(int)
    df_resultado = df_resultado.sort_values("prioridade").reset_index(drop=True)
    df_resultado["prioridade"] = range(1, len(df_resultado) + 1)

    return df_resultado

def colorir_risco(val):
    cores = {"Alto": "#ffcccc", "Médio": "#fff3cc", "Baixo": "#ccffcc"}
    return f"background-color: {cores.get(val, 'white')}"

st.set_page_config(page_title="Analisador de Auditoria", page_icon="🔍", layout="wide")
st.title("🔍 Analisador de Achados de Auditoria")
st.markdown("Faça upload de uma planilha com colunas `achado` e `area` para análise automática via IA.")

arquivo = st.file_uploader("Selecione a planilha (.xlsx)", type=["xlsx"])

if arquivo:
    df = pd.read_excel(arquivo)
    st.subheader("Achados carregados")
    st.dataframe(df, use_container_width=True)

    if st.button("Analisar com IA", type="primary"):
        with st.spinner("Processando..."):
            df_resultado = processar_planilha(df)

        st.subheader("Resultado da análise")
        st.dataframe(
            df_resultado.style.applymap(colorir_risco, subset=["risco"]),
            use_container_width=True
        )

        buffer = io.BytesIO()
        df_resultado.to_excel(buffer, index=False)
        buffer.seek(0)

        st.download_button(
            label="Baixar resultado em Excel",
            data=buffer,
            file_name="achados_analisados.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
