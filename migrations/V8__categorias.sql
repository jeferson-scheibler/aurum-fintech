DROP TABLE IF EXISTS categoria;

CREATE TABLE categoria (
    id   SERIAL PRIMARY KEY,
    nome VARCHAR(60) NOT NULL UNIQUE
);

INSERT INTO categoria (nome) VALUES
    ('Alimentação'), ('Transporte'), ('Moradia'), ('Lazer'),
    ('Saúde'), ('Educação'), ('Salário'), ('Outros');

ALTER TABLE lancamento ADD COLUMN categoria_id INTEGER REFERENCES categoria(id);

-- aprendizado: descrição normalizada -> categoria escolhida manualmente da última vez
CREATE TABLE categoria_regra (
    descricao_norm VARCHAR(255) PRIMARY KEY,
    categoria_id   INTEGER NOT NULL REFERENCES categoria(id)
);
