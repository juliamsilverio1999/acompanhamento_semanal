-- Gerado por scripts/init_db.py a partir de app/models.py. Não editar à mão.

CREATE TYPE unidade_medida AS ENUM ('m', 'm2', 'm3', 'kg', 't', 'un', 'vb', 'h', '%%');

CREATE TABLE atividades (
	id UUID NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	unidade_medida unidade_medida NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (nome)
);

CREATE TABLE obras (
	id UUID NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	cod_obra VARCHAR(5) NOT NULL, 
	uf VARCHAR(2) NOT NULL, 
	cidade VARCHAR(255) NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_obras_uf CHECK (uf = upper(uf) AND length(uf) = 2), 
	UNIQUE (cod_obra)
);

CREATE TABLE obra_atividade (
	id UUID NOT NULL, 
	obra_id UUID NOT NULL, 
	atividade_id UUID NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (obra_id, atividade_id), 
	FOREIGN KEY(obra_id) REFERENCES obras (id), 
	FOREIGN KEY(atividade_id) REFERENCES atividades (id)
);

CREATE TABLE produtividade_base_obra_atividade_semana (
	id UUID NOT NULL, 
	obra_atividade_id UUID NOT NULL, 
	semana INTEGER NOT NULL, 
	dia_inicial_semana DATE NOT NULL, 
	previsto_semana NUMERIC(18, 6) NOT NULL, 
	prod_orcada_media_equipe_dia NUMERIC(18, 6), 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (obra_atividade_id, semana), 
	UNIQUE (obra_atividade_id, dia_inicial_semana), 
	CONSTRAINT ck_base_semana CHECK (semana >= 1), 
	CONSTRAINT ck_base_previsto CHECK (previsto_semana >= 0), 
	CONSTRAINT ck_base_prod_orcada CHECK (prod_orcada_media_equipe_dia > 0), 
	FOREIGN KEY(obra_atividade_id) REFERENCES obra_atividade (id)
);

CREATE TABLE dados_obra_atividade (
	id UUID NOT NULL, 
	produtividade_base_obra_atividade_semana_id UUID NOT NULL, 
	real NUMERIC(18, 6) NOT NULL, 
	previsto_acumulado NUMERIC(18, 6) NOT NULL, 
	real_acumulado NUMERIC(18, 6) NOT NULL, 
	delta_acumulado NUMERIC(18, 6) NOT NULL, 
	equipe NUMERIC(18, 6), 
	prod_media_equipe_dia NUMERIC(18, 6), 
	indice_produtividade NUMERIC(18, 6), 
	justificativa TEXT, 
	dado_extra JSONB, 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_dados_equipe CHECK (equipe >= 0), 
	UNIQUE (produtividade_base_obra_atividade_semana_id), 
	FOREIGN KEY(produtividade_base_obra_atividade_semana_id) REFERENCES produtividade_base_obra_atividade_semana (id)
);
