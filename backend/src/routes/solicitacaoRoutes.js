const express = require('express');

const autenticar = require('../middlewares/authMiddleware');

const {
    criarSolicitacao,
    listarSolicitacoes,
    listarPendentes,
    aprovarSolicitacao,
    reprovarSolicitacao
} = require('../controllers/solicitacaoController');

const { validarCriacao, validarDecisao } = require('../middlewares/validation');
const router = express.Router();
router.use(autenticar);

router.post('/', validarCriacao, criarSolicitacao);

router.get(
    '/',
    listarSolicitacoes
);

router.get(
    '/pendentes',
    listarPendentes
);

router.patch(
    '/:id/aprovar',
    validarDecisao,
    aprovarSolicitacao
);

router.patch(
    '/:id/reprovar',
    validarDecisao,
    reprovarSolicitacao
);

module.exports = router;