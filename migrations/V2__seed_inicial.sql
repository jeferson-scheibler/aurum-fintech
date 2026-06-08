-- Único usuário inicial: admin / admin123 (hash pbkdf2:sha256, gerado com werkzeug.security)
INSERT INTO usuario (nome, login, senha, situacao) VALUES
('Administrador', 'admin',
 'pbkdf2:sha256:1000000$TwPEEdmjhtx67yXP$fb274296f99bfa49523bca2bbd2bc6b3a8991012470f6d957b616c52a3c9cb0a',
 'ativo')
ON CONFLICT (login) DO NOTHING;
