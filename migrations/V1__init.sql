CREATE TABLE IF NOT EXISTS usuario (
    id       SERIAL PRIMARY KEY,
    nome     VARCHAR(100),
    login    VARCHAR(50) UNIQUE,
    senha    VARCHAR(100),
    email    VARCHAR(150),
    situacao VARCHAR(20) DEFAULT 'ativo'
);

CREATE TABLE IF NOT EXISTS lancamento (
    id              SERIAL PRIMARY KEY,
    descricao       VARCHAR(255),
    data_lancamento DATE,
    valor           NUMERIC(10,2),
    tipo_lancamento VARCHAR(20),
    situacao        VARCHAR(20) DEFAULT 'ativo'
);
