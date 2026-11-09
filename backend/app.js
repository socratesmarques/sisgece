require('dotenv').config({ path: require('path').join(__dirname, '.env'), quiet: true });
const express = require('express');
const helmet = require('helmet');
const { rateLimit } = require('express-rate-limit');
const path = require('path');
const { production, trustProxy } = require('./src/config/runtime');
const pool = require('./src/config/database');
const app = express();
app.disable('x-powered-by');
app.set('trust proxy', trustProxy);
app.use(helmet({ contentSecurityPolicy: production ? { directives: {
    defaultSrc: ["'self'"], scriptSrc: ["'self'"], styleSrc: ["'self'"],
    imgSrc: ["'self'", 'data:'], objectSrc: ["'none'"], frameAncestors: ["'none'"],
    upgradeInsecureRequests: production ? [] : null
} } : false, strictTransportSecurity: production ? undefined : false }));
app.use((req, res, next) => {
    if (/^\/(auth|estudantes|responsaveis|solicitacoes|api)(\/|$)/i.test(req.path)) {
        res.set('Cache-Control', 'no-store');
    }
    // As escritas exigem JSON: formulários externos não podem usar a sessão.
    if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method)) {
        if (req.get('sec-fetch-site') === 'cross-site') {
            return res.status(403).json({ erro: 'Origem não permitida' });
        }
        if (!req.is('application/json')) return res.status(415).json({ erro: 'Envie application/json' });
    }
    next();
});
app.use(express.json({ limit: '32kb', strict: true }));
app.get('/favicon.ico', (req, res) => res.status(204).end());
app.get('/api/health', (req, res) => res.json({ status: 'ativo' }));
app.get('/api/ready', async (req, res) => {
    try {
        const resultado = await pool.query(`SELECT
            to_regclass('public.administradores') IS NOT NULL AS administradores,
            to_regclass('public.estudantes') IS NOT NULL AS estudantes,
            to_regclass('public.responsaveis') IS NOT NULL AS responsaveis,
            to_regclass('public.responsavel_estudante') IS NOT NULL AS vinculos,
            to_regclass('public.solicitacoes') IS NOT NULL AS solicitacoes`);
        const pronto = Object.values(resultado.rows[0]).every(Boolean);
        res.status(pronto ? 200 : 503).json({ status: pronto ? 'pronto' : 'indisponivel' });
    } catch { res.status(503).json({ status: 'indisponivel' }); }
});
app.use(rateLimit({ windowMs: 60000, limit: 120, standardHeaders: 'draft-8', legacyHeaders: false,
    message: { erro: 'Muitas requisições. Tente novamente em um minuto.' } }));
app.use('/auth', require('./src/routes/authRoutes'));
app.use('/estudantes', require('./src/routes/estudanteRoutes'));
app.use('/responsaveis', require('./src/routes/responsavelRoutes'));
app.use('/solicitacoes', require('./src/routes/solicitacaoRoutes'));
const frontend = path.join(__dirname, '../frontend');
app.get(['/', '/index.html'], (req, res) => res.redirect('/pages/admin-login.html'));
// A demonstração com credenciais fictícias nunca é distribuída em produção.
app.get('/demo', (req, res) => production ? res.sendStatus(404) : res.sendFile(path.join(frontend, 'index.html')));
app.use('/pages', express.static(path.join(frontend, 'pages')));
app.use('/assets/css', express.static(path.join(frontend, 'assets/css')));
if (production) {
    for (const file of ['admin-login.js', 'admin-dashboard.js']) {
        app.get('/assets/js/' + file, (req, res) => res.sendFile(path.join(frontend, 'assets/js', file)));
    }
} else app.use('/assets/js', express.static(path.join(frontend, 'assets/js')));
app.use((req, res) => res.status(404).json({ erro: 'Recurso não encontrado' }));
app.use((erro, req, res, next) => {
    if (res.headersSent) return next(erro);
    const status = erro.type === 'entity.too.large' ? 413 : erro.type === 'entity.parse.failed' ? 400 : 500;
    console.error(JSON.stringify({ evento: 'falha_http', metodo: req.method, status, codigo: erro.code || erro.type || 'interno' }));
    res.status(status).json({ erro: status === 500 ? 'Erro interno do servidor' : 'Corpo da requisição inválido' });
});
if (require.main === module) {
    const server = app.listen(process.env.PORT || 3000, () => console.log('SISGECE iniciado.'));
    let encerrando = false;
    const encerrar = () => {
        if (encerrando) return;
        encerrando = true;
        const deadline = setTimeout(() => process.exit(1), 15000).unref();
        server.close(async () => {
            await pool.end();
            clearTimeout(deadline);
            process.exit(0);
        });
    };
    process.on('SIGTERM', encerrar);
    process.on('SIGINT', encerrar);
}
module.exports = app;
