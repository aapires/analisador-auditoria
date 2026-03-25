import anthropic
import pandas as pd

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
CONSEQUÊNCIAS: [uma frase]
RECOMENDAÇÃO: [uma frase]
RESPONSAVEL: [autoridade responsável a quem a recomendação seria direcionada, ex.: Diretor, Secretário, Gerente]

Achado: {texto}"""}
        ]
    )
    return mensagem.content[0].text

df = pd.read_excel("achados.xlsx")

print(f"Analisando {len(df)} achados...\n")

resultados = []
for i, row in df.iterrows():
    print(f"Processando achado {i+1}...")
    analise = analisar_achado(row["achado"], row["area"])
    
    linhas = analise.strip().split("\n")
    risco, justificativa, consequencias, recomendacao, responsavel = "", "", "", "", ""
    for linha in linhas:
        if linha.startswith("RISCO:"):
            risco = linha.replace("RISCO:", "").strip()
        elif linha.startswith("JUSTIFICATIVA:"):
            justificativa = linha.replace("JUSTIFICATIVA:", "").strip()
        elif linha.startswith("CONSEQUÊNCIAS:"):
            consequencias = linha.replace("CONSEQUÊNCIAS:", "").strip()
        elif linha.startswith("RECOMENDAÇÃO:"):
            recomendacao = linha.replace("RECOMENDAÇÃO:", "").strip()
        elif linha.startswith("RESPONSAVEL:"):
            responsavel = linha.replace("RESPONSAVEL:", "").strip()

    resultados.append({
        "achado": row["achado"],
        "area": row["area"],
        "risco": risco,
        "justificativa": justificativa,
        "consequencias": consequencias,
        "recomendacao": recomendacao,
        "Responsavel": responsavel
    })

df_resultado = pd.DataFrame(resultados)

# Definir ordem de risco para cálculo da prioridade
ordem_risco = {
    "Alto": 1,
    "Médio": 2,
    "Medio": 2,
    "Baixo": 3
}

# Ordenar pelos níveis de risco e atribuir prioridade 1..N,
# preservando a ordem original dentro de cada nível de risco
df_resultado["__ordem_risco"] = df_resultado["risco"].map(ordem_risco).fillna(4)
df_resultado["__pos_original"] = range(len(df_resultado))
df_resultado = df_resultado.sort_values(["__ordem_risco", "__pos_original"]).reset_index(drop=True)
df_resultado["Prioridade"] = range(1, len(df_resultado) + 1)
df_resultado = df_resultado.drop(columns=["__ordem_risco", "__pos_original"])

df_resultado.to_excel("achados_analisados.xlsx", index=False)

print("\nConcluído! Arquivo salvo em achados_analisados.xlsx")
