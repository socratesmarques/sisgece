const express = require('express');

const {
    criarSolicitacao
} = require('../controllers/solicitacaoController');

const router = express.Router();

router.post('/', criarSolicitacao);

module.exports = router;