CREATE TABLE IF NOT EXISTS usuario (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100),
    login VARCHAR(50) UNIQUE,
    senha VARCHAR(100),
    situacao VARCHAR(20) DEFAULT 'ativo'
);

CREATE TABLE IF NOT EXISTS lancamento (
    id SERIAL PRIMARY KEY,
    descricao VARCHAR(255),
    data_lancamento DATE,
    valor NUMERIC(10,2),
    tipo_lancamento VARCHAR(20),
    situacao VARCHAR(20) DEFAULT 'ativo'
);

INSERT INTO usuario (nome, login, senha, situacao) VALUES
('Administrador', 'admin', 'admin123', 'ativo');

INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao) VALUES
('Salário março',        '2026-03-05', 4500.00, 'receita', 'ativo'),
('Aluguel',              '2026-03-10', 1200.00, 'despesa', 'ativo'),
('Freelance web',        '2026-03-12',  800.00, 'receita', 'ativo'),
('Supermercado',         '2026-03-14',  350.00, 'despesa', 'ativo'),
('Internet',             '2026-03-15',   99.90, 'despesa', 'ativo'),
('Energia elétrica',     '2026-03-15',  180.00, 'despesa', 'ativo'),
('Consultoria TI',       '2026-03-18', 1200.00, 'receita', 'ativo'),
('Plano de saúde',       '2026-03-20',  320.00, 'despesa', 'ativo'),
('Transferência receb.', '2026-03-22',  500.00, 'receita', 'ativo'),
('Combustível',          '2026-03-24',  210.00, 'despesa', 'ativo');
