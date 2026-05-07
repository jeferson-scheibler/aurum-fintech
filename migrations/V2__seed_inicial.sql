INSERT INTO usuario (nome, login, senha, situacao) VALUES
('Administrador', 'fin_admin', 'Fin407', 'ativo')
ON CONFLICT (login) DO NOTHING;

INSERT INTO lancamento (descricao, data_lancamento, valor, tipo_lancamento, situacao) VALUES
('Salário março',        '2026-03-05', 4500.00, 'receita', 'ativo'),
('Aluguel',              '2026-03-10', 1200.00, 'despesa', 'ativo'),
('Freelance web',        '2026-03-12',  800.00, 'receita', 'ativo'),
('Supermercado',         '2026-03-14',  350.00, 'despesa', 'ativo'),
('Internet',             '2026-03-15',   99.90, 'despesa', 'ativo');
