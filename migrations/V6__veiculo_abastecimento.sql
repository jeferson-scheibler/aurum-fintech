CREATE TABLE veiculo (
    id       SERIAL PRIMARY KEY,
    apelido  VARCHAR(50) NOT NULL,
    marca    VARCHAR(50),
    modelo   VARCHAR(50),
    ano      INTEGER,
    situacao VARCHAR(20) NOT NULL DEFAULT 'ativo'
);

CREATE TABLE abastecimento (
    id            SERIAL PRIMARY KEY,
    veiculo_id    INTEGER NOT NULL REFERENCES veiculo(id),
    data          DATE NOT NULL,
    km            NUMERIC(10,1) NOT NULL,
    litros        NUMERIC(8,2) NOT NULL,
    valor_total   NUMERIC(10,2) NOT NULL,
    lancamento_id INTEGER REFERENCES lancamento(id),
    situacao      VARCHAR(20) NOT NULL DEFAULT 'ativo'
);

INSERT INTO veiculo (apelido, marca, modelo, ano) VALUES ('Equinox', 'Chevrolet', 'Equinox', 2022);
