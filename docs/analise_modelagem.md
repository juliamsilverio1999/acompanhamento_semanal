# Análise da modelagem: Obras Productivity Data Architecture

Pontos levantados ao implementar o diagrama. Cada item diz o que foi feito no código local e o que precisa de decisão do time.

## 1. Já ajustado no código (desvios do diagrama)

| # | Ponto | Problema | O que foi feito |
|---|---|---|---|
| 1.1 | `decimal(10,6)` | Comporta só 4 dígitos inteiros (máx. 9.999,999999). Acumulados como m² de alvenaria ou kg de aço passam disso rapidamente, e o insert falha. | `numeric(18,6)` |
| 1.2 | DADOS 1:N com a semana base | Permitiria dois "realizados" para a mesma semana, e o acumulado ficaria ambíguo. | FK `unique` (1:1). Para histórico de correções, ver 3.4. |
| 1.3 | Falta de unicidade | Daria para duplicar obra, vínculo obra × atividade e semana. | `unique(cod_obra)`, `unique(obra_id, atividade_id)`, `unique(obra_atividade_id, semana)` e `unique(obra_atividade_id, dia_inicial_semana)` |
| 1.4 | Auditoria | Sem rastreio de quando o registro mudou. | `criado_em` / `atualizado_em`. No Dataverse isso já vem nativo, com *created by/modified by*. |
| 1.5 | `UF` | Só a convenção de maiúsculas. | `CHECK` de maiúscula com 2 caracteres; a API converte automaticamente. |

## 2. Decisões de regra de negócio (precisam de validação)

1. **Dias trabalhados na semana**: `prod_media_equipe_dia` precisa de um divisor que não existe no modelo. Hoje é uma variável global (`DIAS_TRABALHADOS_SEMANA=5`). Feriados, sábados e chuva mudam isso por semana e por obra. *Sugestão:* coluna `dias_trabalhados` em DADOS (padrão 5).
2. **O que é `equipe`?** Número de equipes ou de pessoas? A fórmula é a mesma, mas a `prod_orcada_media_equipe_dia` precisa estar na mesma base, senão o índice não significa nada.
3. **Semana sem apontamento**: hoje entra como real = 0 no acumulado, o que faz o delta despencar. A alternativa é tratar como "não informado" e interromper a curva real. Quem decide é o negócio.
4. **`prod_orcada_media_equipe_dia` com padrão 1**: um padrão "silencioso" gera um índice aparentemente válido, mas falso. *Sugestão:* tornar obrigatório (sem padrão), ou nulo e o índice não ser calculado.
5. **`semana` × `dia_inicial_semana`**: os dois campos são redundantes. A semana é sequencial da obra ou ISO? Hoje é sequencial e o dia inicial é validado contra `PRIMEIRO_DIA_SEMANA` (segunda). Na obra a semana de medição às vezes vai de sábado a sexta.
6. **Justificativa obrigatória**: está implementada com limite configurável (`INDICE_LIMITE_JUSTIFICATIVA=0.90`). Confirmar o limite e se ela também vale para índice muito *acima* (ex.: > 1,3, que pode indicar erro de apontamento).

## 3. Melhorias de modelagem sugeridas

1. **`previsto_acumulado` no lugar errado**: ele só existe em DADOS, então semanas futuras (sem apontamento) não têm curva planejada gravada. A API calcula isso na leitura (`previsto_acumulado_plano`), mas o natural é a coluna morar em `PRODUTIVIDADE_BASE_...`.
2. **Campos acumulados gravados**: são derivados, e corrigir a semana 3 obriga a recalcular da 3 em diante. Isso está implementado (recalcula a série inteira a cada gravação). Manter gravado é útil no Power Apps, porque agregações como Sum/running total sofrem com limite de delegação. O custo é que a consistência passa a depender de quem grava, que precisa ser sempre o backend ou um flow.
3. **Replanejamento**: alterar `previsto_semana` sobrescreve o plano original. Se o time quiser comparar *linha de base × plano revisado*, é preciso versionar (ex.: `versao_plano` ou tabela de revisões).
4. **Histórico de apontamentos**: se o realizado puder ser corrigido depois do fechamento da semana, convém um status (`aberto` / `fechado`) e/ou log de alterações.
5. **Obra**: faltam `data_inicio`, `status` (ativa/encerrada) e possivelmente o responsável. A `data_inicio` permitiria derivar `semana` a partir do `dia_inicial_semana`.
6. **Quantidade total orçada da atividade na obra** (em OBRA_ATIVIDADE): permite mostrar o % concluído, que é a pergunta mais comum do gestor.
7. **`unidade_medida` como enum**: no Dataverse vira *Choice*. Está ok, mas incluir unidade nova exige deploy. Uma tabela de unidades é mais flexível.

## 4. Pontos para a migração ao Power Apps

| Local (dev) | Power Apps / Dataverse | Atenção |
|---|---|---|
| `uuid` | GUID nativo | ok |
| `numeric(18,6)` | Decimal (até 10 casas) | ok |
| `enum unidade_medida` | Choice | ok |
| `jsonb dado_extra` | **Não existe**: vira texto multilinha | Não dá para consultar/filtrar. Se algum campo extra virar relevante, promover a coluna. |
| Motor de cálculo Python | Power Fx, Power Automate ou plugin C# | A regra precisa ser **reimplementada**. Os testes em `tests/test_calculos.py` servem de especificação executável. Alternativa: manter esta API e expor via *custom connector*. |
| Recalcular a série inteira | Flow disparado na gravação | Cuidado com loops (flow que grava e se redispara). |
| Prévia do índice antes de salvar | Fórmula Power Fx no próprio formulário | É uma conta simples, cabe no app. |

A decisão de arquitetura mais importante para a produção é **onde o cálculo vai morar**: (a) Dataverse + Power Fx/Automate, ou (b) esta API Python hospedada (Azure) + custom connector. O protótipo foi montado de forma que (b) seja direto e (a) tenha os testes como referência.
