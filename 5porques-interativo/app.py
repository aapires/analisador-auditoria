"""
5 Porquês Interativo — análise de causa raiz com edição interativa de cada passo.

Fluxo:
  1. Usuário informa achado + área → gera cadeia completa.
  2. Cada resposta tem botão de editar.
  3. Editar: exibe 4 alternativas geradas pela IA + caixa para resposta própria.
  4. Salvar: recalcula toda a cadeia a partir daquele ponto.
  5. Desfazer: volta ao estado anterior.
"""

import copy
import os
from google import genai
from google.genai import types
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash"

# ── Estilo ────────────────────────────────────────────────────────────────────

CSS = """
<style>
    .stApp, [data-testid="stAppViewContainer"], section.main {
        background-color: #D8E4E8 !important;
    }
    .block-container { background-color: #CCDCE0 !important; }
    .stButton > button[kind="primary"] {
        background-color: #154453; border-color: #154453;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #3C7A83; border-color: #3C7A83;
    }
    h1, h2, h3 { color: #154453 !important; }
    .step-card {
        background: white;
        border-left: 4px solid #154453;
        border-radius: 4px;
        padding: 12px 16px;
        margin-bottom: 6px;
    }
    .step-card-editing {
        background: #f0f7f9;
        border: 2px solid #3C7A83;
        border-radius: 6px;
        padding: 16px;
        margin-bottom: 6px;
    }
    .conclusao-card {
        background: #154453;
        color: white;
        border-radius: 6px;
        padding: 14px 18px;
        margin-top: 16px;
    }
    .rec-card {
        background: #3C7A83;
        color: white;
        border-radius: 6px;
        padding: 14px 18px;
        margin-top: 8px;
    }
</style>
"""

# ── LLM ───────────────────────────────────────────────────────────────────────

SYSTEM_BASE = """\
Você é um auditor interno sênior especialista em análise de causa raiz pela técnica dos 5 Porquês.

Regras:
- A causa raiz é geralmente uma falha de processo, controle, gestão ou decisão — não um sintoma.
- A recomendação deve atacar diretamente a causa raiz, dirigida à autoridade competente.
- Pare antes do 5º passo se a causa raiz já for identificada; use VAZIO nos passos restantes."""


def _ctx(chain):
    return "\n".join(
        f"Passo {i}: {s['pergunta']} / {s['resposta']}"
        for i, s in enumerate(chain, 1)
    )


def _parsear_passo(texto, n):
    p = r = ""
    for linha in texto.splitlines():
        l = linha.strip()
        if l.upper().startswith(f"P{n}_PERGUNTA:"):
            v = l[len(f"P{n}_PERGUNTA:"):].strip()
            p = "" if v.upper().startswith("VAZIO") else v
        elif l.upper().startswith(f"P{n}_RESPOSTA:"):
            v = l[len(f"P{n}_RESPOSTA:"):].strip()
            r = "" if v.upper().startswith("VAZIO") else v
    return p, r


def _parsear_conclusao(texto):
    causa = rec = ""
    for linha in texto.splitlines():
        l = linha.strip()
        if l.upper().startswith("CAUSA_RAIZ:"):
            causa = l[len("CAUSA_RAIZ:"):].strip()
        elif l.upper().startswith("RECOMENDACAO:"):
            rec = l[len("RECOMENDACAO:"):].strip()
    return causa, rec


def gerar_cadeia_completa(achado, area):
    prompt = f"""Área: {area}
Achado: {achado}

Aplique a técnica dos 5 Porquês. Responda SOMENTE neste formato, sem texto adicional:
P1_PERGUNTA: Por quê [pergunta derivada do achado]?
P1_RESPOSTA: Porque [resposta].
P2_PERGUNTA: Por quê [pergunta baseada em P1_RESPOSTA]?
P2_RESPOSTA: Porque [resposta].
P3_PERGUNTA: Por quê [pergunta baseada em P2_RESPOSTA]?
P3_RESPOSTA: Porque [resposta].
P4_PERGUNTA: Por quê [...]? — ou VAZIO se causa raiz já identificada
P4_RESPOSTA: Porque [...]. — ou VAZIO
P5_PERGUNTA: Por quê [...]? — ou VAZIO
P5_RESPOSTA: Porque [...]. — ou VAZIO
CAUSA_RAIZ: [causa raiz identificada]
RECOMENDACAO: [recomendação focada na causa raiz]"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_BASE,
            max_output_tokens=2048,
        ),
    )
    texto = resp.text
    chain = []
    for n in range(1, 6):
        p, r = _parsear_passo(texto, n)
        if p and r:
            chain.append({"pergunta": p, "resposta": r})
    causa, rec = _parsear_conclusao(texto)
    return chain, causa, rec


def gerar_alternativas(achado, area, chain, idx):
    pergunta = chain[idx]["pergunta"]
    ctx = _ctx(chain[:idx])
    prompt = f"""Área: {area}
Achado: {achado}
{"Cadeia confirmada:\n" + ctx if ctx else ""}

Pergunta atual: {pergunta}

Gere 4 respostas alternativas plausíveis, cada uma representando uma causa diferente.
Responda SOMENTE neste formato:
ALT_1: Porque [resposta 1].
ALT_2: Porque [resposta 2].
ALT_3: Porque [resposta 3].
ALT_4: Porque [resposta 4]."""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_BASE,
            max_output_tokens=1024,
        ),
    )
    alts = []
    for linha in resp.text.splitlines():
        l = linha.strip()
        for n in range(1, 5):
            if l.upper().startswith(f"ALT_{n}:"):
                alts.append(l[len(f"ALT_{n}:"):].strip())
    return alts[:4]


def regenerar_a_partir_de(achado, area, chain_confirmada):
    """Recebe a cadeia confirmada (0..N com nova resposta em N) e regenera N+1..fim."""
    prox = len(chain_confirmada) + 1
    ctx = _ctx(chain_confirmada)

    linhas_fmt = []
    for i in range(prox, 6):
        linhas_fmt += [
            f"P{i}_PERGUNTA: Por quê [...]? — ou VAZIO",
            f"P{i}_RESPOSTA: Porque [...]. — ou VAZIO",
        ]
    linhas_fmt += ["CAUSA_RAIZ: [...]", "RECOMENDACAO: [...]"]

    prompt = f"""Área: {area}
Achado: {achado}

Cadeia já confirmada:
{ctx}

Continue a partir do passo {prox}. Use VAZIO nos passos restantes se a causa raiz já foi identificada.
Responda SOMENTE neste formato:
{chr(10).join(linhas_fmt)}"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_BASE,
            max_output_tokens=2048,
        ),
    )
    texto = resp.text
    new_steps = []
    for n in range(prox, 6):
        p, r = _parsear_passo(texto, n)
        if p and r:
            new_steps.append({"pergunta": p, "resposta": r})
    causa, rec = _parsear_conclusao(texto)
    return chain_confirmada + new_steps, causa, rec


# ── Session state ─────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "phase": "input",
        "achado": "",
        "area": "",
        "chain": [],
        "causa_raiz": "",
        "recomendacao": "",
        "editing_index": None,
        "alternatives": None,
        "history": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in ["phase", "achado", "area", "chain", "causa_raiz", "recomendacao",
              "editing_index", "alternatives", "history"]:
        if k in st.session_state:
            del st.session_state[k]


# ── Telas ─────────────────────────────────────────────────────────────────────

def tela_input():
    st.markdown("Informe o achado de auditoria e a área para iniciar a análise.")
    achado = st.text_area("Achado de auditoria:", height=120, key="inp_achado")
    area = st.text_input("Área:", key="inp_area")

    if st.button("Analisar", type="primary"):
        if achado.strip() and area.strip():
            with st.spinner("Gerando análise dos 5 Porquês..."):
                chain, causa, rec = gerar_cadeia_completa(achado.strip(), area.strip())
            st.session_state.update({
                "phase": "results",
                "achado": achado.strip(),
                "area": area.strip(),
                "chain": chain,
                "causa_raiz": causa,
                "recomendacao": rec,
                "editing_index": None,
                "alternatives": None,
                "history": [],
            })
            st.rerun()
        else:
            st.warning("Preencha o achado e a área.")


def tela_resultados():
    s = st.session_state

    # ── Cabeçalho ──
    col_info, col_undo, col_new = st.columns([7, 1.5, 1.5])
    with col_info:
        st.markdown(f"**Achado:** {s.achado}  \n**Área:** {s.area}")
    with col_undo:
        if s.history:
            if st.button("↩ Desfazer", use_container_width=True):
                prev = s.history.pop()
                s.chain = prev["chain"]
                s.causa_raiz = prev["causa_raiz"]
                s.recomendacao = prev["recomendacao"]
                s.editing_index = None
                s.alternatives = None
                st.rerun()
    with col_new:
        if st.button("Nova análise", use_container_width=True):
            _reset()
            st.rerun()

    st.divider()

    # ── Cadeia de porquês ──
    for i, step in enumerate(s.chain):
        is_editing = s.editing_index == i

        if is_editing:
            # Gera alternativas se ainda não foram geradas
            if s.alternatives is None:
                with st.spinner("Gerando alternativas..."):
                    s.alternatives = gerar_alternativas(s.achado, s.area, s.chain, i)
                st.rerun()

            st.markdown(
                f'<div class="step-card-editing"><strong>{i+1}. {step["pergunta"]}</strong></div>',
                unsafe_allow_html=True,
            )

            opts = s.alternatives + ["✍️ Digitar minha própria resposta"]
            choice = st.radio(
                "Selecione uma alternativa:",
                opts,
                key=f"radio_{i}",
            )

            custom_val = ""
            if choice == opts[-1]:
                custom_val = st.text_area(
                    "Sua resposta:",
                    value=step["resposta"],
                    key=f"custom_{i}",
                    height=80,
                )

            col_salvar, col_cancelar, _ = st.columns([1, 1, 6])
            with col_salvar:
                if st.button("Salvar", type="primary", key=f"save_{i}"):
                    nova = custom_val.strip() if choice == opts[-1] else choice
                    if nova:
                        s.history.append({
                            "chain": copy.deepcopy(s.chain),
                            "causa_raiz": s.causa_raiz,
                            "recomendacao": s.recomendacao,
                        })
                        s.chain[i]["resposta"] = nova
                        with st.spinner("Recalculando cadeia..."):
                            s.chain, s.causa_raiz, s.recomendacao = regenerar_a_partir_de(
                                s.achado, s.area, s.chain[:i + 1]
                            )
                        s.editing_index = None
                        s.alternatives = None
                        st.rerun()
                    else:
                        st.warning("A resposta não pode estar vazia.")
            with col_cancelar:
                if st.button("Cancelar", key=f"cancel_{i}"):
                    s.editing_index = None
                    s.alternatives = None
                    st.rerun()

        else:
            col_step, col_btn = st.columns([11, 1])
            with col_step:
                st.markdown(
                    f'<div class="step-card">'
                    f'<strong>{i+1}. {step["pergunta"]}</strong><br>'
                    f'{step["resposta"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                # Só mostra o botão editar se nenhum outro passo está sendo editado
                if s.editing_index is None:
                    if st.button("✏️", key=f"edit_{i}", help="Editar esta resposta"):
                        s.editing_index = i
                        s.alternatives = None
                        st.rerun()

    # ── Conclusão ──
    st.markdown(
        f'<div class="conclusao-card">'
        f'<strong>🎯 Causa Raiz</strong><br>{s.causa_raiz}'
        f'</div>'
        f'<div class="rec-card">'
        f'<strong>💡 Recomendação</strong><br>{s.recomendacao}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="5 Porquês Interativo", page_icon="🔎", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

col_titulo, col_org = st.columns([8, 2])
with col_titulo:
    st.title("🔎 5 Porquês Interativo")
with col_org:
    st.markdown(
        "<div style='text-align:right; padding-top:18px; color:#154453; font-weight:bold;'>NUATI – SECIN</div>",
        unsafe_allow_html=True,
    )

st.caption("Ferramenta para auxílio da identificação da causa-raiz — versão para testes.")

_init()

if st.session_state.phase == "input":
    tela_input()
else:
    tela_resultados()
