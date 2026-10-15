require('dotenv').config();

const express = require('express');

const estudanteRoutes = require('./src/routes/estudanteRoutes');
const responsavelRoutes = require('./src/routes/responsavelRoutes');
const solicitacaoRoutes = require('./src/routes/solicitacaoRoutes');

const app = express();

app.use(express.json());

app.get('/', (req, res) => {
    res.json({
        mensagem: 'API do SISGECE funcionando'
    });
});

app.use('/estudantes', estudanteRoutes);

app.use('/responsaveis', responsavelRoutes);

app.use('/solicitacoes', solicitacaoRoutes);

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
    console.log(`Servidor rodando em http://localhost:${PORT}`);
});