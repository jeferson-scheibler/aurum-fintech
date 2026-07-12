CREATE TABLE meta (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(100) NOT NULL,
    tipo        VARCHAR(20) NOT NULL,       -- 'limite' | 'economia'
    valor_alvo  NUMERIC(10,2) NOT NULL,
    data_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    data_alvo   DATE,                        -- usado só quando tipo = 'economia'
    situacao    VARCHAR(20) NOT NULL DEFAULT 'ativo'
);
