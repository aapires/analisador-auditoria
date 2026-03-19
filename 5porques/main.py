"""
5 Porquês — Análise de causa raiz de achados de auditoria.

Lê achados.xlsx (colunas: achado, area), aplica a técnica dos 5 Porquês
com Claude e salva o resultado em achados_5porques.xlsx.

Colunas de saída:
    achado, area, por_que_1..5 (vazias a partir da causa raiz),
    causa_raiz, recomendacao
"""

import os
import re
import anthropic
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

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


def aplicar_5porques(achado: str, area: str) -> dict:
    prompt = f"Área de auditoria: {area}\nAchado: {achado}"

    resposta = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    texto = resposta.content[0].text
    return _parsear_resposta(texto)


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


def main():
    df = pd.read_excel("achados.xlsx")
    print(f"Analisando {len(df)} achado(s) com a técnica dos 5 Porquês...\n")

    resultados = []
    for i, row in df.iterrows():
        print(f"Processando achado {i + 1}/{len(df)}...")
        analise = aplicar_5porques(row["achado"], row["area"])
        resultados.append({
            "achado": row["achado"],
            "area": row["area"],
            **analise,
        })

    df_resultado = pd.DataFrame(resultados, columns=[
        "achado", "area",
        "por_que_1", "por_que_2", "por_que_3", "por_que_4", "por_que_5",
        "causa_raiz", "recomendacao",
    ])

    df_resultado.to_excel("achados_5porques.xlsx", index=False)
    print("\nConcluído! Arquivo salvo em achados_5porques.xlsx")


if __name__ == "__main__":
    main()
