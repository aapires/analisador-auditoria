"""
5 Porquês Interativo (local) — roda com Ollama (Gemma 3 4B ou outro modelo local).

Fluxo:
  1. Usuário informa achado + área → gera cadeia completa.
  2. Cada resposta tem 3 botões: Causa Raiz, Editar, Sugestões.
  3. Causa Raiz: trunca a cadeia no passo atual e regera conclusão.
  4. Editar: caixa de texto livre para digitar a resposta, recalcula cadeia.
  5. Sugestões: exibe 3 alternativas geradas pela IA, com botão de atualizar.
  6. Desfazer: volta ao estado anterior.
"""

import copy
import re
import ollama
import streamlit as st

MODEL = "gemma3:4b"

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


def _llm(prompt):
    resp = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_BASE},
            {"role": "user", "content": prompt},
        ],
    )
    return resp["message"]["content"]


def _strip_md(text):
    return text.replace("**", "").replace("*", "").strip()


def _ctx(chain):
    return "\n".join(
        f"Passo {i}: {s['pergunta']} / {s['resposta']}"
        for i, s in enumerate(chain, 1)
    )


def _limpar_vazio(v):
    """Remove sufixos '— VAZIO' ou '- VAZIO' que o modelo às vezes adiciona."""
    v = re.sub(r"\s*[—\-]+\s*VAZIO\s*$", "", v, flags=re.IGNORECASE).strip()
    return "" if v.upper().startswith("VAZIO") else v


def _parsear_passo(texto, n):
    p = r = ""
    for linha in texto.splitlines():
        l = _strip_md(linha)
        lu = l.upper()
        if lu.startswith(f"P{n}_PERGUNTA:"):
            p = _limpar_vazio(l[len(f"P{n}_PERGUNTA:"):].strip())
        elif lu.startswith(f"P{n}_RESPOSTA:"):
            r = _limpar_vazio(l[len(f"P{n}_RESPOSTA:"):].strip())
    return p, r


def _parsear_conclusao(texto):
    causa = rec = ""
    for linha in texto.splitlines():
        l = _strip_md(linha)
        lu = l.upper()
        if lu.startswith("CAUSA_RAIZ:"):
            causa = l[len("CAUSA_RAIZ:"):].strip()
        elif lu.startswith("RECOMENDACAO:"):
            rec = l[len("RECOMENDACAO:"):].strip()
        elif lu.startswith("RECOMENDAÇÃO:"):
            rec = l[len("RECOMENDAÇÃO:"):].strip()
    return causa, rec


def gerar_cadeia_completa(achado, area):
    prompt = f"""Área: {area}
Achado: {achado}

Aplique a técnica dos 5 Porquês. Responda SOMENTE neste formato exato, sem texto adicional, sem markdown:
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

    texto = _llm(prompt)
    chain = []
    for n in range(1, 6):
        p, r = _parsear_passo(texto, n)
        if p and r:
            chain.append({"pergunta": p, "resposta": r})
    causa, rec = _parsear_conclusao(texto)
    return chain, causa, rec


def gerar_conclusao(achado, area, chain):
    ctx = _ctx(chain)
    prompt = f"""Área: {area}
Achado: {achado}

Cadeia dos Porquês confirmada:
{ctx}

O último passo representa a causa raiz identificada. Gere a conclusão.
Responda SOMENTE neste formato exato, sem markdown:
CAUSA_RAIZ: [causa raiz com base no último passo da cadeia]
RECOMENDACAO: [recomendação focada na causa raiz, dirigida à autoridade competente]"""

    return _parsear_conclusao(_llm(prompt))


def gerar_alternativas(achado, area, chain, idx, excluir=None):
    pergunta = chain[idx]["pergunta"]
    ctx = _ctx(chain[:idx])
    excluir_txt = ""
    if excluir:
        excluir_txt = "\n\nNÃO repita estas respostas já apresentadas:\n" + "\n".join(
            f"- {a}" for a in excluir
        )
    prompt = f"""Área: {area}
Achado: {achado}
{"Cadeia confirmada:\n" + ctx if ctx else ""}

Pergunta atual: {pergunta}

Gere EXATAMENTE 3 respostas alternativas plausíveis, cada uma representando uma causa diferente.{excluir_txt}
Responda SOMENTE neste formato exato, sem markdown, sem numeração adicional:
ALT_1: Porque [resposta 1].
ALT_2: Porque [resposta 2].
ALT_3: Porque [resposta 3]."""

    alts = []
    for linha in _llm(prompt).splitlines():
        l = _strip_md(linha)
        m = re.search(r"ALT_\d\s*:\s*(.+)", l, re.IGNORECASE)
        if m:
            alts.append(m.group(1).strip())
    return alts[:3]


def regenerar_a_partir_de(achado, area, chain_confirmada):
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
Responda SOMENTE neste formato exato, sem markdown:
{chr(10).join(linhas_fmt)}"""

    texto = _llm(prompt)
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
        "editing_mode": None,
        "alternatives": None,
        "history": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in ["phase", "achado", "area", "chain", "causa_raiz", "recomendacao",
              "editing_index", "editing_mode", "alternatives", "history"]:
        if k in st.session_state:
            del st.session_state[k]


def _cancelar_edicao(s):
    s.editing_index = None
    s.editing_mode = None
    s.alternatives = None


def _salvar_historico(s):
    s.history.append({
        "chain": copy.deepcopy(s.chain),
        "causa_raiz": s.causa_raiz,
        "recomendacao": s.recomendacao,
    })


# ── Telas ─────────────────────────────────────────────────────────────────────

def tela_input():
    st.markdown("Informe o achado de auditoria e a área para iniciar a análise.")
    achado = st.text_area("Achado de auditoria:", height=120, key="inp_achado")
    area = st.text_input("Área:", key="inp_area")

    if st.button("Analisar", type="primary"):
        if achado.strip() and area.strip():
            try:
                with st.spinner(f"Gerando análise com {MODEL} (local)..."):
                    chain, causa, rec = gerar_cadeia_completa(achado.strip(), area.strip())
                st.session_state.update({
                    "phase": "results",
                    "achado": achado.strip(),
                    "area": area.strip(),
                    "chain": chain,
                    "causa_raiz": causa,
                    "recomendacao": rec,
                    "editing_index": None,
                    "editing_mode": None,
                    "alternatives": None,
                    "history": [],
                })
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao conectar ao Ollama: {e}\n\nVerifique se o Ollama está rodando e o modelo `{MODEL}` está instalado.")
        else:
            st.warning("Preencha o achado e a área.")


def tela_resultados():
    s = st.session_state

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
                _cancelar_edicao(s)
                st.rerun()
    with col_new:
        if st.button("Nova análise", use_container_width=True):
            _reset()
            st.rerun()

    st.divider()

    for i, step in enumerate(s.chain):
        editing_this = s.editing_index == i

        if editing_this and s.editing_mode == "edit":
            st.markdown(
                f'<div class="step-card-editing"><strong>{i+1}. {step["pergunta"]}</strong></div>',
                unsafe_allow_html=True,
            )
            nova_resp = st.text_area(
                "Sua resposta:",
                value=step["resposta"],
                key=f"custom_{i}",
                height=80,
            )
            col_salvar, col_cancelar, _ = st.columns([1, 1, 6])
            with col_salvar:
                if st.button("Salvar", type="primary", key=f"save_edit_{i}"):
                    nova = nova_resp.strip()
                    if nova:
                        _salvar_historico(s)
                        s.chain[i]["resposta"] = nova
                        with st.spinner("Recalculando cadeia..."):
                            s.chain, s.causa_raiz, s.recomendacao = regenerar_a_partir_de(
                                s.achado, s.area, s.chain[:i + 1]
                            )
                        _cancelar_edicao(s)
                        st.rerun()
                    else:
                        st.warning("A resposta não pode estar vazia.")
            with col_cancelar:
                if st.button("Cancelar", key=f"cancel_edit_{i}"):
                    _cancelar_edicao(s)
                    st.rerun()

        elif editing_this and s.editing_mode == "suggestions":
            if s.alternatives is None:
                with st.spinner("Gerando sugestões..."):
                    s.alternatives = gerar_alternativas(s.achado, s.area, s.chain, i)
                st.rerun()

            st.markdown(
                f'<div class="step-card-editing"><strong>{i+1}. {step["pergunta"]}</strong></div>',
                unsafe_allow_html=True,
            )
            choice = st.radio(
                "Selecione uma sugestão:",
                s.alternatives,
                key=f"radio_{i}",
            )
            col_salvar, col_atualizar, col_cancelar, _ = st.columns([1, 2, 1, 4])
            with col_salvar:
                if st.button("Salvar", type="primary", key=f"save_sug_{i}"):
                    _salvar_historico(s)
                    s.chain[i]["resposta"] = choice
                    with st.spinner("Recalculando cadeia..."):
                        s.chain, s.causa_raiz, s.recomendacao = regenerar_a_partir_de(
                            s.achado, s.area, s.chain[:i + 1]
                        )
                    _cancelar_edicao(s)
                    st.rerun()
            with col_atualizar:
                if st.button("🔄 Atualizar sugestões", key=f"refresh_{i}"):
                    with st.spinner("Gerando novas sugestões..."):
                        s.alternatives = gerar_alternativas(
                            s.achado, s.area, s.chain, i, excluir=s.alternatives
                        )
                    st.rerun()
            with col_cancelar:
                if st.button("Cancelar", key=f"cancel_sug_{i}"):
                    _cancelar_edicao(s)
                    st.rerun()

        else:
            col_step, col_cr, col_ed, col_sg = st.columns([9, 1, 1, 1])
            with col_step:
                st.markdown(
                    f'<div class="step-card">'
                    f'<strong>{i+1}. {step["pergunta"]}</strong><br>'
                    f'{step["resposta"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if s.editing_index is None:
                with col_cr:
                    if st.button("🎯", key=f"cr_{i}", help="Marcar como causa raiz — encerra a cadeia aqui"):
                        _salvar_historico(s)
                        nova_chain = s.chain[:i + 1]
                        with st.spinner("Gerando conclusão..."):
                            causa, rec = gerar_conclusao(s.achado, s.area, nova_chain)
                        s.chain = nova_chain
                        s.causa_raiz = causa
                        s.recomendacao = rec
                        st.rerun()
                with col_ed:
                    if st.button("✏️", key=f"edit_{i}", help="Editar resposta manualmente"):
                        s.editing_index = i
                        s.editing_mode = "edit"
                        st.rerun()
                with col_sg:
                    if st.button("💡", key=f"sug_{i}", help="Ver sugestões da IA"):
                        s.editing_index = i
                        s.editing_mode = "suggestions"
                        s.alternatives = None
                        st.rerun()

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

st.set_page_config(page_title="5 Porquês (local)", page_icon="🔎", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

st.title("🔎 5 Porquês Interativo")
st.caption(f"Modelo local: `{MODEL}` via Ollama — versão para testes.")

_init()

if st.session_state.phase == "input":
    tela_input()
else:
    tela_resultados()
