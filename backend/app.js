require('dotenv').config({ path: require('path').join(__dirname, '.env') });

const express = require('express');
const path = require('path');
const pool = require('./src/config/database');

const estudanteRoutes = require('./src/routes/estudanteRoutes');
const responsavelRoutes = require('./src/routes/responsavelRoutes');
const solicitacaoRoutes = require('./src/routes/solicitacaoRoutes');
const authRoutes = require('./src/routes/authRoutes');

// Não iniciar uma API exposta sem uma chave JWT adequada.
if (process.env.NODE_ENV === 'production' &&
    (!process.env.JWT_SECRET || process.env.JWT_SECRET.length < 32)) {
    console.error('JWT_SECRET deve conter pelo menos 32 caracteres em produção.');
    process.exit(1);
}

const app = express();
app.use(express.json());

app.get('/api/health', (req, res) => {
    res.json({ mensagem: 'API do SISGECE funcionando' });
});

// Prontidão verifica banco e tabelas. Evita marcar a aplicação como saudável
// quando o PostgreSQL existe, mas o esquema ainda não foi instalado.
app.get('/api/ready', async (req, res) => {
    try {
        const resultado = await pool.query(`
            SELECT
                to_regclass('public.administradores') IS NOT NULL AS administradores,
                to_regclass('public.estudantes') IS NOT NULL AS estudantes,
                to_regclass('public.responsaveis') IS NOT NULL AS responsaveis,
                to_regclass('public.responsavel_estudante') IS NOT NULL AS vinculos,
                to_regclass('public.solicitacoes') IS NOT NULL AS solicitacoes
        `);

        if (!Object.values(resultado.rows[0]).every(Boolean)) {
            return res.status(503).json({
                status: 'indisponivel',
                motivo: 'Tabelas obrigatórias não encontradas'
            });
        }

        return res.json({ status: 'pronto' });
    } catch (erro) {
        console.error('Falha na verificação de prontidão:', erro.message);
        return res.status(503).json({ status: 'indisponivel' });
    }
});

app.use('/auth', authRoutes);
app.use('/estudantes', estudanteRoutes);
app.use('/responsaveis', responsavelRoutes);
app.use('/solicitacoes', solicitacaoRoutes);

app.use(express.static(path.join(__dirname, '../frontend')));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Servidor rodando em http://localhost:${PORT}`);
});
