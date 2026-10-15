const express = require('express');

const autenticar = require('../middlewares/authMiddleware');

const {
    criarSolicitacao,
    listarSolicitacoes,
    listarPendentes,
    aprovarSolicitacao,
    reprovarSolicitacao
} = require('../controllers/solicitacaoController');

const router = express.Router();

router.post('/', criarSolicitacao);

router.get(
    '/',
    autenticar,
    listarSolicitacoes
);

router.get(
    '/pendentes',
    autenticar,
    listarPendentes
);

router.patch(
    '/:id/aprovar',
    autenticar,
    aprovarSolicitacao
);

router.patch(
    '/:id/reprovar',
    autenticar,
    reprovarSolicitacao
);

module.exports = router;