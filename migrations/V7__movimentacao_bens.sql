CREATE TABLE bem (
    id       SERIAL PRIMARY KEY,
    nome     VARCHAR(100) NOT NULL,
    tipo     VARCHAR(20) NOT NULL,             -- 'investimento' | 'imovel' | 'veiculo' | 'outro'
    valor    NUMERIC(12,2) NOT NULL DEFAULT 0, -- usado só pros bens manuais; investimento é calculado
    auto     BOOLEAN NOT NULL DEFAULT FALSE,   -- true = valor mantido automaticamente pelas movimentações
    situacao VARCHAR(20) NOT NULL DEFAULT 'ativo'
);

ALTER TABLE lancamento ADD COLUMN bem_id INTEGER REFERENCES bem(id);
ALTER TABLE lancamento ADD COLUMN direcao VARCHAR(10); -- 'entrada' | 'saida', só quando tipo_lancamento='movimentacao'

INSERT INTO bem (nome, tipo, valor, auto) VALUES ('Investimentos', 'investimento', 0, TRUE);

-- Reclassifica o histórico: "reservado" (era despesa) veio de dentro pra fora do caixa = entrada
-- no investimento; "retirado" (era receita) = saída do investimento de volta pro caixa.
UPDATE lancamento
SET direcao = CASE WHEN tipo_lancamento = 'despesa' THEN 'entrada' ELSE 'saida' END,
    bem_id  = (SELECT id FROM bem WHERE nome = 'Investimentos'),
    tipo_lancamento = 'movimentacao'
WHERE descricao ILIKE '%investimento%'
  AND tipo_lancamento IN ('receita', 'despesa');
