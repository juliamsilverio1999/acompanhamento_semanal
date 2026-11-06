"""Protótipo de UX (Streamlit). Fala com o backend só via HTTP, como o
Power Apps faria via conector — nenhuma regra de cálculo mora aqui."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import requests  # noqa: E402
import streamlit as st  # noqa: E402

from app.config import settings  # noqa: E402

API = settings.api_base_url.rstrip("/")
UNIDADES = ["m", "m2", "m3", "kg", "t", "un", "vb", "h", "%"]

st.set_page_config(page_title="Acompanhamento Semanal", layout="wide")


def api(metodo, caminho, **kwargs):
    try:
        r = requests.request(metodo, f"{API}{caminho}", timeout=10, **kwargs)
    except requests.ConnectionError:
        st.error(f"API fora do ar em {API}. Suba com: python -m app")
        st.stop()
    if r.status_code >= 400:
        try:
            detalhe = r.json().get("detail")
        except ValueError:
            detalhe = r.text
        st.error(f"Erro {r.status_code}: {detalhe}")
        return None
    return r.json() if r.content else None


def selecionar_obra_atividade(chave):
    obras = api("GET", "/obras") or []
    if not obras:
        st.info("Cadastre uma obra primeiro.")
        st.stop()
    obra = st.selectbox(
        "Obra", obras, format_func=lambda o: f"{o['cod_obra']} - {o['nome']}", key=f"obra_{chave}"
    )
    vinculos = api("GET", f"/obras/{obra['id']}/atividades") or []
    if not vinculos:
        st.info("Esta obra não tem atividades vinculadas.")
        st.stop()
    return st.selectbox(
        "Atividade",
        vinculos,
        format_func=lambda v: f"{v['atividade']['nome']} ({v['atividade']['unidade_medida']})",
        key=f"ativ_{chave}",
    )


def num(v):
    return None if v is None else float(v)


def texto_ou_nulo(v):
    """Valor da grade para o JSON da API: célula vazia (NaN) vira null."""
    return None if pd.isna(v) else str(v)


def tabela_acompanhamento(linhas):
    registros = []
    for l in linhas:
        d = l["dados"] or {}
        registros.append({
            "semana": l["semana"],
            "início": l["dia_inicial_semana"],
            "previsto": num(l["previsto_semana"]),
            "previsto acum.": num(l["previsto_acumulado_plano"]),
            "real": num(d.get("real")),
            "real acum.": num(d.get("real_acumulado")),
            "delta acum.": num(d.get("delta_acumulado")),
            "equipe": num(d.get("equipe")),
            "prod. média equipe/dia": num(d.get("prod_media_equipe_dia")),
            "prod. orçada": num(l["prod_orcada_media_equipe_dia"]),
            "índice": num(d.get("indice_produtividade")),
            "justificativa": d.get("justificativa"),
        })
    return pd.DataFrame(registros)


# --- Páginas ---------------------------------------------------------------

def pagina_apontamento():
    st.header("Apontamento semanal")
    vinculo = selecionar_obra_atividade("apont")
    unidade = vinculo["atividade"]["unidade_medida"]
    linhas = api("GET", f"/obra-atividades/{vinculo['id']}/acompanhamento") or []
    if not linhas:
        st.info("Sem semanas planejadas para esta atividade. Use a página Planejamento.")
        return

    linha = st.selectbox(
        "Semana",
        linhas,
        format_func=lambda l: f"Semana {l['semana']} - {l['dia_inicial_semana']}"
        + ("  ✔ apontada" if l["dados"] else ""),
    )
    dados = linha["dados"] or {}
    c1, c2 = st.columns(2)
    c1.metric(f"Previsto na semana ({unidade})", linha["previsto_semana"])
    c2.metric(
        "Prod. orçada (equipe/dia)",
        linha["prod_orcada_media_equipe_dia"] or "- (sem índice)",
    )

    # Sem st.form de propósito: os campos reagem a cada alteração e a prévia
    # do índice aparece antes de salvar (comportamento esperado no Power Apps).
    chave = linha["base_id"]
    real = st.number_input(
        f"Realizado na semana ({unidade})", value=float(dados.get("real") or 0),
        key=f"real_{chave}", help="Valor negativo = estorno / correção de medição.",
    )
    equipe = st.number_input(
        "Equipe média da semana", min_value=0.0, step=0.5,
        value=float(dados["equipe"]) if dados.get("equipe") is not None else None,
        key=f"eq_{chave}", placeholder="não informada",
    )
    corpo = {"real": str(real), "equipe": None if equipe is None else str(equipe)}
    previa = api("POST", f"/semanas/{chave}/realizado/previa", json=corpo) or {}
    p1, p2 = st.columns(2)
    p1.metric("Prod. média equipe/dia (prévia)", previa.get("prod_media_equipe_dia") or "-")
    p2.metric("Índice de produtividade (prévia)", previa.get("indice_produtividade") or "-")

    rotulo = "Justificativa" + (" (obrigatória)" if previa.get("exige_justificativa") else "")
    justificativa = st.text_area(rotulo, value=dados.get("justificativa") or "", key=f"just_{chave}")

    if st.button("Salvar apontamento", type="primary"):
        corpo["justificativa"] = justificativa
        if api("PUT", f"/semanas/{chave}/realizado", json=corpo):
            st.success("Apontamento salvo e série recalculada.")
            st.rerun()


def pagina_dashboard():
    st.header("Dashboard")
    vinculo = selecionar_obra_atividade("dash")
    linhas = api("GET", f"/obra-atividades/{vinculo['id']}/acompanhamento") or []
    if not linhas:
        st.info("Sem dados.")
        return
    df = tabela_acompanhamento(linhas)
    serie = df.set_index("semana")
    st.subheader(f"Curva acumulada ({vinculo['atividade']['unidade_medida']})")
    st.line_chart(serie[["previsto acum.", "real acum."]])
    st.subheader("Índice de produtividade")
    st.bar_chart(serie[["índice"]])
    st.dataframe(df, hide_index=True)


DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
COLUNAS_VALOR = ["previsto_semana", "prod_orcada_media_equipe_dia"]


def colunas_planejamento(unidade):
    return {
        "base_id": None,  # oculta
        "semana": st.column_config.NumberColumn("Semana"),
        "dia_inicial_semana": st.column_config.DateColumn("Início", format="DD/MM/YYYY"),
        "dia_final_semana": st.column_config.DateColumn("Fim", format="DD/MM/YYYY"),
        "previsto_semana": st.column_config.NumberColumn(
            f"Previsto na semana ({unidade})", min_value=0, step=0.001, required=True
        ),
        "prod_orcada_media_equipe_dia": st.column_config.NumberColumn(
            f"Prod. orçada equipe/dia ({unidade})", min_value=0.001, step=0.001,
            help="Vazio = sem produtividade orçada: o índice não é calculado.",
        ),
        "apontada": st.column_config.CheckboxColumn("Apontada"),
    }


def montar_semanas(proxima, inicio, qtd, anterior):
    """Gera a lista de semanas a partir da data inicial. Se o usuário mudar a
    data ou a quantidade, os valores já digitados são mantidos por posição."""
    linhas = []
    for i in range(qtd):
        dia = inicio + timedelta(weeks=i)
        linha = {
            "semana": proxima + i,
            "dia_inicial_semana": dia,
            "dia_final_semana": dia + timedelta(days=6),
            "previsto_semana": None,
            "prod_orcada_media_equipe_dia": None,
        }
        if anterior is not None and i < len(anterior):
            for col in COLUNAS_VALOR:
                linha[col] = anterior.iloc[i][col]
        linhas.append(linha)
    return pd.DataFrame(linhas).astype({col: "float64" for col in COLUNAS_VALOR})


def pagina_planejamento():
    st.header("Planejamento (produtividade base)")
    s = st.session_state
    if "aviso_plan" in s:
        st.success(s.pop("aviso_plan"))

    vinculo = selecionar_obra_atividade("plan")
    unidade = vinculo["atividade"]["unidade_medida"]
    linhas = api("GET", f"/obra-atividades/{vinculo['id']}/acompanhamento") or []

    if linhas:
        semanas_existentes(vinculo, linhas, unidade)

    st.subheader("Novas semanas")
    proxima = max((l["semana"] for l in linhas), default=0) + 1
    if linhas:
        inicio_padrao = date.fromisoformat(linhas[-1]["dia_inicial_semana"]) + timedelta(weeks=1)
    else:
        hoje = date.today()
        inicio_padrao = hoje - timedelta(days=(hoje.weekday() - settings.primeiro_dia_semana) % 7)

    estado = f"plano_{vinculo['id']}"
    c1, c2 = st.columns(2)
    inicio = c1.date_input(
        f"Dia inicial da semana {proxima}", value=inicio_padrao, format="DD/MM/YYYY",
        key=f"{estado}_inicio",
    )
    qtd = int(c2.number_input(
        "Número de semanas", min_value=1, max_value=260, value=4, step=1, key=f"{estado}_qtd"
    ))
    dia_invalido = inicio.weekday() != settings.primeiro_dia_semana
    if dia_invalido:
        st.error(
            f"A semana deve começar na {DIAS_SEMANA[settings.primeiro_dia_semana]} "
            f"(PRIMEIRO_DIA_SEMANA). A data escolhida é uma {DIAS_SEMANA[inicio.weekday()]}."
        )

    # A lista é recriada quando muda a data inicial, a quantidade ou a próxima semana
    assinatura = (proxima, inicio, qtd)
    if s.get(f"{estado}_assinatura") != assinatura:
        s[f"{estado}_base"] = montar_semanas(proxima, inicio, qtd, s.get(f"{estado}_ultimo"))
        s[f"{estado}_ultimo"] = s[f"{estado}_base"]
        s[f"{estado}_assinatura"] = assinatura
        s[f"{estado}_versao"] = s.get(f"{estado}_versao", 0) + 1

    with st.container(border=True):
        st.markdown("**Repetir valor para todas as semanas**")
        r1, r2 = st.columns(2)
        rep_previsto = r1.number_input(
            f"Previsto na semana ({unidade})", min_value=0.0, value=None, key=f"{estado}_rep_prev"
        )
        rep_prod = r2.number_input(
            f"Prod. orçada equipe/dia ({unidade})", min_value=0.001, value=None,
            key=f"{estado}_rep_prod",
        )
        so_vazias = st.checkbox("Preencher só as semanas ainda vazias", key=f"{estado}_so_vazias")
        if st.button(
            "Repetir nas semanas", disabled=rep_previsto is None and rep_prod is None
        ):
            df = s[f"{estado}_ultimo"].copy()
            for col, valor in zip(COLUNAS_VALOR, (rep_previsto, rep_prod)):
                if valor is not None:
                    df.loc[df[col].isna() if so_vazias else df.index, col] = valor
            # Nova chave = editor reinicia com os valores repetidos
            s[f"{estado}_base"] = s[f"{estado}_ultimo"] = df
            s[f"{estado}_versao"] += 1
            st.rerun()

    editado = st.data_editor(
        s[f"{estado}_base"],
        key=f"{estado}_editor_{s[f'{estado}_versao']}",
        hide_index=True,
        num_rows="fixed",
        disabled=["semana", "dia_inicial_semana", "dia_final_semana"],
        column_config=colunas_planejamento(unidade),
    )
    s[f"{estado}_ultimo"] = editado

    pendentes = editado.loc[editado["previsto_semana"].isna(), "semana"].tolist()
    st.caption(
        f"{qtd} semanas · total previsto: {editado['previsto_semana'].sum():,.3f} {unidade}"
    )
    if pendentes:
        st.info("Falta preencher as semanas: " + ", ".join(str(n) for n in pendentes))

    if st.button("Salvar planejamento", type="primary", disabled=bool(pendentes) or dia_invalido):
        corpo = [
            {
                "semana": int(l.semana),
                "dia_inicial_semana": l.dia_inicial_semana.isoformat(),
                "previsto_semana": str(l.previsto_semana),
                "prod_orcada_media_equipe_dia": texto_ou_nulo(l.prod_orcada_media_equipe_dia),
            }
            for l in editado.itertuples()
        ]
        if api("POST", f"/obra-atividades/{vinculo['id']}/semanas", json=corpo):
            for sufixo in ("base", "ultimo", "assinatura"):
                s.pop(f"{estado}_{sufixo}", None)
            s["aviso_plan"] = f"{qtd} semanas salvas (semanas {proxima} a {proxima + qtd - 1})."
            st.rerun()


def semanas_existentes(vinculo, linhas, unidade):
    """Semanas já gravadas: edição direta na lista; salva só as linhas alteradas."""
    s = st.session_state
    chave = f"existentes_{vinculo['id']}"
    atual = pd.DataFrame([
        {
            "base_id": l["base_id"],
            "semana": l["semana"],
            "dia_inicial_semana": date.fromisoformat(l["dia_inicial_semana"]),
            "previsto_semana": float(l["previsto_semana"]),
            "prod_orcada_media_equipe_dia": num(l["prod_orcada_media_equipe_dia"]),
            "apontada": l["dados"] is not None,
        }
        for l in linhas
    ]).astype({col: "float64" for col in COLUNAS_VALOR})
    with st.expander(f"Semanas já planejadas ({len(linhas)})"):
        editado = st.data_editor(
            atual,
            key=f"{chave}_{s.get(chave, 0)}",
            hide_index=True,
            num_rows="fixed",
            disabled=["semana", "dia_inicial_semana", "apontada"],
            column_config=colunas_planejamento(unidade),
        )
        # fillna: NaN != NaN, e prod. orçada vazia não pode contar como alteração
        alteradas = editado[
            (editado[COLUNAS_VALOR].fillna(-1) != atual[COLUNAS_VALOR].fillna(-1)).any(axis=1)
        ]
        st.caption("Alterar o previsto recalcula os acumulados das semanas já apontadas.")
        if st.button("Salvar alterações", disabled=alteradas.empty, key=f"{chave}_salvar"):
            ok = all(
                api("PATCH", f"/semanas/{l.base_id}", json={
                    "previsto_semana": str(l.previsto_semana),
                    "prod_orcada_media_equipe_dia": texto_ou_nulo(l.prod_orcada_media_equipe_dia),
                })
                for l in alteradas.itertuples()
            )
            if ok:
                s[chave] = s.get(chave, 0) + 1
                s["aviso_plan"] = f"{len(alteradas)} semana(s) atualizada(s)."
                st.rerun()


def pagina_cadastros():
    st.header("Cadastros")
    c1, c2 = st.columns(2)
    with c1, st.form("obra", clear_on_submit=True):
        st.subheader("Nova obra")
        corpo = {
            "nome": st.text_input("Nome"),
            "cod_obra": st.text_input("Código (até 5)", max_chars=5),
            "uf": st.text_input("UF", max_chars=2),
            "cidade": st.text_input("Cidade"),
        }
        if st.form_submit_button("Salvar obra") and api("POST", "/obras", json=corpo):
            st.success("Obra criada.")
    with c2, st.form("atividade", clear_on_submit=True):
        st.subheader("Nova atividade")
        corpo = {
            "nome": st.text_input("Nome da atividade"),
            "unidade_medida": st.selectbox("Unidade", UNIDADES),
        }
        if st.form_submit_button("Salvar atividade") and api("POST", "/atividades", json=corpo):
            st.success("Atividade criada.")

    obras = api("GET", "/obras") or []
    atividades = api("GET", "/atividades") or []

    if atividades:
        editar_atividade(atividades)

    st.subheader("Vincular atividade à obra")
    if obras and atividades:
        with st.form("vinculo"):
            obra = st.selectbox("Obra", obras, format_func=lambda o: f"{o['cod_obra']} - {o['nome']}")
            ativ = st.selectbox("Atividade", atividades, format_func=lambda a: a["nome"])
            if st.form_submit_button("Vincular") and api(
                "POST", f"/obras/{obra['id']}/atividades", json={"atividade_id": ativ["id"]}
            ):
                st.success("Vinculado.")


def editar_atividade(atividades):
    s = st.session_state
    if "aviso_ativ" in s:
        st.success(s.pop("aviso_ativ"))
    with st.container(border=True):
        st.subheader("Editar atividade")
        # Fora do form: trocar a atividade recarrega nome e unidade atuais
        ativ = st.selectbox(
            "Atividade", atividades, key="editar_ativ",
            format_func=lambda a: f"{a['nome']} ({a['unidade_medida']})",
        )
        with st.form(f"editar_ativ_{ativ['id']}"):
            nome = st.text_input("Nome", value=ativ["nome"])
            unidade = st.selectbox(
                "Unidade", UNIDADES, index=UNIDADES.index(ativ["unidade_medida"])
            )
            st.caption(
                "Trocar a unidade muda só o rótulo: os valores já lançados "
                "(previsto, realizado, prod. orçada) não são convertidos."
            )
            if st.form_submit_button("Salvar alterações"):
                corpo = {"nome": nome.strip(), "unidade_medida": unidade}
                if corpo == {"nome": ativ["nome"], "unidade_medida": ativ["unidade_medida"]}:
                    st.info("Nada mudou.")
                elif api("PATCH", f"/atividades/{ativ['id']}", json=corpo):
                    s["aviso_ativ"] = f"Atividade '{corpo['nome']}' atualizada ({corpo['unidade_medida']})."
                    st.rerun()


PAGINAS = {
    "Apontamento semanal": pagina_apontamento,
    "Dashboard": pagina_dashboard,
    "Planejamento": pagina_planejamento,
    "Cadastros": pagina_cadastros,
}
PAGINAS[st.sidebar.radio("Página", list(PAGINAS))]()
