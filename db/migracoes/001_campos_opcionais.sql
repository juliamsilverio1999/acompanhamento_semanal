-- 2026-11-03 · Importação SES Teresópolis
-- Idempotente: pode rodar mais de uma vez (aplicada por scripts/init_db.py).

-- Prod. orçada opcional e sem padrão 1: vazio = índice não calculado
ALTER TABLE produtividade_base_obra_atividade_semana
    ALTER COLUMN prod_orcada_media_equipe_dia DROP NOT NULL,
    ALTER COLUMN prod_orcada_media_equipe_dia DROP DEFAULT;

-- Real pode ser negativo (estorno / correção de medição)
ALTER TABLE dados_obra_atividade DROP CONSTRAINT IF EXISTS ck_dados_real;

-- Equipe decimal (média da semana) e opcional (vazio = não informada)
ALTER TABLE dados_obra_atividade
    ALTER COLUMN equipe TYPE NUMERIC(18, 6),
    ALTER COLUMN equipe DROP NOT NULL;
