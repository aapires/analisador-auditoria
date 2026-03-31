"""
5 Porquês Interativo (local) — roda com Ollama.

Fluxo:
  1. Usuário informa achado → gera cadeia completa.
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

MODEL_PADRAO = "gemma3:4b"

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
Você é um auditor interno sênior especialista em análise de causa raiz.
Sua tarefa é aplicar a técnica dos 5 Porquês a achados de auditoria.

Critério fundamental da causa raiz:
- A causa raiz DEVE ser uma falha estrutural em política, processo, sistema, competência ou cultura organizacional.
- Ela precisa ter poder de sanar não apenas o achado analisado, mas outros achados similares — caso fosse corrigida.
- Nunca identifique como causa raiz um sintoma, um evento pontual ou uma falha individual isolada.
- A causa raiz é justamente a resposta ao último porque da cadeia estabelecida.
- Pergunte-se: "Se corrigirmos isso, impediremos que problemas similares ocorram sistematicamente?" — só então é causa raiz.
- A recomendação deve atacar diretamente a causa raiz estrutural, dirigida à autoridade competente."""


def _listar_modelos():
    """Retorna lista de nomes de modelos disponíveis no Ollama."""
    try:
        resp = ollama.list()
        modelos = [m.model for m in resp.models]
        return modelos if modelos else [MODEL_PADRAO]
    except Exception:
        return [MODEL_PADRAO]


def _chamar_modelo(model: str, system: str, prompt: str) -> str:
    resp = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
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


def _parsear_passo(texto, n):
    p = r = ""
    for linha in texto.splitlines():
        l = _strip_md(linha)
        lu = l.upper()
        if lu.startswith(f"P{n}_PERGUNTA:"):
            v = l[len(f"P{n}_PERGUNTA:"):].strip()
            p = "" if v.upper().startswith("VAZIO") else v
        elif lu.startswith(f"P{n}_RESPOSTA:"):
            v = l[len(f"P{n}_RESPOSTA:"):].strip()
            r = "" if v.upper().startswith("VAZIO") else v
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


def gerar_cadeia_completa(achado, model):
    prompt = f"""Achado: {achado}

REGRA OBRIGATÓRIA: Preencha todos os 5 porquês completos (P1 até P5). Nenhum campo pode conter VAZIO.
Aprofunde cada resposta até atingir o 5º nível, chegando a uma falha estrutural na causa raiz.

Responda SOMENTE neste formato, sem texto adicional:
P1_PERGUNTA: Por quê [pergunta derivada do achado]?
P1_RESPOSTA: Porque [resposta].
P2_PERGUNTA: Por quê [pergunta baseada em P1_RESPOSTA]?
P2_RESPOSTA: Porque [resposta].
P3_PERGUNTA: Por quê [pergunta baseada em P2_RESPOSTA]?
P3_RESPOSTA: Porque [resposta].
P4_PERGUNTA: Por quê [pergunta baseada em P3_RESPOSTA]?
P4_RESPOSTA: Porque [resposta].
P5_PERGUNTA: Por quê [pergunta baseada em P4_RESPOSTA]?
P5_RESPOSTA: Porque [resposta — esta é a falha estrutural que é a causa raiz].
CAUSA_RAIZ: [descrição objetiva da falha estrutural identificada]
RECOMENDACAO: [recomendação focada em eliminar a causa raiz estrutural]"""

    texto = _chamar_modelo(model, SYSTEM_BASE, prompt)
    chain = []
    for n in range(1, 6):
        p, r = _parsear_passo(texto, n)
        if p and r:
            chain.append({"pergunta": p, "resposta": r})
    causa, rec = _parsear_conclusao(texto)
    return chain, causa, rec


def gerar_conclusao(achado, chain, model):
    ctx = _ctx(chain)
    prompt = f"""Achado: {achado}

Cadeia dos Porquês confirmada:
{ctx}

O último passo representa a causa raiz identificada. Gere a conclusão.
Responda SOMENTE neste formato:
CAUSA_RAIZ: [causa raiz com base no último passo da cadeia]
RECOMENDACAO: [recomendação focada na causa raiz, dirigida à autoridade competente]"""

    return _parsear_conclusao(_chamar_modelo(model, SYSTEM_BASE, prompt))


def gerar_alternativas(achado, chain, idx, model, excluir=None):
    pergunta = chain[idx]["pergunta"]
    ctx = _ctx(chain[:idx])
    excluir_txt = ""
    if excluir:
        excluir_txt = "\n\nNÃO repita estas respostas já apresentadas:\n" + "\n".join(
            f"- {a}" for a in excluir
        )
    prompt = f"""Achado: {achado}
{"Cadeia confirmada:\n" + ctx if ctx else ""}

Pergunta atual: {pergunta}

Gere EXATAMENTE 3 respostas alternativas plausíveis, cada uma representando uma causa diferente.
Cada resposta deve ser completa e não pode ser cortada.{excluir_txt}
Responda SOMENTE neste formato, sem texto adicional:
ALT_1: Porque [resposta 1].
ALT_2: Porque [resposta 2].
ALT_3: Porque [resposta 3]."""

    alts = []
    bloco = ""
    for linha in _chamar_modelo(model, SYSTEM_BASE, prompt).splitlines():
        l = _strip_md(linha)
        m = re.match(r"ALT_\d\s*:\s*(.+)", l, re.IGNORECASE)
        if m:
            if bloco:
                alts.append(bloco.strip())
            bloco = m.group(1).strip()
        elif bloco and l:
            bloco += " " + l
    if bloco:
        alts.append(bloco.strip())
    return alts[:3]


def regenerar_a_partir_de(achado, chain_confirmada, model):
    prox = len(chain_confirmada) + 1
    ctx = _ctx(chain_confirmada)

    linhas_fmt = []
    for i in range(prox, 6):
        linhas_fmt += [
            f"P{i}_PERGUNTA: Por quê [...]? — ou VAZIO",
            f"P{i}_RESPOSTA: Porque [...]. — ou VAZIO",
        ]
    linhas_fmt += ["CAUSA_RAIZ: [...]", "RECOMENDACAO: [...]"]

    prompt = f"""Achado: {achado}

Cadeia já confirmada:
{ctx}

Continue a partir do passo {prox}. Use VAZIO nos passos restantes se a causa raiz já foi identificada.
Responda SOMENTE neste formato:
{chr(10).join(linhas_fmt)}"""

    texto = _chamar_modelo(model, SYSTEM_BASE, prompt)
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
        "chain": [],
        "causa_raiz": "",
        "recomendacao": "",
        "editing_index": None,
        "editing_mode": None,
        "alternatives": None,
        "history": [],
        "model": MODEL_PADRAO,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in ["phase", "achado", "chain", "causa_raiz", "recomendacao",
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
    st.markdown("### Descreva o achado de auditoria")
    achado = st.text_area(
        "Achado:",
        height=160,
        key="inp_achado",
        placeholder="Descreva o achado com o máximo de contexto possível...",
        label_visibility="collapsed",
    )

    declaracao = st.checkbox("Declaro que esse achado não inclui dados com restrição de acesso.")

    with st.expander("⚙️ Configurações"):
        modelos_disponiveis = _listar_modelos()
        idx_padrao = modelos_disponiveis.index(MODEL_PADRAO) if MODEL_PADRAO in modelos_disponiveis else 0
        model = st.selectbox(
            "Modelo local (Ollama):",
            modelos_disponiveis,
            index=idx_padrao,
        )

    if st.button("Iniciar análise", type="primary"):
        if not declaracao:
            st.warning("É necessário confirmar a declaração antes de iniciar a análise.")
        elif not achado.strip():
            st.warning("Descreva o achado antes de continuar.")
        else:
            with st.spinner("Gerando análise dos 5 Porquês..."):
                try:
                    chain, causa, rec = gerar_cadeia_completa(achado.strip(), model)
                except Exception as e:
                    st.error(f"Erro ao conectar ao Ollama: {e}\n\nVerifique se o Ollama está rodando e o modelo `{model}` está instalado.")
                    st.stop()
            st.session_state.update({
                "phase": "results",
                "achado": achado.strip(),
                "chain": chain,
                "causa_raiz": causa,
                "recomendacao": rec,
                "editing_index": None,
                "editing_mode": None,
                "alternatives": None,
                "history": [],
                "model": model,
            })
            st.rerun()


def tela_resultados():
    s = st.session_state

    # ── Cabeçalho ──
    col_info, col_undo, col_new = st.columns([7, 1.5, 1.5])
    with col_info:
        st.markdown(f"**Achado:** {s.achado}")
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

    # ── Cadeia de porquês ──
    for i, step in enumerate(s.chain):
        editing_this = s.editing_index == i

        if editing_this and s.editing_mode == "edit":
            # ── Modo: editar texto livre ──
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
                            try:
                                s.chain, s.causa_raiz, s.recomendacao = regenerar_a_partir_de(
                                    s.achado, s.chain[:i + 1], s.model
                                )
                            except Exception as e:
                                st.error(f"Erro ao recalcular cadeia: {e}")
                                st.stop()
                        _cancelar_edicao(s)
                        st.rerun()
                    else:
                        st.warning("A resposta não pode estar vazia.")
            with col_cancelar:
                if st.button("Cancelar", key=f"cancel_edit_{i}"):
                    _cancelar_edicao(s)
                    st.rerun()

        elif editing_this and s.editing_mode == "suggestions":
            # ── Modo: sugestões da IA ──
            if s.alternatives is None:
                with st.spinner("Gerando sugestões..."):
                    try:
                        s.alternatives = gerar_alternativas(s.achado, s.chain, i, s.model)
                    except Exception as e:
                        st.error(f"Erro ao gerar sugestões: {e}")
                        _cancelar_edicao(s)
                        st.stop()
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
                        try:
                            s.chain, s.causa_raiz, s.recomendacao = regenerar_a_partir_de(
                                s.achado, s.chain[:i + 1], s.model
                            )
                        except Exception as e:
                            st.error(f"Erro ao recalcular cadeia: {e}")
                            st.stop()
                    _cancelar_edicao(s)
                    st.rerun()
            with col_atualizar:
                if st.button("🔄 Atualizar sugestões", key=f"refresh_{i}"):
                    with st.spinner("Gerando novas sugestões..."):
                        try:
                            s.alternatives = gerar_alternativas(
                                s.achado, s.chain, i, s.model, excluir=s.alternatives
                            )
                        except Exception as e:
                            st.error(f"Erro ao gerar sugestões: {e}")
                            st.stop()
                    st.rerun()
            with col_cancelar:
                if st.button("Cancelar", key=f"cancel_sug_{i}"):
                    _cancelar_edicao(s)
                    st.rerun()

        else:
            # ── Estado normal: exibe card + 3 botões ──
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
                            try:
                                causa, rec = gerar_conclusao(s.achado, nova_chain, s.model)
                            except Exception as e:
                                st.error(f"Erro ao gerar conclusão: {e}")
                                st.stop()
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

st.set_page_config(page_title="5 Porquês (local)", page_icon="🔎", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

st.title("5 Porquês Interativo")
st.markdown("**Ferramenta:** Análise interativa de 5 porquês — modelo local via Ollama")

_init()

if st.session_state.phase == "input":
    tela_input()
else:
    tela_resultados()
