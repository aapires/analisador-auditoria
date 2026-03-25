import anthropic

client = anthropic.Anthropic()

texto = input("Cole o achado de auditoria aqui: ")

mensagem = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": f"Analise o seguinte achado de auditoria e classifique o risco (Alto/Médio/Baixo) com justificativa:\n\n{texto}"}
    ]
)

print(mensagem.content[0].text)
